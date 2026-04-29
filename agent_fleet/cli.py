"""Command-line interface for ``agentfleet``."""

from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path

from .config import config_path, find_repo_root, load_config, write_default_config
from .doctor import run_doctor
from .fleet import (
    build_slots,
    clean_fleet,
    count_overrides,
    launch_fleet,
    print_status,
    setup_fleet,
)
from .models import AgentSlot, FleetConfig
from .npm_pkg import cached_npm_latest_version, installed_version, is_newer, run_npm_upgrade
from .preview import print_saved_preview_state, start_preview, stop_previews


def main(argv: list[str] | None = None) -> int:
    """Run the selected command."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        print_onboarding()
        maybe_print_update_notice()
        return 0

    if args.command == "upgrade":
        return run_npm_upgrade(dry_run=getattr(args, "dry_run", False))

    repo_root = find_repo_root()

    if args.command == "init":
        path = write_default_config(repo_root, force=args.force)
        print_init_followup(path)
        return 0

    cfg = load_config(repo_root)
    slots = selected_slots(cfg, args)

    if args.command == "doctor":
        return run_doctor(cfg, slots, check_preview=not args.no_preview)

    if args.command == "setup":
        maybe_doctor(args, cfg, slots, check_preview=False)
        setup_fleet(cfg, slots, link_node_modules=args.link_node_modules)
        print_handoff(cfg, slots)
        return 0

    if args.command == "launch":
        maybe_doctor(args, cfg, slots, check_preview=False)
        if not args.no_setup:
            setup_fleet(cfg, slots, link_node_modules=args.link_node_modules)
        launch_fleet(
            cfg,
            slots,
            args.terminal,
            args.session,
            args.no_attach,
            tmux_layout=args.tmux_layout,
            ghostty_size=args.ghostty_size,
        )
        return 0

    if args.command == "preview":
        cfg = apply_preview_overrides(cfg, args)
        preview_slots = explicit_worktrees(cfg, args.worktrees) if args.worktrees else slots
        if args.include_main:
            preview_slots = [
                AgentSlot(
                    kind="main",
                    index=0,
                    command="",
                    branch=current_branch(cfg.repo_root),
                    path=cfg.repo_root,
                ),
                *preview_slots,
            ]
        if args.limit is not None:
            preview_slots = preview_slots[: args.limit]
        maybe_doctor(args, cfg, preview_slots, check_preview=False)
        return start_preview(cfg, preview_slots, install_deps=not args.no_install)

    if args.command == "status":
        print_status(cfg, slots)
        print_saved_preview_state(cfg)
        return 0

    if args.command == "stop":
        return stop_previews(cfg)

    if args.command == "clean":
        clean_fleet(cfg, slots, force=args.force)
        return 0

    if args.command == "tasks":
        write_task_scaffold(slots, args.out, args.force)
        return 0

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(prog="agentfleet", description="Manage local worktree agent fleets.")
    subcommands = parser.add_subparsers(dest="command")

    init = subcommands.add_parser("init", help="Write a starter agentfleet.toml.")
    init.add_argument("--force", action="store_true", help="Overwrite an existing config.")

    doctor = subcommands.add_parser("doctor", help="Verify required local dependencies.")
    add_count_args(doctor)
    doctor.add_argument("--no-preview", action="store_true", help="Skip preview port checks.")

    setup = subcommands.add_parser("setup", help="Create or refresh worktrees.")
    add_count_args(setup)
    add_skip_doctor(setup)
    setup.add_argument("--link-node-modules", action="store_true", help="Symlink frontend node_modules when safe.")

    launch = subcommands.add_parser(
        "launch",
        help="Create worktrees and open agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Terminal backends must be installed locally:\n"
            "  tmux          e.g. brew install tmux (Linux: use your package manager)\n"
            "  iterm         iTerm2 on macOS, e.g. brew install --cask iterm2\n"
            "  ghostty       Ghostty, e.g. brew install --cask ghostty (ghostty-splits uses the same app)\n"
            "  auto          uses tmux when it is on PATH, otherwise print-only\n"
            "\n"
            "Default agent commands in agentfleet.toml are claude and codex. Install the CLIs, then run doctor:\n"
            "  claude        npm install -g @anthropic-ai/claude-code  (see https://code.claude.com/docs/en/setup)\n"
            "  codex         npm install -g @openai/codex  (see https://developers.openai.com/codex/cli)\n"
        ),
    )
    add_count_args(launch)
    add_skip_doctor(launch)
    launch.add_argument("--link-node-modules", action="store_true", help="Symlink frontend node_modules when safe.")
    launch.add_argument(
        "--terminal",
        choices=["auto", "tmux", "iterm", "ghostty", "ghostty-splits", "print"],
        default="auto",
    )
    launch.add_argument(
        "--tmux-layout",
        choices=["panes", "windows"],
        default="panes",
        help="For tmux, show agents as tiled panes or separate windows.",
    )
    launch.add_argument(
        "--ghostty-size",
        metavar="COLSxROWS",
        default=None,
        help="Initial Ghostty window size, e.g. 180x50. Applies to ghostty and ghostty-splits.",
    )
    launch.add_argument(
        "--session",
        default=None,
        help="tmux session name. Defaults to agentfleet-<project_name>.",
    )
    launch.add_argument("--no-attach", action="store_true", help="For tmux, do not attach.")
    launch.add_argument("--no-setup", action="store_true", help="Do not create/fetch worktrees before launching.")

    preview = subcommands.add_parser("preview", help="Start the local preview dashboard.")
    add_count_args(preview)
    add_skip_doctor(preview)
    preview.add_argument("worktrees", nargs="*", type=Path, help="Explicit worktree paths to preview.")
    preview.add_argument("--worktrees", dest="worktrees_flag", nargs="*", type=Path, help=argparse.SUPPRESS)
    preview.add_argument("--dashboard-port", type=int, default=None, help="Override the dashboard port.")
    preview.add_argument("--limit", type=int, default=None, help="Limit the number of previews.")
    preview.add_argument("--include-main", action="store_true", help="Include the main repo worktree.")
    preview.add_argument("--no-install", action="store_true", help="Skip preview dependency install command.")

    status = subcommands.add_parser("status", help="Show branch and dirty state.")
    add_count_args(status)

    stop = subcommands.add_parser("stop", help="Stop saved preview processes.")
    add_count_args(stop)

    clean = subcommands.add_parser("clean", help="Remove worktrees and branches.")
    add_count_args(clean)
    clean.add_argument("--force", action="store_true", help="Remove dirty worktrees and force-delete branches.")

    tasks = subcommands.add_parser("tasks", help="Print or write a task scaffold.")
    add_count_args(tasks)
    tasks.add_argument("--out", type=Path, default=None)
    tasks.add_argument("--force", action="store_true")

    upgrade = subcommands.add_parser(
        "upgrade",
        help="Reinstall the global npm package to the latest release (requires npm).",
    )
    upgrade.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the npm command that would run instead of executing it.",
    )

    return parser


def add_count_args(parser: argparse.ArgumentParser) -> None:
    """Add legacy count overrides for common agent families."""

    parser.add_argument("--codex", type=int, default=None, help="Override Codex agent count.")
    parser.add_argument("--claude", type=int, default=None, help="Override Claude agent count.")


def add_skip_doctor(parser: argparse.ArgumentParser) -> None:
    """Add the common doctor bypass flag."""

    parser.add_argument("--skip-doctor", action="store_true", help="Skip preflight checks.")


def _show_agentfleet_init_in_onboarding() -> bool:
    """True when ``agentfleet.toml`` is missing in the current git repo (first-time)."""

    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return not config_path(candidate).exists()
    return True


INIT_AI_AGENT_PROMPT = """Configure AgentFleet for this repository.

