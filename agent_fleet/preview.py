"""Preview dashboard and process lifecycle for worktree fleets."""

from __future__ import annotations

import html
import http.server
import json
import os
import signal
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from .commands import run
from .models import AgentSlot, FleetConfig, PreviewConfig, PreviewServiceConfig, PreviewSlot, RuntimePreviewService

STATE_FILE = "preview-processes.json"
ROUTES = [
    "/",
    "/health",
    "/docs",
    "/api/health",
    "/login",
    "/dashboard",
    "/admin",
    "/settings",
]


def start_preview(cfg: FleetConfig, slots: list[AgentSlot], install_deps: bool = True) -> int:
    """Start configured preview services and serve the dashboard until interrupted."""

    if not cfg.preview.configured:
        print(
            "Preview is not configured: add [[preview.services]] in agentfleet.toml "
            "(repo root). See the README \"Give This To Your AI Agent\" checklist, or run "
            "`agentfleet doctor` after editing."
        )
        return 1

    preview_slots = build_preview_slots(cfg, slots)
    if not preview_slots:
        print("No previewable worktrees found for the configured preview service dirs.")
        return 1

    validate_ports(cfg, preview_slots)
    state_root = cfg.resolved_state_root()
    state_root.mkdir(parents=True, exist_ok=True)

    processes: list[subprocess.Popen[str]] = []
    try:
        for preview in preview_slots:
            processes.extend(start_preview_processes(cfg, preview, install_deps))
        write_state(cfg, preview_slots, processes)
        dashboard_path = write_dashboard(cfg, preview_slots)
        server = start_dashboard_server(dashboard_path.parent, cfg.preview.dashboard_port)
        print_summary(cfg, preview_slots)
        wait_forever(processes, server)
    finally:
        for proc in processes:
            stop_process(proc.pid)
        clear_state(cfg)
    return 0


def build_preview_slots(cfg: FleetConfig, slots: list[AgentSlot]) -> list[PreviewSlot]:
    """Return preview metadata with unique ports across all agent families."""

    preview_slots: list[PreviewSlot] = []
    for preview_index, slot in enumerate(
        [slot for slot in slots if is_previewable(cfg, slot.path)], start=1
    ):
        preview_slots.append(build_preview_slot(cfg, slot, preview_index))
    return preview_slots


def preview_service_configs(preview: PreviewConfig) -> tuple[PreviewServiceConfig, ...]:
    """Return generic service configs, converting legacy API/UI config when needed."""

    if preview.services:
        return preview.services
    if not (preview.api_dir and preview.ui_dir and preview.api_command and preview.ui_command):
        return ()
    return (
        PreviewServiceConfig(
            name="api",
            port_base=preview.api_base_port,
            directory=preview.api_dir,
            command=preview.api_command,
            install_command="",
            install_if_missing="",
        ),
        PreviewServiceConfig(
            name="web",
            port_base=preview.ui_base_port,
            directory=preview.ui_dir,
            command=preview.ui_command,
            env={preview.ui_api_env_var: "{api_url}"},
            install_command=preview.install_command,
            install_if_missing=preview.install_if_missing,
            primary=True,
        ),
    )


def build_runtime_services(
    preview: PreviewConfig, slot: AgentSlot, log_root: Path, port_offset: int
) -> list[RuntimePreviewService]:
    """Resolve service configs into per-worktree ports, directories, and logs."""

    services = []
    for config in preview_service_configs(preview):
        services.append(
            RuntimePreviewService(
                name=config.name,
                port=config.port_base + port_offset,
                directory=slot.path / config.directory,
                command=config.command,
                env=config.env,
                log=log_root / f"{slot.label}-{config.name}.log",
                primary=config.primary,
                install_command=config.install_command,
                install_if_missing=config.install_if_missing,
            )
        )
    if services and not any(service.primary for service in services):
        last = services[-1]
        services[-1] = RuntimePreviewService(
            name=last.name,
            port=last.port,
            directory=last.directory,
            command=last.command,
            env=last.env,
            log=last.log,
            primary=True,
            install_command=last.install_command,
            install_if_missing=last.install_if_missing,
        )
    return services


