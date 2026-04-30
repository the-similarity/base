"""npm registry version checks and global upgrade helper for the AgentFleet CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

NPM_SCOPE_PACKAGE = "@buyan14/agentfleet"
# Registry expects scoped name path-encoded: @scope%2Fname
NPM_LATEST_URL = "https://registry.npmjs.org/@buyan14%2Fagentfleet/latest"
DEFAULT_CACHE_TTL_SEC = 86_400


def installed_version() -> str:
    """Return the installed ``agentfleet`` distribution version."""

    try:
        return version("agentfleet")
    except PackageNotFoundError:
        from . import __version__ as fallback

        return fallback


def _cache_path() -> Path:
    """Return the JSON cache path for the last registry probe."""

    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".cache"
    path = root / "agentfleet" / "npm_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _semver_key(text: str) -> tuple[int, ...]:
    """Parse a simple ``x.y.z`` prefix for ordering (ignores pre-release suffix)."""

    head = text.split("-", 1)[0].strip()
    parts: list[int] = []
    for piece in head.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest: str, current: str) -> bool:
    """Return whether ``latest`` sorts above ``current``."""

    return _semver_key(latest) > _semver_key(current)


def fetch_npm_latest_version(*, timeout_sec: float = 4.0) -> str | None:
    """GET the latest version string from the npm registry (no cache)."""

    req = urllib.request.Request(
        NPM_LATEST_URL,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    ver = payload.get("version")
    return str(ver).strip() if ver else None


def cached_npm_latest_version(ttl_sec: int = DEFAULT_CACHE_TTL_SEC) -> str | None:
    """Return latest npm version, using a short-lived on-disk cache."""

    path = _cache_path()
    now = time.time()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        cached_ver = data.get("version")
        checked = float(data.get("checked_at", 0.0))
        if isinstance(cached_ver, str) and cached_ver and (now - checked) < ttl_sec:
            return cached_ver

    latest = fetch_npm_latest_version()
    if latest:
        try:
            path.write_text(
                json.dumps({"version": latest, "checked_at": now}),
                encoding="utf-8",
            )
        except OSError:
            pass
    return latest


def npm_upgrade_command() -> list[str]:
    """Return argv for upgrading the global npm package."""

    return ["npm", "install", "-g", f"{NPM_SCOPE_PACKAGE}@latest"]


def run_npm_upgrade(*, dry_run: bool) -> int:
    """Run ``npm install -g`` for this package, or print the command when ``dry_run``."""

    if not shutil.which("npm"):
        print("agentfleet upgrade: npm was not found on PATH. Install Node/npm, then run:")
        print(f"  npm install -g {NPM_SCOPE_PACKAGE}@latest")
        return 1
    cmd = npm_upgrade_command()
    if dry_run:
        print("Would run:", " ".join(cmd))
        return 0
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"agentfleet upgrade: npm exited with status {result.returncode}.")
        return result.returncode
    # Invalidate cache so the next onboarding check sees the new version.
    try:
        _cache_path().unlink(missing_ok=True)
    except OSError:
        pass
    print(f"Upgraded {NPM_SCOPE_PACKAGE}. Run `agentfleet doctor` to verify.")
    return 0