1. Create or update agentfleet.toml.
2. Keep the default fleet at 2 Codex agents and 2 Claude agents unless this repo needs something else.
3. Inspect the project and add [[preview.services]] for the local services needed to preview work.
4. For each preview service set name, dir, port_base, command using {port}, and env values if needed.
5. Mark the browser-facing service with primary = true.
6. Run `agentfleet doctor` and explain any failures.
7. If this is frontend-only, backend-only, Docker-only, mobile, or multi-service, configure the closest useful setup and explain the tradeoff."""


def print_init_followup(written: Path) -> None:
    """Print README-aligned instructions after ``agentfleet init`` writes the config."""

    print(f"Wrote {written}")
    print()
    print(
        'Give this checklist to your AI agent (same block as "Give This To Your AI Agent" in the '
        "AgentFleet README), or edit agentfleet.toml yourself in the project root."
    )
    print()
    print(INIT_AI_AGENT_PROMPT)


def print_onboarding() -> None:
    """Print a compact orientation screen for first-time CLI usage."""

    # ANSI color codes
    CYAN = "\033[38;5;51m"  # bright cyan — ships
    BLUE = "\033[38;5;39m"  # ocean blue — waves
    YELLOW = "\033[38;5;220m"  # gold — title
    GREEN = "\033[38;5;120m"  # soft green — section headers
    GRAY = "\033[38;5;245m"  # muted — descriptions
    WHITE = "\033[38;5;255m"  # bright — commands
    MAGENTA = "\033[38;5;213m"  # accent — flags
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    init_line = f"  {WHITE}agentfleet init{RESET}\n" if _show_agentfleet_init_in_onboarding() else ""

    head = rf"""
{CYAN}            |             |              |
           )_)           )_)            )_)
          )___)         )___)          )___)
         )____)        )____)         )____)
       __|____|______|____|________|____|__{RESET}
   {BLUE}~~~~\                                  /~~~~
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~{RESET}

