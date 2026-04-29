#!/usr/bin/env python3
"""
Validate the agent harness documentation.

This checker keeps the harness legible to autonomous workers. It intentionally
focuses on structural guarantees rather than prose quality: required files
exist, index links resolve, execution plans have the fields agents need, and
known hot files are represented in the harness docs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_ROOT = REPO_ROOT / "docs" / "agent-harness"

REQUIRED_FILES = [
    HARNESS_ROOT / "README.md",
    HARNESS_ROOT / "operating-model.md",
    HARNESS_ROOT / "agent-legibility.md",
    HARNESS_ROOT / "golden-principles.md",
    HARNESS_ROOT / "quality-scorecard.md",
    HARNESS_ROOT / "exec-plans" / "README.md",
    HARNESS_ROOT / "templates" / "exec-plan-template.md",
]

HOT_FILES = [
    "obsidian_thesim/_MOC.md",
    ".gitignore",
    "CHANGELOG.md",
    "pyproject.toml",
]

EXEC_PLAN_REQUIRED_HEADINGS = [
    "## Goal",
    "## Non-Goals",
    "## Scope",
    "## Agent Task Slices",
    "## Acceptance Criteria",
    "## Validation",
    "## Risks And Rollback",
    "## Progress Log",
]


@dataclass
class Finding:
    """A single harness validation failure."""

    path: Path
    message: str

    def format(self) -> str:
        relative = self.path.relative_to(REPO_ROOT)
        return f"{relative}: {self.message}"


def main() -> int:
    """Run all harness checks and print agent-actionable findings."""
    findings: list[Finding] = []
    findings.extend(check_required_files())
    findings.extend(check_markdown_links())
    findings.extend(check_hot_file_mentions())
    findings.extend(check_quality_scorecard())
    findings.extend(check_active_exec_plans())

    if findings:
        print("Agent harness check failed:\n")
        for finding in findings:
            print(f"- {finding.format()}")
        print("\nFix the harness docs or update this checker if the invariant changed.")
        return 1

    print("Agent harness check passed.")
    return 0


def check_required_files() -> list[Finding]:
    """Ensure the core harness map exists."""
    findings: list[Finding] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            findings.append(Finding(path, "required harness file is missing"))
    return findings


def check_markdown_links() -> list[Finding]:
    """Validate relative Markdown links inside the harness directory."""
    findings: list[Finding] = []
    for path in HARNESS_ROOT.rglob("*.md"):
        text = path.read_text()
        for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if should_skip_link(target):
                continue
            target_path = (path.parent / target.split("#", 1)[0]).resolve()
            if not target_path.exists():
                findings.append(
                    Finding(path, f"link '{label}' points to missing path: {target}")
                )
    return findings


def should_skip_link(target: str) -> bool:
    """Return whether a Markdown link target is intentionally external."""
    return (
        target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("#")
        or target.startswith("mailto:")
        or target.startswith("[[")
    )


def check_hot_file_mentions() -> list[Finding]:
    """Ensure shared-file conflict rules are visible in the harness."""
    readme = HARNESS_ROOT / "README.md"
    if not readme.exists():
        return []

    text = readme.read_text()
    findings: list[Finding] = []
    for hot_file in HOT_FILES:
        if hot_file not in text:
            findings.append(
                Finding(readme, f"shared hot file '{hot_file}' is not mentioned")
            )
    return findings


def check_quality_scorecard() -> list[Finding]:
    """Ensure the scorecard remains a real scorecard."""
    path = HARNESS_ROOT / "quality-scorecard.md"
    if not path.exists():
        return []

    text = path.read_text()
    findings: list[Finding] = []
    for heading in ["| Area | Grade | Evidence | Next Upgrade |", "## Update Rules"]:
        if heading not in text:
            findings.append(Finding(path, f"missing required scorecard section: {heading}"))
    return findings


def check_active_exec_plans() -> list[Finding]:
    """Validate active execution plans if any exist."""
    active_dir = HARNESS_ROOT / "exec-plans" / "active"
    if not active_dir.exists():
        return []

    findings: list[Finding] = []
    for path in sorted(active_dir.glob("*.md")):
        text = path.read_text()
        findings.extend(check_plan_metadata(path, text))
        for heading in EXEC_PLAN_REQUIRED_HEADINGS:
            if heading not in text:
                findings.append(Finding(path, f"missing required heading: {heading}"))
    return findings


def check_plan_metadata(path: Path, text: str) -> list[Finding]:
    """Validate metadata fields for an active execution plan."""
    findings: list[Finding] = []
    required_prefixes = ["Status:", "Owner:", "Created:", "Last Updated:"]
    for prefix in required_prefixes:
        if not re.search(rf"^{re.escape(prefix)}\s+\S+", text, flags=re.MULTILINE):
            findings.append(Finding(path, f"missing metadata field: {prefix}"))

    status_match = re.search(r"^Status:\s+(\S+)", text, flags=re.MULTILINE)
    if status_match and status_match.group(1).lower() != "active":
        findings.append(Finding(path, "active plan must have 'Status: active'"))
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
