"""Worktree planning, setup, launch, status, and cleanup."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .commands import require_command, run, sh_quote
from .models import AgentSlot, FleetConfig
from .style import dim, info, kv, ok, rule, title, warn


def build_slots(cfg: FleetConfig, overrides: dict[str, int] | None = None) -> list[AgentSlot]:
    """Return all configured slots, applying optional CLI count overrides."""

    slots: list[AgentSlot] = []
    for spec in cfg.agents:
        count = overrides.get(spec.kind, spec.count) if overrides else spec.count
        if count < 0:
            raise SystemExit(f"{spec.kind} count must be non-negative.")
        for index in range(1, count + 1):
            branch = spec.branch_name(index)
            slots.append(
                AgentSlot(
                    kind=spec.kind,
                    index=index,
                    command=spec.command_name(),
                    branch=branch,
                    path=worktree_path(cfg, spec.kind, index),
                )
            )
    return slots


def count_overrides(codex: int | None, claude: int | None) -> dict[str, int]:
    """Return legacy CLI count overrides for the common agent families."""

    overrides: dict[str, int] = {}
    if codex is not None:
        overrides["codex"] = codex
    if claude is not None:
        overrides["claude"] = claude
    return overrides


def worktree_path(cfg: FleetConfig, kind: str, index: int) -> Path:
    """Return the worktree path for a slot."""

    if cfg.worktree_root == cfg.repo_root.parent:
        return cfg.worktree_root / f"{cfg.project_name}-{kind}-{index}"
    return cfg.worktree_root / f"{kind}-{index}"


def setup_fleet(cfg: FleetConfig, slots: list[AgentSlot], link_node_modules: bool = False) -> None:
    """Create or reconnect all requested worktrees."""

    run(["git", "fetch", "origin", "main"], cwd=cfg.repo_root)
    cfg.worktree_root.mkdir(parents=True, exist_ok=True)
    print(rule("Worktrees"))
    for slot in slots:
        ensure_worktree(cfg, slot)
        if link_node_modules:
            link_frontend_node_modules(cfg.repo_root, slot.path)


def ensure_worktree(cfg: FleetConfig, slot: AgentSlot) -> None:
    """Ensure a single slot has a usable worktree."""

    if is_registered_worktree(cfg.repo_root, slot.path):
        print(f"{ok('exists'):<10} {slot.label:<12} {slot.path} {dim('(' + slot.branch + ')')}")
        return
    if slot.path.exists() and not (slot.path / ".git").exists():
        raise SystemExit(
            f"Path exists but is not a git worktree: {slot.path}. "
            "Move it aside or choose a different worktree_root."
        )
    if slot.path.exists():
        print(f"{ok('exists'):<10} {slot.label:<12} {slot.path} {dim('(' + slot.branch + ')')}")
        return
    if branch_exists(cfg.repo_root, slot.branch):
        print(f"{info('attach'):<10} {slot.label:<12} {slot.path} {dim('(' + slot.branch + ')')}")
        run(["git", "worktree", "add", str(slot.path), slot.branch], cwd=cfg.repo_root)
        return

    print(f"{info('create'):<10} {slot.label:<12} {slot.path} {dim('(' + slot.branch + ' from ' + cfg.base_ref + ')')}")
    run(["git", "worktree", "add", str(slot.path), "-b", slot.branch, cfg.base_ref], cwd=cfg.repo_root)


def branch_exists(repo_root: Path, branch: str) -> bool:
    """Return whether a local branch exists."""

    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def is_registered_worktree(repo_root: Path, path: Path) -> bool:
    """Return whether git knows about the worktree path."""

    result = run(["git", "worktree", "list", "--porcelain"], cwd=repo_root, check=False)
    needle = f"worktree {path.resolve()}"
    return needle in result.stdout.splitlines()


def link_frontend_node_modules(repo_root: Path, worktree: Path) -> None:
    """Symlink matching Node dependencies for any package-lock based project."""

    for lockfile in repo_root.rglob("package-lock.json"):
        if ignored_dependency_path(lockfile, repo_root):
            continue
        relative_lockfile = lockfile.relative_to(repo_root)
        worktree_lockfile = worktree / relative_lockfile
        package_dir = lockfile.parent
        worktree_package_dir = worktree_lockfile.parent
        source = package_dir / "node_modules"
        target = worktree_package_dir / "node_modules"
        if not source.is_dir() or not worktree_package_dir.is_dir():
            continue
        if not same_file(lockfile, worktree_lockfile):
            print(f"  skip node_modules link for {worktree.name}/{relative_lockfile.parent}: lockfile differs or missing")
            continue
        if target.is_symlink():
            continue
        if target.exists():
            print(f"  keep existing node_modules: {target}")
            continue
        target.symlink_to(source, target_is_directory=True)
        print(f"  linked node_modules in {worktree.name}/{relative_lockfile.parent}")


def ignored_dependency_path(path: Path, repo_root: Path) -> bool:
    """Return whether a dependency search path is inside generated folders."""

    relative_parts = path.relative_to(repo_root).parts
    return any(part in {".git", "node_modules"} for part in relative_parts)


def same_file(left: Path, right: Path) -> bool:
    """Return whether two files exist and contain identical bytes."""

    return left.exists() and right.exists() and left.read_bytes() == right.read_bytes()


def launch_fleet(
    cfg: FleetConfig,
    slots: list[AgentSlot],
    terminal: str,
    session: str | None,
    no_attach: bool,
    tmux_layout: str = "panes",
    ghostty_size: str | None = None,
) -> None:
    """Launch each agent in its own terminal context."""

    chosen = choose_terminal(terminal)
    if chosen == "tmux":
        launch_tmux(cfg, slots, session or default_tmux_session(cfg), no_attach, tmux_layout)
    elif chosen == "iterm":
        launch_iterm(slots)
    elif chosen == "ghostty":
        launch_ghostty(slots, ghostty_size)
    elif chosen == "ghostty-splits":
        launch_ghostty_splits(slots, ghostty_size)
    elif chosen == "print":
        print_launch_hints(slots)
    else:
        raise SystemExit(f"Unsupported terminal: {chosen}")


def choose_terminal(requested: str) -> str:
    """Pick a terminal backend."""

    if requested != "auto":
        return requested
    return "tmux" if shutil.which("tmux") else "print"


def default_tmux_session(cfg: FleetConfig) -> str:
    """Return the project-scoped tmux session name.

    The default must include the project name so launching AgentFleet in two
    repositories cannot silently dump every agent window into one shared session.
    """

    safe_project = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in cfg.project_name.lower()
    ).strip("-")
    return f"agentfleet-{safe_project or 'repo'}"


def launch_tmux(
    cfg: FleetConfig, slots: list[AgentSlot], session: str, no_attach: bool, layout: str
) -> None:
    """Open agents in tmux using a tiled pane or window layout."""

    if not require_command("tmux"):
        raise SystemExit("Missing required command: tmux")
    if layout == "panes":
        launch_tmux_panes(cfg, slots, session, no_attach)
        return
    launch_tmux_windows(cfg, slots, session, no_attach)


def launch_tmux_windows(cfg: FleetConfig, slots: list[AgentSlot], session: str, no_attach: bool) -> None:
    """Open one tmux window per agent."""

    if subprocess.run(["tmux", "has-session", "-t", session], check=False).returncode != 0:
        run(["tmux", "new-session", "-d", "-s", session, "-n", "control", "-c", str(cfg.repo_root)])
    existing_windows = tmux_window_names(session)
    for slot in slots:
        if slot.label in existing_windows:
            print(f"{warn('skip'):<10} tmux window exists: {session}:{slot.label}")
            continue
        run(
            [
                "tmux",
                "new-window",
                "-t",
                session,
                "-n",
                slot.label,
                "-c",
                str(slot.path),
                slot.command,
            ]
        )
    print_tmux_ready(session, "windows", no_attach)


def launch_tmux_panes(cfg: FleetConfig, slots: list[AgentSlot], session: str, no_attach: bool) -> None:
    """Open all agents as tiled panes in one tmux window.

    This uses tmux's split-window and select-layout tiled workflow so all
    agents can be watched in parallel from a single window.
    """

    if not slots:
        raise SystemExit("No agent slots requested.")

    window = "agents"
    target = f"{session}:{window}"
    session_exists = subprocess.run(["tmux", "has-session", "-t", session], check=False).returncode == 0
    if session_exists and tmux_window_exists(session, window):
        print(f"{warn('skip'):<10} tmux window exists: {target}")
        print_tmux_ready(session, "panes", no_attach)
        return

    first = slots[0]
    if not session_exists:
        run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session,
                "-n",
                window,
                "-c",
                str(first.path),
                first.command,
            ]
        )
    else:
        run(
            [
                "tmux",
                "new-window",
                "-t",
                session,
                "-n",
                window,
                "-c",
                str(first.path),
                first.command,
            ]
        )
    run(["tmux", "select-pane", "-t", f"{target}.0", "-T", first.label])

    for slot in slots[1:]:
        run(["tmux", "split-window", "-t", target, "-c", str(slot.path), slot.command])
        run(["tmux", "select-pane", "-t", f"{target}.!", "-T", slot.label])
        run(["tmux", "select-layout", "-t", target, "tiled"])

    run(["tmux", "select-layout", "-t", target, "tiled"])
    print_tmux_ready(session, "panes", no_attach)


def print_tmux_ready(session: str, layout: str, no_attach: bool) -> None:
    """Print tmux handoff information."""

    print(rule("Tmux"))
    print(kv("session", session))
    print(kv("layout", layout))
    print(kv("attach", f"tmux attach -t {session}"))
    if not no_attach:
        os.execvp("tmux", ["tmux", "attach", "-t", session])


def tmux_window_names(session: str) -> set[str]:
    """Return existing tmux window names for a session."""

    result = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def tmux_window_exists(session: str, window: str) -> bool:
    """Return whether a tmux window exists in the target session."""

    return window in tmux_window_names(session)


def launch_iterm(slots: list[AgentSlot]) -> None:
    """Open iTerm2 tabs and run each agent command."""

    script_lines = ['tell application "iTerm"', "  activate", "  create window with default profile"]
    for index, slot in enumerate(slots):
        escaped = shell_join_cd_command(slot).replace('"', '\\"')
        if index > 0:
            script_lines.append("  tell current window to create tab with default profile")
        script_lines.append(f'  tell current session of current window to write text "{escaped}"')
    script_lines.append("end tell")
    run(["osascript", "-e", "\n".join(script_lines)])


def launch_ghostty(slots: list[AgentSlot], size: str | None = None) -> None:
    """Open Ghostty windows and run each agent command."""

    if not shutil.which("open"):
        raise SystemExit("Ghostty launching is only supported on systems with `open`.")
    size_args = ghostty_size_args(size)
    for slot in slots:
        run(["open", "-na", "Ghostty", "--args", *size_args, "-e", "zsh", "-lc", shell_join_cd_command(slot)])


def launch_ghostty_splits(slots: list[AgentSlot], size: str | None = None) -> None:
    """Open one Ghostty window and arrange agents in native split panes.

    Ghostty documents ``new_split`` as a keybinding action and enables the
    macOS AppleScript dictionary by default, but macOS does not currently expose
    a CLI action for "new split and run this command". This backend therefore
    drives the documented split keybindings through System Events. It is scoped
    to launch time and fails closed with a clear permission hint if macOS blocks
    accessibility automation.
    """

    if not slots:
        return
    if not shutil.which("open"):
        raise SystemExit("Ghostty split launching is only supported on macOS with `open`.")

    first, *rest = slots
    run(["open", "-na", "Ghostty", "--args", *ghostty_size_args(size), "-e", "zsh", "-lc", shell_join_cd_command(first)])
    if not rest:
        return

    time.sleep(1.2)
    for index, slot in enumerate(rest, start=2):
        run_ghostty_split_applescript(split_script(index, shell_join_cd_command(slot)))


def ghostty_size_args(size: str | None) -> list[str]:
    """Return Ghostty CLI size args from a ``COLSxROWS`` value."""

    if not size:
        return []
    normalized = size.lower().replace("×", "x")
    try:
        columns_text, rows_text = normalized.split("x", 1)
        columns = int(columns_text)
        rows = int(rows_text)
    except ValueError as exc:
        raise SystemExit("--ghostty-size must look like COLSxROWS, for example 180x50.") from exc
    if columns <= 0 or rows <= 0:
        raise SystemExit("--ghostty-size columns and rows must be positive integers.")
    return [f"--window-width={columns}", f"--window-height={rows}"]


def split_script(index: int, command: str) -> str:
    """Return AppleScript that creates a split and starts an agent command."""

    escaped = applescript_string(command)
    # Build a pleasant 2x2 layout for the common four-agent case:
    # first pane already exists, second splits right, third splits down on the
    # right, fourth moves left and splits down. Additional panes keep splitting
    # the currently focused pane to the right.
    if index == 2:
        split_keys = 'keystroke "d" using command down'
    elif index == 3:
        split_keys = 'keystroke "d" using {command down, shift down}'
    elif index == 4:
        split_keys = """
        key code 123 using {command down, option down}
        delay 0.15
        keystroke "d" using {command down, shift down}
        """.strip()
    else:
        split_keys = 'keystroke "d" using command down'

    return f"""