def service_port(services: list[RuntimePreviewService], name: str, fallback: int) -> int:
    """Return the port for a named service with a compatibility fallback."""

    aliases = {
        "api": {"api", "backend", "server"},
        "web": {"web", "ui", "frontend", "app"},
    }
    names = aliases.get(name, {name})
    for service in services:
        if service.name in names:
            return service.port
    return fallback


def build_preview_slot(cfg: FleetConfig, slot: AgentSlot, preview_index: int | None = None) -> PreviewSlot:
    """Return preview metadata for a slot."""

    port_offset = slot.index if preview_index is None else preview_index
    log_root = cfg.resolved_state_root() / "logs"
    services = build_runtime_services(cfg.preview, slot, log_root, port_offset)
    api_port = service_port(services, "api", cfg.preview.api_base_port + port_offset)
    ui_port = service_port(services, "web", cfg.preview.ui_base_port + port_offset)
    return PreviewSlot(
        slot=slot,
        api_port=api_port,
        ui_port=ui_port,
        api_log=log_root / f"{slot.label}-api.log",
        ui_log=log_root / f"{slot.label}-ui.log",
        services=tuple(services),
    )


def is_previewable(cfg: FleetConfig, worktree: Path) -> bool:
    """Return whether a worktree contains the configured preview service directories."""

    return all((worktree / service.directory).is_dir() for service in preview_service_configs(cfg.preview))


def validate_ports(cfg: FleetConfig, previews: list[PreviewSlot]) -> None:
    """Fail early if any configured preview port is occupied."""

    ports = [cfg.preview.dashboard_port]
    for preview in previews:
        ports.extend(service.port for service in preview.services)
    for port in ports:
        if not port_is_free(port):
            raise SystemExit(f"Port {port} is already in use. Stop it or use fewer slots.")


def port_is_free(port: int) -> bool:
    """Return whether localhost has an active listener on the port."""

    checks = [(socket.AF_INET, ("127.0.0.1", port)), (socket.AF_INET6, ("::1", port))]
    for family, address in checks:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                if sock.connect_ex(address) == 0:
                    return False
            except OSError:
                continue
    return True


