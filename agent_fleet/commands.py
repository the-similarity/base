"""Shared subprocess and shell helpers for the fleet CLI."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path


def require_command(command: str) -> bool:
    """Return whether a command exists on PATH."""

    return shutil.which(command) is not None


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command and include useful context in failures."""

    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        tail = (result.stderr or result.stdout).strip()[-1600:]
        rendered = " ".join(shlex.quote(part) for part in command)
        location = f" in {cwd}" if cwd else ""
        raise SystemExit(
            f"Command failed{location}: {rendered}\n"
            f"exit code: {result.returncode}\n{tail}"
        )
    return result


def sh_quote(value: Path | str) -> str:
    """Return a shell-safe single token."""

    return shlex.quote(str(value))
