"""Preview dashboard and process lifecycle for worktree fleets."""

from __future__ import annotations

import html
import http.server
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from .commands import run
from .handoff_prompt import INIT_AI_AGENT_PROMPT, print_prompt_box
from .models import AgentSlot, FleetConfig, PreviewConfig, PreviewServiceConfig, PreviewSlot, RuntimePreviewService

STATE_FILE = "preview-processes.json"

# Paths offered in datalist + route quick-picker (ordering is UX preference).
ALL_ROUTE_SUGGESTIONS = [
    "/",
    "/dashboard",
    "/login",
    "/admin",
    "/settings",
    "/health",
    "/docs",
    "/api/health",
]

# First-row chips target the SPA preview iframe (`ui_url`): product surfaces only.
PREVIEW_ROUTE_CHIPS = ["/dashboard", "/login", "/admin", "/settings"]

# Second row opens backend origin (`api_url`): OpenAPI/OpenAPI-health style probes only.
BACKEND_ROUTE_CHIPS = ["/", "/health", "/docs", "/api/health"]

# Skip heavy or irrelevant dirs when scanning one level for nested ``.venv``/``venv``.
PREVIEW_CHILD_SCAN_SKIP = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        ".git",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        "__pycache__",
        ".tox",
    }
)


def start_preview(cfg: FleetConfig, slots: list[AgentSlot], install_deps: bool = True) -> int:
    """Start configured preview services and serve the dashboard until interrupted."""

    if not cfg.preview.configured:
        print(
            "Preview is not configured: add [[preview.services]] in agentfleet.toml (repo root)."
        )
        print()
        print("Give this checklist to your AI agent:")
        print()
        print_prompt_box(INIT_AI_AGENT_PROMPT)
        return 1

    preview_slots = build_preview_slots(cfg, slots)
    if not preview_slots:
        print("No previewable worktrees found for the configured preview service dirs.")
        return 1

    validate_ports(cfg, preview_slots)
    state_root = cfg.resolved_state_root()
    state_root.mkdir(parents=True, exist_ok=True)

    tracked: list[tuple[subprocess.Popen[str], str]] = []
    try:
        for preview in preview_slots:
            tracked.extend(start_preview_processes(cfg, preview, install_deps))
        processes = [proc for proc, _ in tracked]
        write_state(cfg, preview_slots, processes)
        dashboard_path = write_dashboard(cfg, preview_slots)
        server = start_dashboard_server(dashboard_path.parent, cfg.preview.dashboard_port)
        print_summary(cfg, preview_slots)
        wait_forever(tracked, server)
    finally:
        for proc, _ in tracked:
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


def _venv_exe_dir_name() -> str:
    """Return ``bin`` / ``Scripts`` for virtual environments on this OS."""

    return "Scripts" if os.name == "nt" else "bin"


def _venv_script_dirs_under(base: Path) -> list[Path]:
    """Return sibling ``.venv/<bin>`` and ``venv/<bin>`` when present."""

    leaf = Path(_venv_exe_dir_name())
    found: list[Path] = []
    for stem in (".venv", "venv"):
        cand = (base / stem / leaf).resolve()
        if cand.is_dir():
            found.append(cand)
    return found


def _pyproject_declares_poetry(repo_root: Path) -> bool:
    path = repo_root / "pyproject.toml"
    if not path.is_file():
        return False
    try:
        head = path.read_text(encoding="utf-8")[:24000]
    except OSError:
        return False
    return "[tool.poetry]" in head


def _poetry_venv_exe_dir(repo_root: Path) -> Path | None:
    """Resolve ``poetry env info -p``/``bin`` when Poetry manages the env at repo root."""

    if shutil.which("poetry") is None:
        return None
    if not _pyproject_declares_poetry(repo_root):
        return None
    rr = repo_root.resolve()
    try:
        completed = subprocess.run(
            ["poetry", "env", "info", "-p"],
            cwd=rr,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or "").strip()
    if not text:
        return None
    venv_home = Path(text.splitlines()[0].strip())
    exe_dir = venv_home / _venv_exe_dir_name()
    return exe_dir.resolve() if exe_dir.is_dir() else None