{YELLOW}{BOLD}    _                    _   _____ _           _
   / \   __ _  ___ _ __ | |_|  ___| | ___  ___| |_
  / _ \ / _` |/ _ \ '_ \| __| |_  | |/ _ \/ _ \ __|
 / ___ \ (_| |  __/ | | | |_|  _| | |  __/  __/ |_
/_/   \_\__, |\___|_| |_|\__|_|   |_|\___|\___|\__|
        |___/{RESET}

{GRAY}AgentFleet: run coding agents in isolated git worktrees.{RESET}
"""

    tail = rf"""
{GREEN}{BOLD}Start here:{RESET}
{init_line}  {WHITE}agentfleet doctor{RESET}
  {WHITE}agentfleet setup{RESET}
  {WHITE}agentfleet launch {MAGENTA}--terminal{RESET} {WHITE}ghostty-splits {MAGENTA}--ghostty-size{RESET} {WHITE}180x50{RESET}
  {WHITE}agentfleet preview{RESET}

{GREEN}{BOLD}Launch terminals{RESET} {GRAY}(install the matching app first; see agentfleet launch --help):{RESET}
  {MAGENTA}--terminal ghostty-splits{RESET}   {GRAY}one Ghostty window with native split panes{RESET}
  {MAGENTA}--terminal ghostty{RESET}          {GRAY}separate Ghostty windows{RESET}
  {MAGENTA}--terminal tmux{RESET}             {GRAY}tmux session, panes by default{RESET}
  {MAGENTA}--terminal iterm{RESET}            {GRAY}iTerm windows/tabs{RESET}
  {MAGENTA}--terminal print{RESET}            {GRAY}print commands only{RESET}

{GREEN}{BOLD}Ghostty sizing:{RESET}
  {MAGENTA}--ghostty-size 180x50{RESET}       {GRAY}set initial columns x rows for Ghostty windows{RESET}

{GREEN}{BOLD}Agent CLIs{RESET} {GRAY}(defaults; override command= in agentfleet.toml if you use others):{RESET}
  {CYAN}claude{RESET}    {WHITE}npm install -g @anthropic-ai/claude-code{RESET}   {DIM}https://code.claude.com/docs/en/setup{RESET}
  {CYAN}codex{RESET}     {WHITE}npm install -g @openai/codex{RESET}              {DIM}https://developers.openai.com/codex/cli{RESET}

{GREEN}{BOLD}Other useful commands:{RESET}
  {WHITE}agentfleet status{RESET}
  {WHITE}agentfleet stop{RESET}
  {WHITE}agentfleet clean{RESET}
  {WHITE}agentfleet tasks {MAGENTA}--out{RESET} {WHITE}agentfleet-tasks.yaml{RESET}
  {WHITE}agentfleet upgrade{RESET}            {GRAY}npm global install to latest{RESET}

{DIM}Run `agentfleet --help` or `agentfleet <command> --help` for details.{RESET}
"""

    print(head + tail)


def maybe_print_update_notice() -> None:
    """If the npm registry has a newer release, print a short upgrade hint."""

    if os.environ.get("AGENTFLEET_NO_UPDATE_CHECK"):
        return
    current = installed_version()
    latest = cached_npm_latest_version()
    if not latest or not is_newer(latest, current):
        return
    yellow = "\033[38;5;220m"
    white = "\033[38;5;255m"
    dim = "\033[2m"
    reset = "\033[0m"
    print()
    print(f"{yellow}Update available on npm:{reset} {white}{latest}{reset} (installed: {dim}{current}{reset}).")
    print("Upgrade with:")
    print(f"  {dim}npm install -g @buyan14/agentfleet@latest{reset}")
    print(f"  {dim}agentfleet upgrade{reset}")
    print(f"{dim}Disable this check: AGENTFLEET_NO_UPDATE_CHECK=1{reset}")


def selected_slots(cfg: FleetConfig, args: argparse.Namespace) -> list[AgentSlot]:
    """Return slots after applying CLI count overrides."""

    return build_slots(cfg, count_overrides(getattr(args, "codex", None), getattr(args, "claude", None)))


def apply_preview_overrides(cfg: FleetConfig, args: argparse.Namespace) -> FleetConfig:
    """Apply preview-only CLI overrides to immutable config objects."""

    worktrees_flag = getattr(args, "worktrees_flag", None)
    if worktrees_flag is not None:
        args.worktrees = worktrees_flag
    if args.dashboard_port is None:
        return cfg
    return replace(cfg, preview=replace(cfg.preview, dashboard_port=args.dashboard_port))


def explicit_worktrees(cfg: FleetConfig, paths: list[Path]) -> list[AgentSlot]:
    """Turn explicit preview paths into synthetic slots."""

    slots: list[AgentSlot] = []
    for index, path in enumerate(paths, start=1):
        resolved = path.resolve()
        if not resolved.exists():
            print(f"Skipping missing worktree: {resolved}")
            continue
        slots.append(
            AgentSlot(
                kind="agent",
                index=index,
                command="",
                branch=current_branch(resolved),
                path=resolved,
            )
        )
    return slots


def current_branch(path: Path) -> str:
    """Return the current branch for display-only explicit worktrees."""

    from .fleet import current_branch as branch_for_path

    return branch_for_path(path)


def maybe_doctor(
    args: argparse.Namespace, cfg: FleetConfig, slots: list[AgentSlot], check_preview: bool
) -> None:
    """Run doctor unless the user explicitly bypassed it."""

    if getattr(args, "skip_doctor", False):
        return
    code = run_doctor(cfg, slots, check_preview=check_preview, quiet=True)
    if code != 0:
        raise SystemExit(code)


def print_handoff(cfg: FleetConfig, slots: list[AgentSlot]) -> None:
    """Print launch and preview commands after setup."""

    print("\nLaunch:")
    print("  agentfleet launch --no-setup")
    paths = " ".join(str(slot.path) for slot in slots)
    print("\nPreview:")
    print(f"  agentfleet preview --worktrees {paths}")
    print(f"\nState: {cfg.resolved_state_root()}")


def write_task_scaffold(slots: list[AgentSlot], out: Path | None, force: bool) -> None:
    """Print or write a mixed-agent task scaffold."""

    lines = [
        "# Generated by agentfleet tasks",
        "tasks:",
    ]
    for slot in slots:
        lines.extend(
            [
                f"  - id: {slot.label}-task",
                f"    agent: {slot.kind}",
                f"    title: \"chore: describe {slot.label} work\"",
                "    prompt: |",
                f"      You are {slot.label}. Work only in your assigned scope.",
                "      Scope: <paths>",
                "      Task: <specific outcome>",
                "",
            ]
        )
    content = "\n".join(lines) + "\n"
    if out is None:
        print(content, end="")
        return
    path = out if out.is_absolute() else Path.cwd() / out
    if path.exists() and not force:
        raise SystemExit(f"Refusing to overwrite {path}. Pass --force.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