def start_preview_processes(
    cfg: FleetConfig, preview: PreviewSlot, install_deps: bool
) -> list[subprocess.Popen[str]]:
    """Start the configured service commands for one preview slot."""

    processes: list[subprocess.Popen[str]] = []
    for service in preview.services:
        service.log.parent.mkdir(parents=True, exist_ok=True)
        if install_deps and service.install_if_missing and service.install_command:
            missing = service.directory / service.install_if_missing
            if not missing.exists():
                print(f"[{preview.slot.label}:{service.name}] installing dependencies...")
                run(split_command(render_service_template(service.install_command, preview, service)), cwd=service.directory)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(preview.slot.path)
        for key, value in service.env.items():
            env[key] = render_service_template(value, preview, service)

        log_handle = service.log.open("w", encoding="utf-8")
        processes.append(
            subprocess.Popen(
                split_command(render_service_template(service.command, preview, service)),
                cwd=service.directory,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        )
    return processes


def render_command(template: str, preview: PreviewSlot) -> str:
    """Render preview command templates."""

    service = preview.primary_service
    port = service.port if service is not None else preview.ui_port
    return template.format(
        api_port=preview.api_port,
        ui_port=preview.ui_port,
        api_url=preview.api_url,
        ui_url=preview.ui_url,
        port=port,
        service_port=port,
        worktree=preview.slot.path,
    )


def render_service_template(template: str, preview: PreviewSlot, service: RuntimePreviewService) -> str:
    """Render a service command or env template."""

    return template.format(
        api_port=preview.api_port,
        ui_port=preview.ui_port,
        api_url=preview.api_url,
        ui_url=preview.ui_url,
        port=service.port,
        service_port=service.port,
        service_url=service.url,
        service_name=service.name,
        worktree=preview.slot.path,
    )


def split_command(command: str) -> list[str]:
    """Split a shell-like command template into argv."""

    import shlex

    return shlex.split(command)


def write_dashboard(cfg: FleetConfig, previews: list[PreviewSlot]) -> Path:
    """Write a live preview wall with embedded UI frames."""

    dashboard_dir = cfg.resolved_state_root() / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(render_card(preview) for preview in previews)
    path = dashboard_dir / "index.html"
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentFleet Preview Wall</title>
  <style>
    :root {{
      --bg:
        radial-gradient(circle at 18% 12%, rgba(232, 196, 176, .58), transparent 28%),
        radial-gradient(circle at 78% 6%, rgba(91, 138, 114, .50), transparent 32%),
        radial-gradient(circle at 62% 88%, rgba(194, 101, 92, .28), transparent 34%),
        linear-gradient(160deg, #4a7a5a 0%, #6b9a72 25%, #c4b896 55%, #8a6a4a 80%, #3d2f1f 100%);
      --surface: rgba(255,255,255,.78);
      --ink: #171714;
      --muted: #6f7168;
      --line: rgba(22,22,20,.12);
      --accent: #3d6650;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      background-attachment: fixed;
      color: var(--ink);
    }}
    .shell {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 16px;
      padding: 16px;
    }}
    aside, .card {{
      border: 1px solid rgba(255,255,255,.52);
      background: var(--surface);
      backdrop-filter: blur(20px) saturate(120%);
      box-shadow: 0 24px 80px rgba(38,43,31,.18);
      border-radius: 16px;
    }}
    aside {{ padding: 18px; }}
    h1 {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 34px;
      line-height: .96;
      font-weight: 400;
      letter-spacing: -.03em;
    }}
    .copy {{ color: var(--muted); line-height: 1.45; font-size: 13px; }}
    .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 18px 0; }}
    .stat {{ border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: rgba(255,255,255,.55); }}
    .label {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .12em; font-weight: 700; }}
    .value {{ margin-top: 2px; font-family: Georgia, serif; font-size: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 16px; }}
    .card {{ overflow: hidden; }}
    .card-head {{ padding: 14px 16px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 12px; align-items: start; }}
    .card h2 {{ margin: 2px 0 0; font-size: 16px; }}
    .links {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .pill {{ display: inline-block; padding: 7px 10px; border-radius: 999px; background: #fff; border: 1px solid var(--line); color: var(--accent); font-weight: 700; text-decoration: none; font-size: 12px; }}
    iframe {{ width: 100%; height: 420px; display: block; border: 0; background: #fff; }}
    .meta {{ padding: 12px 16px; display: grid; gap: 8px; border-top: 1px solid var(--line); }}
    code {{ display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; background: rgba(255,255,255,.66); border: 1px solid var(--line); border-radius: 9px; padding: 8px; font-size: 12px; }}
    @media (max-width: 900px) {{ .shell {{ grid-template-columns: 1fr; }} .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="label">AgentFleet</div>
      <h1>Preview Wall</h1>
      <p class="copy">Local review wall for agent worktrees. Each card embeds a live UI preview backed by its isolated API and worktree.</p>
      <div class="stat-grid">
        <div class="stat"><div class="label">Agents</div><div class="value">{len(previews)}</div></div>
        <div class="stat"><div class="label">Dashboard</div><div class="value">{cfg.preview.dashboard_port}</div></div>
      </div>
      <p class="copy">Generated at <code>{html.escape(str(path))}</code></p>
    </aside>
    <main class="grid">
      {cards}
    </main>
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )
    return path


def render_card(preview: PreviewSlot) -> str:
    """Render one live preview card."""

    slot = preview.slot
    return f"""<article class="card">
  <div class="card-head">
    <div>
      <div class="label">{html.escape(slot.label)}</div>
      <h2>{html.escape(slot.branch)}</h2>
    </div>
    <div class="links">
      <a class="pill" href="{preview.ui_url}" target="_blank" rel="noreferrer">UI :{preview.ui_port}</a>
      <a class="pill" href="{preview.api_url}" target="_blank" rel="noreferrer">API :{preview.api_port}</a>
    </div>
  </div>
  <iframe src="{preview.ui_url}" loading="lazy" title="{html.escape(slot.label)} preview"></iframe>
  <div class="meta">
    <div class="label">Worktree</div>
    <code>{html.escape(str(slot.path))}</code>
    <div class="label">Logs</div>
    <code>{html.escape(str(preview.api_log))}</code>
    <code>{html.escape(str(preview.ui_log))}</code>
  </div>
</article>"""


def write_dashboard(cfg: FleetConfig, previews: list[PreviewSlot]) -> Path:
    """Write the recovered multi-page preview fleet dashboard."""

    dashboard_dir = cfg.resolved_state_root() / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    ensure_recovered_assets(dashboard_dir)
    payload = preview_payload(cfg, previews)
    dashboard_path = dashboard_dir / "index.html"
    dashboard_path.write_text(render_preview_page(cfg, previews, payload), encoding="utf-8")
    write_secondary_pages(cfg, dashboard_dir, payload)
    return dashboard_path


def render_card(preview: PreviewSlot) -> str:
    """Render one recovered preview review card."""

    slot = preview.slot
    service_links = "".join(
        f'<a class="pill {"accent" if service.primary else ""}" href="{service.url}" target="_blank" rel="noreferrer">'
        f'{html.escape(service.name)}:{service.port}</a>'
        for service in preview.services
    )
    service_rows = "".join(
        f'<div class="label">{html.escape(service.name)}</div><code>{html.escape(str(service.log))}</code>'
        for service in preview.services
    )
    return f"""<article class="card" id="{html.escape(slot.label)}" data-preview-card data-preview-label="{html.escape(slot.label)}">
  <div class="meta">
    <div class="title">
      <strong>{html.escape(slot.label)}</strong>
      <div class="agent-links">
        <a class="pill accent" data-open-link href="{preview.ui_url}" target="_blank" rel="noreferrer">open preview</a>
        {service_links}
      </div>
    </div>
    <div class="route-control">
      <div class="route-row">
        <div class="label">Endpoint</div>
        <input class="route-input" data-route-input list="route-recommendations" value="/" placeholder="/dashboard" aria-label="{html.escape(slot.label)} endpoint">
        <button class="mini-btn primary" data-apply-route type="button">Apply</button>
        <button class="mini-btn" data-reset-route type="button">Reset</button>
      </div>
      <div class="route-chips">{route_chips(ROUTES[:4])}</div>
      <div class="current-url" data-current-url>{preview.ui_url}</div>
    </div>
    <div class="review-row">
      <div class="label">Review</div>
      <select class="status-select" data-status aria-label="{html.escape(slot.label)} status">
        <option value="reviewing">Reviewing</option>
        <option value="approved">Approved</option>
        <option value="needs-work">Needs work</option>
        <option value="blocked">Blocked</option>
      </select>
      <input class="notes-input" data-notes placeholder="note / ticket / what to check" aria-label="{html.escape(slot.label)} notes">
    </div>
    <div class="meta-grid">
      <div class="label">Branch</div><code>{html.escape(slot.branch)}</code>
      <div class="label">Worktree</div><code>{html.escape(str(slot.path))}</code>
      {service_rows}
    </div>
  </div>
  <iframe src="{preview.ui_url}" loading="lazy"></iframe>
</article>"""


def preview_payload(cfg: FleetConfig, previews: list[PreviewSlot]) -> dict[str, object]:
    """Return JSON data consumed by the recovered dashboard JavaScript."""

    return {
        "dashboardPort": cfg.preview.dashboard_port,
        "routes": ROUTES,
        "previews": [
            {
                "slot": index,
                "label": preview.slot.label,
                "branch": preview.slot.branch,
                "path": str(preview.slot.path),
                "uiUrl": preview.ui_url,
                "apiUrl": preview.api_url,
                "uiPort": preview.ui_port,
                "apiPort": preview.api_port,
                "apiLog": str(preview.api_log),
                "uiLog": str(preview.ui_log),
                "services": [
                    {
                        "name": service.name,
                        "url": service.url,
                        "port": service.port,
                        "log": str(service.log),
                        "primary": service.primary,
                    }
                    for service in preview.services
                ],
            }
            for index, preview in enumerate(previews, start=1)
        ],
    }


def render_preview_page(
    cfg: FleetConfig, previews: list[PreviewSlot], payload: dict[str, object]
) -> str:
    """Render the recovered Agent Previews page."""

    cards = "\n".join(render_card(preview) for preview in previews)
    content = f"""
          <div class="page-head">
            <div>
              <h2 class="page-title">Agent Previews</h2>
              <p class="page-copy">Review each worktree on its own localhost port. Tickets, exports, commands, and settings live on their own pages.</p>
            </div>
            <div class="grid-controls" data-grid-controls>
              <button class="side-btn" data-grid-mode="auto" type="button">Auto grid</button>
              <button class="side-btn" data-grid-mode="one" type="button">1 column</button>
              <button class="side-btn primary" data-grid-mode="two" type="button">2 columns</button>
              <button class="side-btn" data-grid-mode="three" type="button">3 columns</button>
              <button class="side-btn" data-grid-mode="dense" type="button">Dense</button>
            </div>
          </div>
          <div class="preview-grid" data-preview-grid>{cards}</div>
          <datalist id="route-recommendations"></datalist>
"""
    return render_shell(cfg, "previews", "Agent Previews", content, payload)


def write_secondary_pages(cfg: FleetConfig, dashboard_dir: Path, payload: dict[str, object]) -> None:
    """Restore dashboard subpages, excluding hidden/dead pages."""

    for stale_page in ("endpoints", "symphony"):
        stale_dir = dashboard_dir / stale_page
        if stale_dir.exists():
            shutil.rmtree(stale_dir)

    pages = {
        "tickets": (
            "Tickets & Reviews",
            '<div class="review-board" data-review-board></div>',
            "Approve, block, and annotate agent work from one place.",
        ),
        "exports": (
            "Linear Export",
            '<div class="section-card"><div class="panel-title">Export review packet</div><p class="small-copy">Copy/paste this packet into Linear, GitHub, or a release note.</p><textarea class="export-box" data-export-box spellcheck="false"></textarea><div class="button-row"><button class="side-btn primary" data-refresh-export type="button">Refresh export</button><button class="side-btn" data-copy-export type="button">Copy</button></div></div>',
            "Turn local review state into a portable handoff.",
        ),
        "commands": (
            "Fleet Commands",
            '<div class="command-list" data-command-list></div><div class="section-card"><div class="panel-title">Manual commands</div><div class="command-item"><code>agentfleet preview</code></div><div class="command-item"><code>agentfleet preview --include-main</code></div><div class="command-item"><code>agentfleet preview --limit 2</code></div><div class="command-item"><code>agentfleet stop</code></div></div>',
            "Copy launch, preview, and log commands for this fleet.",
        ),
        "settings": (
            "Settings",
            '<div class="settings-grid"><div class="section-card"><div class="panel-title">Theme</div><select class="status-select" data-theme-select><option value="light">Light</option><option value="dark">Dark</option></select></div><div class="section-card"><div class="panel-title">Background</div><select class="status-select" data-background-select><option value="dusk">Dusk</option><option value="painterly">Painterly</option><option value="paper">Paper</option><option value="charcoal">Charcoal</option></select></div></div>',
            "Local-only preferences stored in browser localStorage.",
        ),
    }
    for slug, (title, body, copy) in pages.items():
        page_dir = dashboard_dir / slug
        page_dir.mkdir(exist_ok=True)
        content = f"""
          <div class="page-head">
            <div>
              <h2 class="page-title">{html.escape(title)}</h2>
              <p class="page-copy">{html.escape(copy)}</p>
            </div>
          </div>
          {body}
"""
        (page_dir / "index.html").write_text(
            render_shell(cfg, slug, title, content, payload),
            encoding="utf-8",
        )


def render_shell(
    cfg: FleetConfig, page: str, title: str, content: str, payload: dict[str, object]
) -> str:
    """Render the shared recovered dashboard shell."""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · AgentFleet</title>
  <link rel="stylesheet" href="/assets/dashboard.css">
</head>
<body data-page="{html.escape(page)}">
  <div class="shell">
    {render_sidebar(page)}
    <section class="main-panel">
      <header>
        <div class="crumbs"><span>Workspace</span><span>/</span><strong>{html.escape(title)}</strong></div>
        <div class="top-actions">
          <span class="pill accent">local gate</span>
          <span class="pill">dashboard :{cfg.preview.dashboard_port}</span>
        </div>
      </header>
      <main>
        <section class="page">{content}</section>
      </main>
    </section>
  </div>
  <script id="preview-data" type="application/json">{json.dumps(payload).replace("</", "<\\/")}</script>
  <script src="/assets/dashboard.js"></script>
</body>
</html>
"""


def render_sidebar(active_page: str) -> str:
    """Render the recovered sidebar navigation."""

    nav = [
        ("previews", "/", "Agent Previews"),
        ("tickets", "/tickets/", "Tickets & Reviews"),
        ("exports", "/exports/", "Linear Export"),
        ("commands", "/commands/", "Fleet Commands"),
        ("settings", "/settings/", "Settings"),
    ]
    links = "\n".join(
        f'<a class="nav-btn {"is-active" if page == active_page else ""}" href="{href}">{label}</a>'
        for page, href, label in nav
    )
    return f"""<aside>
  <div>
    <div class="brand-kicker">AgentFleet</div>
    <h1>Preview Fleet</h1>
  </div>
  <p class="sidebar-copy">Local-only review for multi-agent worktrees across any project stack.</p>
  <div class="nav-list">{links}</div>
  <div class="stat-grid">
    <div class="stat"><div class="stat-label">Agents</div><div class="stat-value" data-count-total>0</div></div>
    <div class="stat"><div class="stat-label">Approved</div><div class="stat-value" data-count-approved>0</div></div>
  </div>
  <div class="legend">
    <div class="legend-row"><span class="dot"></span><span>Services run on configured localhost ports.</span></div>
    <div class="legend-row"><span class="dot warn"></span><span>Configure [[preview.services]] per project.</span></div>
  </div>
</aside>"""


def route_chips(routes: list[str]) -> str:
    """Render endpoint chips used by preview cards."""

    return "".join(
        f'<button class="route-chip" data-route-chip="{html.escape(route)}" type="button">{html.escape(route)}</button>'
        for route in routes
    )


def ensure_recovered_assets(dashboard_dir: Path) -> None:
    """Write dashboard assets for the recovered wall."""

    assets = dashboard_dir / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "dashboard.css").write_text(FALLBACK_DASHBOARD_CSS + EXTRA_DASHBOARD_CSS, encoding="utf-8")
    (assets / "dashboard.js").write_text(FALLBACK_DASHBOARD_JS + EXTRA_DASHBOARD_JS, encoding="utf-8")


FALLBACK_DASHBOARD_CSS = """
:root { --surface: #fff; --surface-2:#faf9f6; --ink: #161614; --accent: #5b8a72; --accent-ink:#3d6650; --accent-soft:#e8efe9; --line: rgba(22,22,20,.1); }
* { box-sizing: border-box; } body { margin:0; min-height:100vh; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color:var(--ink); background:linear-gradient(160deg,#2a3a5c,#c89a78); }
.shell { min-height:100vh; padding:14px; display:grid; grid-template-columns:236px minmax(0,1fr); gap:14px; }
aside,.main-panel,.card,.section-card { background:rgba(255,255,255,.9); border:1px solid var(--line); border-radius:16px; box-shadow:0 24px 80px rgba(0,0,0,.18); }
aside { padding:18px; } h1 { font-family:Georgia,serif; font-size:34px; line-height:.96; margin:0 0 12px; }
.nav-list,.button-row,.route-chips,.agent-links,.review-row,.route-row { display:flex; gap:8px; flex-wrap:wrap; }
.nav-btn,.pill,.side-btn,.mini-btn,.route-chip { border:1px solid var(--line); border-radius:999px; padding:7px 10px; background:#fff; color:var(--accent); text-decoration:none; font-weight:700; }
.is-active,.accent,.primary { background:var(--accent-soft); color:var(--accent-ink); }
.stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:18px 0; }
.stat,.meta-grid code,input,select,textarea { background:var(--surface-2); border:1px solid var(--line); border-radius:10px; padding:9px; }
header { display:flex; justify-content:space-between; padding:16px; border-bottom:1px solid var(--line); }
main { padding:16px; } .page-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:14px; }
.preview-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(520px,1fr)); gap:14px; }
.card { overflow:hidden; } .card .meta { padding:14px; display:grid; gap:10px; }
.title { display:flex; justify-content:space-between; gap:10px; }
.meta-grid { display:grid; grid-template-columns:max-content minmax(0,1fr); gap:7px; align-items:center; }
iframe { width:100%; height:420px; border:0; background:#fff; }
.label,.stat-label,.brand-kicker { color:#777; font-size:10px; text-transform:uppercase; letter-spacing:.12em; font-weight:800; }
"""


FALLBACK_DASHBOARD_JS = """
(() => {
  const data = JSON.parse(document.getElementById("preview-data").textContent);
  const previews = data.previews || [];
  const routes = data.routes || ["/"];
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const key = (name, label) => `preview-${name}:${label}`;
  const norm = (route) => { const r = String(route || "/").trim(); return !r || r === "/" ? "/" : r.startsWith("/") || /^https?:/.test(r) ? r : `/${r}`; };
  const url = (base, route) => /^https?:/.test(route) ? route : `${base}${route === "/" ? "" : route}`;
  const find = (label) => previews.find((p) => p.label === label);
  const syncStats = () => { const total = $("[data-count-total]"); if (total) total.textContent = previews.length; const approved = previews.filter((p) => localStorage.getItem(key("status", p.label)) === "approved").length; const node = $("[data-count-approved]"); if (node) node.textContent = approved; };
  const syncCard = (card) => { const p = find(card.dataset.previewLabel); if (!p) return; const route = norm(localStorage.getItem(key("route", p.label)) || "/"); const next = url(p.uiUrl, route); const frame = $("iframe", card); const link = $("[data-open-link]", card); const current = $("[data-current-url]", card); if (frame) frame.src = next; if (link) link.href = next; if (current) current.textContent = next; };
  $$("[data-preview-card]").forEach((card) => {
    const label = card.dataset.previewLabel;
    const input = $("[data-route-input]", card);
    const status = $("[data-status]", card);
    const notes = $("[data-notes]", card);
    if (input) input.value = localStorage.getItem(key("route", label)) || "/";
    if (status) status.value = localStorage.getItem(key("status", label)) || "reviewing";
    if (notes) notes.value = localStorage.getItem(key("notes", label)) || "";
    card.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-route-chip]");
      if (chip && input) { input.value = chip.dataset.routeChip; localStorage.setItem(key("route", label), norm(input.value)); syncCard(card); }
      if (event.target.matches("[data-apply-route]") && input) { localStorage.setItem(key("route", label), norm(input.value)); syncCard(card); }
      if (event.target.matches("[data-reset-route]") && input) { input.value = "/"; localStorage.setItem(key("route", label), "/"); syncCard(card); }
    });
    if (status) status.addEventListener("change", () => { localStorage.setItem(key("status", label), status.value); syncStats(); });
    if (notes) notes.addEventListener("input", () => localStorage.setItem(key("notes", label), notes.value));
    syncCard(card);
  });
  const list = $("#route-recommendations"); if (list) list.innerHTML = routes.map((r) => `<option value="${r}"></option>`).join("");
  syncStats();
})();
"""


EXTRA_DASHBOARD_CSS = """

body[data-page="previews"] main { padding: 12px; }
body[data-page="previews"] .page { width: 100%; max-width: none; margin: 0; }
body[data-page="previews"] .page-head { margin-bottom: 12px; align-items: flex-start; }
body[data-page="previews"] .page-title { font-size: 34px; }
body[data-page="previews"] .page-copy { margin-top: 8px; max-width: 780px; }
body[data-page="previews"] .preview-grid { gap: 10px; }
body[data-page="previews"] .card { border-color: rgba(22, 22, 20, 0.22); }
body[data-page="previews"] .card iframe {
  border-top: 1px solid rgba(22, 22, 20, 0.2);
  outline: 1px solid rgba(22, 22, 20, 0.12);
  outline-offset: -1px;
}
body[data-theme="dark"][data-page="previews"] .card { border-color: rgba(255, 255, 255, 0.2); }
body[data-theme="dark"][data-page="previews"] .card iframe {
  border-top-color: rgba(255, 255, 255, 0.18);
  outline-color: rgba(255, 255, 255, 0.14);
}
.grid-controls { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
.preview-grid[data-grid-mode="one"] { grid-template-columns: minmax(0, 1fr); }
.preview-grid[data-grid-mode="two"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.preview-grid[data-grid-mode="three"] { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.preview-grid[data-grid-mode="dense"] { grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }
.preview-grid[data-grid-mode="dense"] iframe { height: 300px; }
.grid-controls .is-active { background: var(--accent-soft); color: var(--accent-ink); border-color: rgba(61,102,80,.34); }
@media (max-width: 900px) {
  .preview-grid[data-grid-mode="two"],
  .preview-grid[data-grid-mode="three"] { grid-template-columns: minmax(0, 1fr); }
  .grid-controls { justify-content: flex-start; }
}
"""


EXTRA_DASHBOARD_JS = """

(() => {
  const grid = document.querySelector("[data-preview-grid]");
  const controls = Array.from(document.querySelectorAll("[data-grid-mode]"));
  if (!grid || !controls.length) return;
  const defaultVersion = "preview-grid-default-v2";
  if (!localStorage.getItem(defaultVersion)) {
    localStorage.setItem("preview-grid-mode", "two");
    localStorage.setItem(defaultVersion, "1");
  }
  const apply = (mode) => {
    const next = mode || localStorage.getItem("preview-grid-mode") || "two";
    grid.dataset.gridMode = next;
    controls.forEach((button) => button.classList.toggle("is-active", button.dataset.gridMode === next));
    localStorage.setItem("preview-grid-mode", next);
  };
  controls.forEach((button) => button.addEventListener("click", () => apply(button.dataset.gridMode)));
  apply();
})();
"""


def start_dashboard_server(root: Path, port: int) -> http.server.ThreadingHTTPServer:
    """Serve the generated dashboard in a background thread."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def print_summary(cfg: FleetConfig, previews: list[PreviewSlot]) -> None:
    """Print dashboard and slot URLs."""

    dashboard_url = f"http://localhost:{cfg.preview.dashboard_port}"
    print(f"\nDashboard -> {dashboard_url}")
    for preview in previews:
        service_summary = " | ".join(f"{service.name}: {service.url}" for service in preview.services)
        print(f"  {preview.slot.label}: {preview.ui_url}")
        if service_summary:
            print(f"    services: {service_summary}")
        print(f"    logs: {', '.join(str(service.log) for service in preview.services)}")
    webbrowser.open(dashboard_url)
    print("\nPress Ctrl+C to stop previews.")


def wait_forever(
    processes: list[subprocess.Popen[str]], server: http.server.ThreadingHTTPServer
) -> None:
    """Wait until interrupted or a child preview exits."""

    try:
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    raise SystemExit(f"Preview process exited early with code {proc.returncode}.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping preview fleet...")
    finally:
        server.shutdown()


def write_state(cfg: FleetConfig, previews: list[PreviewSlot], processes: list[subprocess.Popen[str]]) -> None:
    """Persist enough process state for ``status`` and ``stop``."""

    state = {
        "dashboard_port": cfg.preview.dashboard_port,
        "processes": [proc.pid for proc in processes],
        "previews": [
            {
                "label": preview.slot.label,
                "ui_url": preview.ui_url,
                "api_url": preview.api_url,
                "services": [
                    {
                        "name": service.name,
                        "url": service.url,
                        "log": str(service.log),
                    }
                    for service in preview.services
                ],
            }
            for preview in previews
        ],
    }
    state_path(cfg).write_text(json.dumps(state, indent=2), encoding="utf-8")


def state_path(cfg: FleetConfig) -> Path:
    """Return the preview state file path."""

    root = cfg.resolved_state_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / STATE_FILE


def clear_state(cfg: FleetConfig) -> None:
    """Remove stale preview process state."""

    path = state_path(cfg)
    if path.exists():
        path.unlink()


def stop_previews(cfg: FleetConfig) -> int:
    """Stop preview processes from the saved state file."""

    path = state_path(cfg)
    if not path.exists():
        print("No saved preview processes found.")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    for pid in data.get("processes", []):
        stop_process(int(pid))
    clear_state(cfg)
    print("Stopped preview processes.")
    return 0


def print_saved_preview_state(cfg: FleetConfig) -> None:
    """Print saved preview URLs and logs if a dashboard is running."""

    path = state_path(cfg)
    if not path.exists():
        print("\npreview: no saved preview processes")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"\npreview dashboard: http://localhost:{data.get('dashboard_port')}")
    for preview in data.get("previews", []):
        print(f"  {preview.get('label')}: {preview.get('ui_url')} | {preview.get('api_url')}")
        services = preview.get("services") or []
        if services:
            print(
                "    services: "
                + " | ".join(f"{service.get('name')}: {service.get('url')}" for service in services)
            )
            print("    logs: " + ", ".join(str(service.get("log")) for service in services))


def stop_process(pid: int) -> None:
    """Terminate a process if it is still alive."""

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        print(f"Could not stop pid {pid}: permission denied.")
