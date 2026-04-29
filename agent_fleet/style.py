"""Small ANSI styling helpers for readable CLI output.

AgentFleet intentionally avoids runtime dependencies, so this module keeps the
visual layer to plain ANSI escape codes and ASCII-only symbols. Colors are
disabled automatically when stdout is not a TTY or ``NO_COLOR`` is set.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"


def enabled() -> bool:
    """Return whether ANSI styling should be emitted."""

    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def color(text: str, code: str) -> str:
    """Colorize text when styling is enabled."""

    return f"{code}{text}{RESET}" if enabled() else text


def bold(text: str) -> str:
    """Return bold text when styling is enabled."""

    return color(text, BOLD)


def dim(text: str) -> str:
    """Return dim text when styling is enabled."""

    return color(text, DIM)


def ok(text: str = "OK") -> str:
    """Return an OK status label."""

    return color(text, GREEN)


def fail(text: str = "FAIL") -> str:
    """Return a failure status label."""

    return color(text, RED)


def warn(text: str = "WARN") -> str:
    """Return a warning status label."""

    return color(text, YELLOW)


def info(text: str) -> str:
    """Return highlighted informational text."""

    return color(text, CYAN)


def title(text: str) -> str:
    """Return a section title."""

    return bold(info(text))


def rule(label: str) -> str:
    """Return a compact section rule."""

    return f"\n{title(label)}\n{dim('-' * max(48, len(label)))}"


def kv(label: str, value: object) -> str:
    """Format a label/value row."""

    return f"{dim(label + ':'):<18} {value}"