def _child_subproject_venv_dirs(root: Path, *, max_dirs: int) -> list[Path]:
    """Find ``<subdir>/.venv/(bin|Scripts)`` for immediate children only."""

    accumulated: list[Path] = []
    try:
        names = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return accumulated
    n = 0
    for child in names:
        if child.name.startswith(".") or child.name in PREVIEW_CHILD_SCAN_SKIP:
            continue
        accumulated.extend(_venv_script_dirs_under(child.resolve()))
        n += 1
        if n >= max_dirs:
            break
    return accumulated


def discover_preview_path_prefixes(
    repo_root: Path, worktree: Path, configured_prepend: tuple[str, ...]
) -> list[str]:
    """Build ordered PATH prefixes so ``python``/``pip`` resolve to project envs anywhere.

    Order:
    1. Optional ``[preview] path_prepend`` entries (supports ``{repo_root}``, ``{worktree}``).
    2. ``repo_root`` ``.venv`` / ``venv`` script dirs.
    3. Poetry-managed venv scripts for Poetry ``pyproject`` at repo root (if ``poetry`` is on PATH).
    4. Same for ``worktree`` (agents often duplicate layout).
    5. Nested envs inside one subdirectory under ``repo_root`` and ``worktree`` (e.g. ``backend/.venv``).

    Dedup preserves first-seen precedence.
    """

    rr = repo_root.resolve()
    wt = worktree.resolve()
    ordered: list[str] = []
    seen: set[str] = set()

    def push(path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            return
        if key not in seen and path.is_dir():
            seen.add(key)
            ordered.append(key)

    for tmpl in configured_prepend:
        try:
            rendered = tmpl.format(repo_root=str(rr), worktree=str(wt)).strip()
        except KeyError as exc:
            raise SystemExit(
                f"agentfleet.toml: preview.path_prepend has unknown {{{exc.args[0]}}} "
                '(only "repo_root" and "worktree" are expanded).'
            ) from exc
        if rendered:
            push(Path(rendered).expanduser())

    for exe in _venv_script_dirs_under(rr):
        push(exe)

    poetry_exe = _poetry_venv_exe_dir(rr)
    if poetry_exe is not None:
        push(poetry_exe)

    for exe in _venv_script_dirs_under(wt):
        push(exe)

    for exe in _child_subproject_venv_dirs(rr, max_dirs=48):
        push(exe)

    for exe in _child_subproject_venv_dirs(wt, max_dirs=48):
        push(exe)

    return ordered


def start_preview_processes(
    cfg: FleetConfig, preview: PreviewSlot, install_deps: bool
) -> list[tuple[subprocess.Popen[str], str]]:
    """Start the configured service commands for one preview slot.

    Each item is ``(process, summary)`` where ``summary`` identifies the slot,
    service, and argv used for clearer errors when the child exits (e.g. 127).
    """

    path_prefixes = discover_preview_path_prefixes(
        cfg.repo_root,
        preview.slot.path,
        cfg.preview.path_prepend,
    )

    launched: list[tuple[subprocess.Popen[str], str]] = []
    for service in preview.services:
        service.log.parent.mkdir(parents=True, exist_ok=True)
        if install_deps and service.install_if_missing and service.install_command:
            missing = service.directory / service.install_if_missing
            if not missing.exists():
                print(f"[{preview.slot.label}:{service.name}] installing dependencies...")
                run(
                    split_command(
                        render_service_template(
                            service.install_command, preview, service, repo_root=cfg.repo_root
                        )
                    ),
                    cwd=service.directory,
                )

        env = os.environ.copy()
        if path_prefixes:
            sep = os.pathsep
            env["PATH"] = sep.join((*path_prefixes, env.get("PATH", "")))
        env["PYTHONPATH"] = str(preview.slot.path)
        for key, value in service.env.items():
            env[key] = render_service_template(value, preview, service, repo_root=cfg.repo_root)

        argv = split_command(
            render_service_template(service.command, preview, service, repo_root=cfg.repo_root)
        )
        cmd_repr = shlex.join(argv)
        summary = f"{preview.slot.label}:{service.name}: {cmd_repr}"

        log_handle = service.log.open("w", encoding="utf-8")
        launched.append(
            (
                subprocess.Popen(
                    argv,
                    cwd=service.directory,
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                ),
                summary,
            )
        )
    return launched


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


def render_service_template(
    template: str,
    preview: PreviewSlot,
    service: RuntimePreviewService,
    *,
    repo_root: Path | None = None,
) -> str:
    """Render a service command or env template.

    Optional ``{repo_root}`` is filled with the git repository root (absolute path) when
    ``repo_root=`` is passed and the placeholder appears in ``template`` — use it for
    ``PYTHONPATH``/data dirs. Preview also prepends typical virtualenv ``bin`` dirs
    (``.venv``, Poetry, nested packages) when found so ``python``/``npm`` resolve like in a dev shell.
    """

    mapping: dict[str, object] = {
        "api_port": preview.api_port,
        "ui_port": preview.ui_port,
        "api_url": preview.api_url,
        "ui_url": preview.ui_url,
        "port": service.port,
        "service_port": service.port,
        "service_url": service.url,
        "service_name": service.name,
        "worktree": preview.slot.path,
    }
    if repo_root is not None and "{repo_root}" in template:
        mapping["repo_root"] = str(repo_root.resolve())
    return template.format(**mapping)


def split_command(command: str) -> list[str]:
    """Split a shell-like command template into argv."""

    return shlex.split(command)


def _ensure_dashboard_log_symlink(dashboard_dir: Path, log_dir: Path) -> None:
    """Expose ``state_root/logs`` as ``/log_files/…`` URLs for the static file server."""

    link = dashboard_dir / "log_files"
    try:
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.exists() and not link.is_symlink():
            return
    except OSError:
        return
    if link.exists():
        return
    try:
        rel = os.path.relpath(log_dir.resolve(), dashboard_dir.resolve())
        link.symlink_to(rel, target_is_directory=True)
    except OSError:
        # Windows without dev mode symlink privilege, etc.
        pass


def _render_logs_page_body(payload: dict[str, object]) -> str:
    """HTML for ``/logs/``: anchored groups with links into ``/log_files/<basename>.log``."""

    previews = payload.get("previews") or []
    chunks: list[str] = []
    for entry in previews:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label") or ""
        slot = entry.get("slot") or 0
        anchor = f"log-slot-{slot}"
        chunks.append(f'<section class="log-group" id="{html.escape(anchor)}">')
        chunks.append(f'<h3 class="panel-title">{html.escape(str(label))}</h3>')
        chunks.append('<ul class="log-link-list">')
        for svc in entry.get("services") or []:
            if not isinstance(svc, dict):
                continue
            name = html.escape(str(svc.get("name") or "service"))
            log_path = str(svc.get("log") or "")
            basename = Path(log_path).name
            if not basename:
                chunks.append(f"<li><span>No log path for {name}</span></li>")
                continue
            href = f"/log_files/{html.escape(basename)}"
            chunks.append(
                f'<li><a class="pill" href="{href}" target="_blank" rel="noreferrer">Open {name} log</a></li>'
            )
        chunks.append("</ul></section>")
    if not chunks:
        chunks.append('<p class="page-copy">No preview services yet.</p>')
    return "\n".join(chunks)


def write_dashboard(cfg: FleetConfig, previews: list[PreviewSlot]) -> Path:
    """Write the recovered multi-page preview fleet dashboard."""

    dashboard_dir = cfg.resolved_state_root() / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    log_dir = cfg.resolved_state_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _ensure_dashboard_log_symlink(dashboard_dir, log_dir)
    ensure_recovered_assets(dashboard_dir)
    payload = preview_payload(cfg, previews)
    dashboard_path = dashboard_dir / "index.html"
    dashboard_path.write_text(render_preview_page(cfg, previews, payload), encoding="utf-8")
    write_secondary_pages(cfg, dashboard_dir, payload)
    return dashboard_path


def render_card(preview: PreviewSlot, slot_index: int) -> str:
    """Render one recovered preview card."""

    slot = preview.slot
    service_links = "".join(
        f'<a class="pill {"accent" if service.primary else ""}" href="{service.url}" target="_blank" rel="noreferrer">'
        f'{html.escape(service.name)}:{service.port}</a>'
        for service in preview.services
    )
    dl_id = f"route-dl-{slot_index}"
    log_anchor = f"/logs/#log-slot-{slot_index}"
    quick = route_quick_select_html(ALL_ROUTE_SUGGESTIONS)
    dl = route_datalist_html(dl_id, ALL_ROUTE_SUGGESTIONS)
    prev_chips = route_chips_html(PREVIEW_ROUTE_CHIPS)
    api_chips = api_route_chips_html(preview, BACKEND_ROUTE_CHIPS)
    return f"""<article class="card" id="{html.escape(slot.label)}" data-preview-card data-preview-label="{html.escape(slot.label)}">
  <div class="meta">
    <div class="title">
      <strong>{html.escape(slot.label)}</strong>
      <div class="agent-links">
        <a class="pill accent" data-open-link href="{preview.ui_url}" target="_blank" rel="noreferrer">open preview</a>
        <a class="pill" href="{html.escape(log_anchor)}">logs</a>
        {service_links}
      </div>
    </div>
    <div class="route-control">
      <div class="route-row">
        <div class="label">Preview path</div>
        <div class="route-input-wrap">{quick}<input class="route-input" data-route-input list="{html.escape(dl_id)}" value="/" placeholder="/dashboard" autocomplete="off" spellcheck="false" aria-label="{html.escape(slot.label)} preview path"></div>
        <button class="mini-btn primary" data-apply-route type="button">Apply</button>
        <button class="mini-btn" data-reset-route type="button">Reset</button>
      </div>
      <div class="route-sub">
        <div class="label">Preview</div>
        <div class="route-chips">{prev_chips}</div>
      </div>
      <div class="route-sub">
        <div class="label">Backend API</div>
        <div class="route-chips">{api_chips}</div>
      </div>
      <div class="current-url mono-trace" data-current-url>{preview.ui_url}</div>
      {dl}
    </div>
    <!-- Review UI disabled: use Tickets page when re-enabled.
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
    -->
    <div class="meta-grid">
      <div class="label">Branch</div><code>{html.escape(slot.branch)}</code>
      <div class="label">Worktree</div><code>{html.escape(str(slot.path))}</code>
    </div>
  </div>
  <iframe src="{preview.ui_url}" loading="lazy"></iframe>
</article>"""


def preview_payload(cfg: FleetConfig, previews: list[PreviewSlot]) -> dict[str, object]:
    """Return JSON data consumed by the recovered dashboard JavaScript."""

    return {
        "dashboardPort": cfg.preview.dashboard_port,
        "routes": ALL_ROUTE_SUGGESTIONS,
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

    cards = "\n".join(render_card(preview, i) for i, preview in enumerate(previews, start=1))
    content = f"""
          <div class="page-head">
            <div>
              <h2 class="page-title">Agent Previews</h2>
              <p class="page-copy">Open each worktree on its own localhost port. Service logs live on <a href="/logs/">Logs</a>. Commands and settings have their own pages.</p>
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
"""
    return render_shell(cfg, "previews", "Agent Previews", content, payload)


def write_secondary_pages(cfg: FleetConfig, dashboard_dir: Path, payload: dict[str, object]) -> None:
    """Restore dashboard subpages, excluding hidden/dead pages."""

    for stale_page in ("endpoints", "symphony"):
        stale_dir = dashboard_dir / stale_page
        if stale_dir.exists():
            shutil.rmtree(stale_dir)

    # Review-focused pages — re-enable when the review UI ships again:
    # "tickets": ("Tickets & Reviews", '<div class="review-board" data-review-board></div>', "..."),
    # "exports": ("Linear Export", '<div class="section-card">...</div>', "..."),

    pages = {
        "logs": (
            "Service logs",
            _render_logs_page_body(payload),
            "Stdout/stderr for each preview service opens as raw ``.log`` files (same files on disk under your state ``logs`` directory).",
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
        ("logs", "/logs/", "Logs"),
        # ("tickets", "/tickets/", "Tickets & Reviews"),
        # ("exports", "/exports/", "Linear Export"),
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
  <p class="sidebar-copy">Local-only multi-agent worktrees across any project stack.</p>
  <div class="nav-list">{links}</div>
  <div class="stat-grid">
    <div class="stat"><div class="stat-label">Agents</div><div class="stat-value" data-count-total>0</div></div>
    <!-- Review stat disabled with review UI:
    <div class="stat"><div class="stat-label">Approved</div><div class="stat-value" data-count-approved>0</div></div>
    -->
  </div>
  <div class="legend">
    <div class="legend-row"><span class="dot"></span><span>Services run on configured localhost ports.</span></div>
    <div class="legend-row"><span class="dot warn"></span><span>Configure [[preview.services]] per project.</span></div>
  </div>
</aside>"""


def route_chips_html(routes: list[str]) -> str:
    """Render clickable chips for SPA preview iframe routes (same origin as iframe)."""

    return "".join(
        f'<button class="route-chip" data-route-chip="{html.escape(route)}" type="button">{html.escape(route)}</button>'
        for route in routes
    )


def route_datalist_html(list_id: str, routes: list[str]) -> str:
    """Return a ``<datalist>`` for ``<input list=…>`` (server-rendered avoids JS timing flakes)."""

    opts = "".join(f'<option value="{html.escape(r)}"></option>' for r in routes)
    return f'<datalist id="{html.escape(list_id)}">{opts}</datalist>'


def route_quick_select_html(routes: list[str]) -> str:
    """Shallow picker; datalists rarely open suggestions on focus alone."""

    opts = '<option value="">Paths…</option>'
    opts += "".join(f'<option value="{html.escape(r)}">{html.escape(r)}</option>' for r in routes)
    return (
        f'<select class="route-quick" data-route-quick aria-label="Suggested path">{opts}</select>'
    )


def api_route_chips_html(preview: PreviewSlot, routes_list: list[str]) -> str:
    """Chip row that opens backend origin URLs in a new tab (does not steer the iframe)."""

    base = preview.api_url.rstrip("/")
    return "".join(
        f'<button type="button" class="route-chip route-chip-api" data-api-route-chip '
        f'data-api-base="{html.escape(base)}" data-api-route="{html.escape(route)}">'
        f"{html.escape(route)}</button>"
        for route in routes_list
    )


def route_chips(routes: list[str]) -> str:
    """Render endpoint chips used by preview cards."""

    return route_chips_html(routes)


def ensure_recovered_assets(dashboard_dir: Path) -> None:
    """Write dashboard assets for the recovered wall."""

    assets = dashboard_dir / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "dashboard.css").write_text(FALLBACK_DASHBOARD_CSS + EXTRA_DASHBOARD_CSS, encoding="utf-8")
    (assets / "dashboard.js").write_text(FALLBACK_DASHBOARD_JS + EXTRA_DASHBOARD_JS, encoding="utf-8")


FALLBACK_DASHBOARD_CSS = """
:root {
  --surface: #faf9f6;
  --surface-2: #ffffff;
  --ink: #161614;
  --ink-3: #7a7a75;
  --accent: #5b8a72;
  --accent-ink: #3d6650;
  --accent-soft: #e8efe9;
  --line: rgba(22,22,20,.09);
  --line-strong: rgba(22,22,20,.14);
  --shadow-card: 0 1px 0 rgba(20,20,20,0.03), 0 8px 28px -14px rgba(20,20,20,0.12);
  --shadow-shell: 0 16px 56px -20px rgba(12,18,14,0.35);
  --radius-lg: 14px;
}
* { box-sizing: border-box; }
html { height: 100%; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
  color: var(--ink);
  background: #1a1e24;
  font-size: 14px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
/* Cadence / Lumen lineage: painterly wash with sage + paper (see design_guideline/cadence). */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    linear-gradient(160deg, #4a7a5a 0%, #6b9a72 22%, #c4b896 52%, #a88060 78%, #3d2f1f 100%);
  opacity: 1;
}
body::after {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 70% 55% at 25% 35%, rgba(120,160,140,0.45), transparent 58%),
    radial-gradient(ellipse 60% 48% at 78% 72%, rgba(200,160,120,0.4), transparent 55%),
    radial-gradient(ellipse 50% 42% at 50% 92%, rgba(40,30,20,0.28), transparent 60%);
  mix-blend-mode: soft-light;
}
.shell { position: relative; z-index: 1; min-height: 100vh; padding: 16px; display: grid; grid-template-columns: 244px minmax(0, 1fr); gap: 14px; }
aside, .main-panel, .card, .section-card {
  background: rgba(255,255,255,.92);
  backdrop-filter: blur(10px);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-shell);
}
aside { padding: 20px 18px; }
aside h1 {
  font-family: Georgia, 'Iowan Old Style', 'Apple Garamond', serif;
  font-size: 32px;
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0 0 10px;
}
.brand-kicker { color: var(--accent); font-size: 10px; text-transform: uppercase; letter-spacing: 0.16em; font-weight: 800; }
.sidebar-copy { margin: 0 0 14px; color: var(--ink-3); font-size: 12px; line-height: 1.5; }
.nav-list { display: flex; flex-direction: column; gap: 4px; }
aside .nav-btn {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 10px 12px;
  background: transparent;
  color: var(--ink);
  font-weight: 650;
  font-size: 13px;
  text-decoration: none;
  transition: background 0.12s ease, border-color 0.12s ease;
}
aside .nav-btn:hover { background: rgba(91,138,114,0.08); color: var(--accent-ink); }
aside .nav-btn.is-active {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: rgba(91,138,114,0.28);
}
.stat-grid { display: grid; grid-template-columns: 1fr; gap: 8px; margin: 18px 0; }
.stat {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}
.stat-value { font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 750; color: var(--accent-ink); }
.stat-label { color: var(--ink-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 800; }
.legend { margin-top: 8px; font-size: 11px; color: var(--ink-3); line-height: 1.45; }
.legend-row { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 8px; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; background: var(--accent); }
.dot.warn { background: #c89a4a; }
.button-row, .agent-links, .review-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.pill, .side-btn, .mini-btn, .route-chip {
  font-family: inherit;
  cursor: pointer;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 7px 12px;
  background: var(--surface-2);
  color: var(--accent-ink);
  text-decoration: none;
  font-weight: 650;
  font-size: 12.5px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.65) inset;
}
.is-active, .accent, .primary { background: var(--accent-soft); color: var(--accent-ink); border-color: rgba(61,102,80,0.25); }
.mini-btn.primary { font-weight: 700; }
.stat, .meta-grid code, input, select, textarea {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 9px 11px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: rgba(255,255,255,0.65);
}
header .top-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.crumbs { font-size: 12px; color: var(--ink-3); }
.crumbs strong { color: var(--ink); font-weight: 700; }
main { padding: 16px 18px 20px; }
.page-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; margin-bottom: 14px; flex-wrap: wrap; }
.page-title { font-family: Georgia, serif; font-size: 30px; margin: 0 0 6px; letter-spacing: -0.02em; }
.page-copy { margin: 0; max-width: 720px; font-size: 13.5px; color: var(--ink-3); line-height: 1.55; }
.page-copy a { color: var(--accent-ink); font-weight: 650; }
.preview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 14px; }
.card { overflow: hidden; border-radius: var(--radius-lg); box-shadow: var(--shadow-card); }
.card .meta { padding: 16px; display: grid; gap: 11px; background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(250,249,246,0.95)); }
.title { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.title strong { font-size: 17px; letter-spacing: -0.02em; }
.route-control { display: flex; flex-direction: column; gap: 10px; }
.route-row {
  display: grid;
  grid-template-columns: 96px minmax(140px, 1fr) auto auto;
  gap: 8px 10px;
  align-items: center;
}
.route-input-wrap { flex: 1 1 200px; display: flex; gap: 8px; align-items: stretch; min-width: 0; }
.route-quick {
  flex: 0 0 auto;
  width: 132px;
  max-width: 40%;
  padding: 9px 10px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--ink-3);
  cursor: pointer;
}
.route-input { flex: 1 1 160px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12.5px; }
.route-input:focus-visible, .route-quick:focus-visible { outline: 2px solid rgba(91,138,114,0.45); outline-offset: 1px; }
.route-sub { display: grid; grid-template-columns: 88px 1fr; gap: 10px; align-items: start; }
.route-sub .label { padding-top: 3px; }
.route-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.route-chip { font-size: 12px; padding: 6px 11px; border-radius: 999px; box-shadow: none; }
.route-chip-api { background: #f3f6f4; border-color: rgba(61,102,80,0.2); color: #2d4a3a; }
.current-url {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  word-break: break-all;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px dashed var(--line);
  border-radius: 10px;
  color: #3d3d38;
}
.mono-trace { line-height: 1.4; }
.meta-grid { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 7px 14px; align-items: center; }
.meta-grid code { font-size: 11.5px; }
iframe { width: 100%; height: 420px; border: 0; background: #fff; }
.label, .brand-kicker {
  color: var(--ink-3);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 800;
}
.section-card { padding: 16px; margin-bottom: 14px; }
.command-list { margin-bottom: 14px; }
"""


FALLBACK_DASHBOARD_JS = """
(() => {
  const data = JSON.parse(document.getElementById("preview-data").textContent);
  const previews = data.previews || [];
  const routes = data.routes || ["/"];
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const key = (name, label) => `preview-${name}:${label}`;
  const escapeAttr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const norm = (route) => { const r = String(route || "/").trim(); return !r || r === "/" ? "/" : r.startsWith("/") || /^https?:/.test(r) ? r : `/${r}`; };
  const url = (base, route) => /^https?:/.test(route) ? route : `${base}${route === "/" ? "" : route}`;
  const find = (label) => previews.find((p) => p.label === label);
  const syncStats = () => { const total = $("[data-count-total]"); if (total) total.textContent = previews.length; };
  const syncCard = (card) => { const p = find(card.dataset.previewLabel); if (!p) return; const route = norm(localStorage.getItem(key("route", p.label)) || "/"); const next = url(p.uiUrl, route); const frame = $("iframe", card); const link = $("[data-open-link]", card); const current = $("[data-current-url]", card); if (frame) frame.src = next; if (link) link.href = next; if (current) current.textContent = next; };
  $$("[data-preview-card]").forEach((card) => {
    const label = card.dataset.previewLabel;
    const input = $("[data-route-input]", card);
    const quick = $("[data-route-quick]", card);
    // Review dashboard (status/notes) commented out — restore when Tickets UI returns.
    if (input) input.value = localStorage.getItem(key("route", label)) || "/";
    if (quick) {
      quick.addEventListener("change", () => {
        const v = quick.value;
        if (!v || !input) return;
        input.value = v;
        localStorage.setItem(key("route", label), norm(v));
        syncCard(card);
        quick.selectedIndex = 0;
      });
    }
    card.addEventListener("click", (event) => {
      const apiChip = event.target.closest("[data-api-route-chip]");
      if (apiChip) {
        let base = String(apiChip.dataset.apiBase || "").trim();
        while (base.endsWith("/")) base = base.slice(0, -1);
        let path = String(apiChip.dataset.apiRoute || "/");
        if (!path.startsWith("/")) path = `/${path}`;
        window.open(base + path, "_blank", "noopener,noreferrer");
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      const chip = event.target.closest("[data-route-chip]");
      if (chip && input) { input.value = chip.dataset.routeChip; localStorage.setItem(key("route", label), norm(input.value)); syncCard(card); }
      if (event.target.matches("[data-apply-route]") && input) { localStorage.setItem(key("route", label), norm(input.value)); syncCard(card); }
      if (event.target.matches("[data-reset-route]") && input) { input.value = "/"; localStorage.setItem(key("route", label), "/"); syncCard(card); }
    });
    syncCard(card);
  });
  const list = $("#route-recommendations");
  if (list) list.innerHTML = routes.map((r) => `<option value="${escapeAttr(r)}"></option>`).join("");
  syncStats();
})();
"""


EXTRA_DASHBOARD_CSS = """

.log-link-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.log-group { margin-bottom: 20px; }
body[data-page="logs"] .log-group:last-child { margin-bottom: 0; }

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
    print(f"  Logs page -> {dashboard_url}/logs/")
    for preview in previews:
        service_summary = " | ".join(f"{service.name}: {service.url}" for service in preview.services)
        print(f"  {preview.slot.label}: {preview.ui_url}")
        if service_summary:
            print(f"    services: {service_summary}")
    webbrowser.open(dashboard_url)
    print("\nPress Ctrl+C to stop previews.")


def wait_forever(
    tracked: list[tuple[subprocess.Popen[str], str]],
    server: http.server.ThreadingHTTPServer,
) -> None:
    """Wait until interrupted or a child preview exits."""

    try:
        while True:
            for proc, summary in tracked:
                if proc.poll() is not None:
                    rc = proc.returncode
                    hint = ""
                    if rc == 127:
                        hint = (
                            "\nExit 127: a program on PATH was not found. "
                            "If the failure is ``npm``/``python`` itself, add that binary's directory to "
                            "``[preview] path_prepend`` (from ``which npm`` / ``which python``). "
                            "If the command is ``npm run ...`` but the log shows ``next``/``vite``: command not found, "
                            "Node deps are missing in that **worktree's** service directory — run ``npm install`` there, "
                            "or set ``install_command`` + ``install_if_missing`` on that ``[[preview.services]]`` block. "
                            "See the Logs page or state ``logs/*.log`` for the exact line."
                        )
                    elif rc not in (0, None):
                        hint = (
                            "\nStderr was merged into the service *.log files (Logs page / state logs dir). "
                            "(often missing deps or wrong interpreter: fix your env, "
                            "or set ``preview.path_prepend`` in agentfleet.toml to the ``bin`` directory you use locally)."
                        )
                    raise SystemExit(
                        f"Preview process exited early with code {rc}.{hint}\n  {summary}"
                    )
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


def stop_process(pid: int) -> None:
    """Terminate a process if it is still alive."""

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        print(f"Could not stop pid {pid}: permission denied.")
