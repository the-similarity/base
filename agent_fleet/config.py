"""Configuration discovery and TOML parsing for ``agentfleet``."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .models import AgentSpec, FleetConfig, PreviewConfig, PreviewServiceConfig

CONFIG_NAME = "agentfleet.toml"
LEGACY_CONFIG_NAME = "agent-fleet.toml"


def find_repo_root(start: Path | None = None) -> Path:
    """Return the nearest parent containing ``.git``.

    The CLI is expected to run inside a git checkout. Failing closed here avoids
    creating worktrees relative to an arbitrary shell directory.
    """

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit("agentfleet must be run inside a git repository.")


def config_path(repo_root: Path) -> Path:
    """Return the repo-local configuration path."""

    preferred = repo_root / CONFIG_NAME
    legacy = repo_root / LEGACY_CONFIG_NAME
    if not preferred.exists() and legacy.exists():
        return legacy
    return preferred


def default_config(repo_root: Path) -> FleetConfig:
    """Return generic clone-and-run defaults for a repo-local agent fleet."""

    project_name = repo_root.name
    return FleetConfig(
        repo_root=repo_root,
        project_name=project_name,
        worktree_root=repo_root.parent,
        agents=(
            AgentSpec("codex", count=2, command="codex", branch_prefix="codex/task"),
            AgentSpec("claude", count=2, command="claude", branch_prefix="claude/task"),
        ),
        preview=PreviewConfig(),
    )


def load_config(repo_root: Path | None = None) -> FleetConfig:
    """Load ``agentfleet.toml`` or return defaults for the current repo."""

    root = repo_root or find_repo_root()
    path = config_path(root)
    if not path.exists():
        return default_config(root)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    fallback = default_config(root)

    project_name = str(data.get("project_name") or fallback.project_name)
    worktree_root = resolve_path(root, data.get("worktree_root"), fallback.worktree_root)
    state_root = resolve_path(root, data.get("state_root"), None)
    agents = tuple(parse_agents(data.get("agents", []))) or fallback.agents
    preview = parse_preview(data.get("preview", {}), fallback.preview)

    return FleetConfig(
        repo_root=root,
        project_name=project_name,
        worktree_root=worktree_root,
        base_ref=str(data.get("base_ref") or fallback.base_ref),
        agents=agents,
        preview=preview,
        state_root=state_root,
    )


def resolve_path(repo_root: Path, value: object, fallback: Path | None) -> Path | None:
    """Resolve a TOML path value relative to the repository root."""

    if value is None:
        return fallback
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (repo_root / path).resolve()


def parse_agents(rows: object) -> list[AgentSpec]:
    """Parse ``[[agents]]`` rows from TOML data."""

    if not isinstance(rows, list):
        raise SystemExit("agentfleet.toml: agents must be an array of tables.")

    specs: list[AgentSpec] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("agentfleet.toml: each agent entry must be a table.")
        kind = str(row.get("kind", "")).strip()
        if not kind:
            raise SystemExit("agentfleet.toml: each agent needs a kind.")
        count = int(row.get("count", 1))
        if count < 0:
            raise SystemExit(f"agentfleet.toml: {kind} count must be non-negative.")
        specs.append(
            AgentSpec(
                kind=kind,
                count=count,
                command=str(row.get("command") or kind),
                branch_prefix=str(row.get("branch_prefix") or f"{kind}/task"),
            )
        )
    return specs


def parse_preview(row: object, fallback: PreviewConfig) -> PreviewConfig:
    """Parse the optional ``[preview]`` table."""

    if not row:
        return fallback
    if not isinstance(row, dict):
        raise SystemExit("agentfleet.toml: preview must be a table.")
    services = parse_preview_services(row.get("services", []))
    return PreviewConfig(
        dashboard_port=int(row.get("dashboard_port", fallback.dashboard_port)),
        api_base_port=int(row.get("api_base_port", fallback.api_base_port)),
        ui_base_port=int(row.get("ui_base_port", fallback.ui_base_port)),
        api_dir=str_or_fallback(row.get("api_dir"), fallback.api_dir),
        ui_dir=str_or_fallback(row.get("ui_dir"), fallback.ui_dir),
        api_command=str_or_fallback(row.get("api_command"), fallback.api_command),
        ui_command=str_or_fallback(row.get("ui_command"), fallback.ui_command),
        ui_api_env_var=str_or_fallback(row.get("ui_api_env_var"), fallback.ui_api_env_var),
        data_dir=str_or_fallback(row.get("data_dir"), fallback.data_dir),
        install_command=str_or_fallback(row.get("install_command"), fallback.install_command),
        install_if_missing=str_or_fallback(row.get("install_if_missing"), fallback.install_if_missing),
        services=tuple(services),
    )


def parse_preview_services(rows: object) -> list[PreviewServiceConfig]:
    """Parse ``[[preview.services]]`` rows from TOML data."""

    if rows in (None, ""):
        return []
    if not isinstance(rows, list):
        raise SystemExit("agentfleet.toml: preview.services must be an array of tables.")

    services: list[PreviewServiceConfig] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise SystemExit("agentfleet.toml: each preview service must be a table.")
        name = str(row.get("name") or "").strip()
        if not name:
            raise SystemExit("agentfleet.toml: each preview service needs a name.")
        command = str(row.get("command") or "").strip()
        if not command:
            raise SystemExit(f"agentfleet.toml: preview service {name} needs a command.")
        env = row.get("env", {})
        if not isinstance(env, dict):
            raise SystemExit(f"agentfleet.toml: preview service {name} env must be a table.")
        services.append(
            PreviewServiceConfig(
                name=name,
                port_base=int(row.get("port_base", 3000 + (index - 1) * 1000)),
                directory=str(row.get("dir") or row.get("directory") or "."),
                command=command,
                env={str(key): str(value) for key, value in env.items()},
                install_command=str(row.get("install_command") or ""),
                install_if_missing=str(row.get("install_if_missing") or ""),
                primary=bool(row.get("primary", False)),
            )
        )
    return services


def str_or_fallback(value: object, fallback: str) -> str:
    """Return non-empty TOML strings while preserving default preview templates."""

    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def write_default_config(repo_root: Path, force: bool = False) -> Path:
    """Write a starter ``agentfleet.toml`` for the current repository."""

    path = config_path(repo_root)
    if path.exists() and not force:
        raise SystemExit(f"Refusing to overwrite {path}. Pass --force to replace it.")
    cfg = default_config(repo_root)
    path.write_text(render_config(cfg), encoding="utf-8")
    return path


def render_config(cfg: FleetConfig) -> str:
    """Render a minimal TOML config without requiring a TOML writer dependency."""

    lines = [
        f'project_name = "{cfg.project_name}"',
        f'worktree_root = "{cfg.worktree_root}"',
        f'base_ref = "{cfg.base_ref}"',
        "",
    ]
    for agent in cfg.agents:
        branch_prefix = agent.branch_prefix or f"{agent.kind}/task"
        lines.extend(
            [
                "[[agents]]",
                f'kind = "{agent.kind}"',
                f"count = {agent.count}",
                f'command = "{agent.command_name()}"',
                f'branch_prefix = "{branch_prefix}"',
                "",
            ]
        )

    preview = cfg.preview
    lines.extend(
        [
            "[preview]",
            f"dashboard_port = {preview.dashboard_port}",
            "# Add one or more [[preview.services]] blocks for your app.",
            "# Example:",
            "# [[preview.services]]",
            '# name = "web"',
            '# dir = "app"',
            "# port_base = 3000",
            '# command = "npm run dev -- --port {port}"',
            "# primary = true",
            "",
        ]
    )
    return "\n".join(lines)


def _escape(value: str) -> str:
    """Escape double-quoted TOML string content."""

    return value.replace("\\", "\\\\").replace('"', '\\"')
