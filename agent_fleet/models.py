"""Core data contracts for the agent fleet CLI.

The package is intentionally stdlib-only so a freshly cloned repository can run
the cockpit without a dependency bootstrap step. These dataclasses are immutable
where possible; commands that mutate git state receive explicit ``Path`` values
from the parsed configuration instead of consulting global process state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class AgentSpec:
    """Configured family of homogeneous agent slots."""

    kind: str
    count: int = 1
    command: str | None = None
    branch_prefix: str | None = None

    def command_name(self) -> str:
        """Return the executable to launch for this agent family."""

        return self.command or self.kind

    def branch_name(self, index: int) -> str:
        """Return the branch name for a one-indexed slot."""

        prefix = self.branch_prefix or f"{self.kind}/task"
        return f"{prefix}-{index}"


@dataclass(frozen=True)
class PreviewServiceConfig:
    """One runnable service in a worktree preview stack."""

    name: str
    port_base: int
    directory: str = "."
    command: str = ""
    env: dict[str, str] = field(default_factory=dict)
    install_command: str = ""
    install_if_missing: str = ""
    primary: bool = False


@dataclass(frozen=True)
class PreviewConfig:
    """Optional preview command templates for a repository.

    New projects should prefer ``services`` because it supports frontend-only,
    API-only, mobile companion servers, Docker Compose stacks, and arbitrary
    multi-service apps. The legacy API/UI fields remain for older configs.
    """

    dashboard_port: int = 3999
    api_base_port: int = 8000
    ui_base_port: int = 3000
    api_dir: str = ""
    ui_dir: str = ""
    api_command: str = ""
    ui_command: str = ""
    ui_api_env_var: str = "NEXT_PUBLIC_API_URL"
    data_dir: str = ""
    install_command: str = "npm install"
    install_if_missing: str = "node_modules"
    services: tuple[PreviewServiceConfig, ...] = field(default_factory=tuple)

    @property
    def configured(self) -> bool:
        """Return whether the repo supplied enough data to start previews."""

        return bool(self.services) or bool(
            self.api_dir and self.ui_dir and self.api_command and self.ui_command
        )


@dataclass(frozen=True)
class FleetConfig:
    """Runtime configuration after resolving config files and CLI overrides."""

    repo_root: Path
    project_name: str
    worktree_root: Path
    base_ref: str = "origin/main"
    agents: tuple[AgentSpec, ...] = field(default_factory=tuple)
    preview: PreviewConfig = field(default_factory=PreviewConfig)
    state_root: Path | None = None

    def resolved_state_root(self) -> Path:
        """Return the state directory for logs, pids, and generated dashboards."""

        if self.state_root is not None:
            return self.state_root
        repo_hash = hashlib.sha256(str(self.repo_root.resolve()).encode("utf-8")).hexdigest()
        return Path("/tmp") / "agentfleet" / f"{self.project_name}-{repo_hash[:10]}"


@dataclass(frozen=True)
class AgentSlot:
    """A single runnable agent bound to a worktree and branch."""

    kind: str
    index: int
    command: str
    branch: str
    path: Path

    @property
    def label(self) -> str:
        """Return a stable label used in terminal windows and logs."""

        return f"{self.kind}-{self.index}"


@dataclass(frozen=True)
class RuntimePreviewService:
    """Resolved service metadata for a single worktree preview."""

    name: str
    port: int
    directory: Path
    command: str
    env: dict[str, str]
    log: Path
    primary: bool = False
    install_command: str = ""
    install_if_missing: str = ""

    @property
    def url(self) -> str:
        """Return the localhost URL for this service."""

        return f"http://localhost:{self.port}"


@dataclass(frozen=True)
class PreviewSlot:
    """Runtime metadata for a worktree preview."""

    slot: AgentSlot
    api_port: int
    ui_port: int
    api_log: Path
    ui_log: Path
    services: tuple[RuntimePreviewService, ...] = field(default_factory=tuple)

    @property
    def primary_service(self) -> RuntimePreviewService | None:
        """Return the service that should be embedded in the preview iframe."""

        if not self.services:
            return None
        for service in self.services:
            if service.primary:
                return service
        return self.services[-1]

    @property
    def api_url(self) -> str:
        """Return the API base URL."""

        for service in self.services:
            if service.name in {"api", "backend", "server"}:
                return service.url
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def ui_url(self) -> str:
        """Return the UI base URL."""

        primary = self.primary_service
        if primary is not None:
            return primary.url
        return f"http://localhost:{self.ui_port}"
