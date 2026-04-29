"""Environment diagnostics for clone-and-run reliability."""

from __future__ import annotations

from .commands import require_command
from .models import AgentSlot, FleetConfig
from .preview import build_preview_slots, port_is_free
from .style import fail, ok as ok_label, rule, warn


def run_doctor(cfg: FleetConfig, slots: list[AgentSlot], check_preview: bool = True) -> int:
    """Print dependency and port checks; return a process exit code."""

    print(rule("AgentFleet Doctor"))
    failures = 0
    failures += check("git", require_command("git"), "required for worktree isolation")
    failures += check("python", require_command("python"), "required for Python preview commands")

    seen_commands = sorted({slot.command for slot in slots if slot.command})
    for command in seen_commands:
        failures += check(command, require_command(command), f"agent command for {command}")

    if cfg.preview.configured and check_preview:
        failures += check("preview api dir", True, cfg.preview.api_dir)
        failures += check("preview ui dir", True, cfg.preview.ui_dir)
        failures += check(
            f"dashboard port {cfg.preview.dashboard_port}",
            port_is_free(cfg.preview.dashboard_port),
            "must be free before preview",
        )
        for preview in build_preview_slots(cfg, slots):
            failures += check(f"api port {preview.api_port}", port_is_free(preview.api_port), preview.slot.label)
            failures += check(f"ui port {preview.ui_port}", port_is_free(preview.ui_port), preview.slot.label)
    elif check_preview:
        print(f"{warn():<5} {'preview':<28} not configured")

    if failures:
        print(f"\n{fail()} Doctor failed: {failures} check(s) need attention.")
        return 1
    print(f"\n{ok_label()} Doctor passed.")
    return 0


def check(name: str, ok: bool, detail: str) -> int:
    """Print one diagnostic row."""

    status = ok_label() if ok else fail()
    print(f"{status:<5} {name:<28} {detail}")
    return 0 if ok else 1