tell application "Ghostty" to activate
delay 0.25
set previousClipboard to the clipboard
set the clipboard to {escaped}
tell application "System Events"
    tell process "Ghostty"
        {split_keys}
        delay 0.25
        keystroke "v" using command down
        key code 36
    end tell
end tell
delay 0.1
set the clipboard to previousClipboard
"""


def applescript_string(value: str) -> str:
    """Quote text as an AppleScript string literal."""

    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_ghostty_split_applescript(script: str) -> None:
    """Run a Ghostty split automation script with a useful permission error."""

    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, check=False)
    if result.returncode == 0:
        return
    stderr = result.stderr.strip() or result.stdout.strip()
    raise SystemExit(
        "Ghostty split automation failed. Grant your terminal Accessibility permission "
        "in System Settings -> Privacy & Security -> Accessibility, then retry.\n"
        f"osascript: {stderr}"
    )


def shell_join_cd_command(slot: AgentSlot) -> str:
    """Return the command launched inside a terminal session."""

    return f"cd {sh_quote(slot.path)} && {slot.command}"


def print_launch_hints(slots: list[AgentSlot]) -> None:
    """Print copy-paste launch and preview commands."""

    print(rule("Launch Commands"))
    for slot in slots:
        print(f"  {shell_join_cd_command(slot)}")
    paths = " ".join(sh_quote(slot.path) for slot in slots)
    print(rule("Preview Dashboard"))
    print(f"  agentfleet preview --worktrees {paths}")


def print_status(cfg: FleetConfig, slots: list[AgentSlot]) -> None:
    """Print branch and dirty status for every slot."""

    print(rule("Fleet Status"))
    print(f"{title('slot'):<12} {title('branch'):<28} {title('state'):<10} path")
    print(dim("-" * 100))
    for slot in slots:
        if not slot.path.exists():
            print(f"{slot.label:<12} {slot.branch:<28} {warn('missing'):<10} {slot.path}")
            continue
        state = warn("dirty") if git_dirty(slot.path) else ok("clean")
        branch = current_branch(slot.path) or slot.branch
        print(f"{slot.label:<12} {branch:<28} {state:<10} {slot.path}")
    print(f"\n{kv('state', cfg.resolved_state_root())}")


def git_dirty(path: Path) -> bool:
    """Return whether a worktree has local changes."""

    result = run(["git", "status", "--porcelain"], cwd=path, check=False)
    return bool(result.stdout.strip())


def current_branch(path: Path) -> str:
    """Return the current branch for a worktree."""

    result = run(["git", "branch", "--show-current"], cwd=path, check=False)
    return result.stdout.strip()


def clean_fleet(cfg: FleetConfig, slots: list[AgentSlot], force: bool) -> None:
    """Remove worktrees and delete local branches, preserving dirty work by default."""

    dirty = [slot for slot in slots if slot.path.exists() and git_dirty(slot.path)]
    if dirty and not force:
        labels = ", ".join(slot.label for slot in dirty)
        raise SystemExit(f"Refusing to clean dirty worktrees: {labels}. Pass --force to override.")

    for slot in slots:
        if is_registered_worktree(cfg.repo_root, slot.path):
            cmd = ["git", "worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(str(slot.path))
            run(cmd, cwd=cfg.repo_root)

    branches = [slot.branch for slot in slots if branch_exists(cfg.repo_root, slot.branch)]
    if branches:
        run(["git", "branch", "-D" if force else "-d", *branches], cwd=cfg.repo_root)
