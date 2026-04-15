"""Catalogue validator for the canonical benchmark slice spec.

Purpose
-------
Enforce the structural invariants of ``catalogue.yaml`` plus the regime
bucket files and cross-asset pair files.  Runs in CI and via
``python -m research.autoresearch.slices.validate``.

Invariants enforced
-------------------
1. No duplicate slice IDs in the catalogue.
2. ``start`` < ``end`` on every slice.
3. ``end`` is not in the future (relative to the machine clock at run
   time).  A slice that ends tomorrow is almost certainly a fabricated
   window; we force the author to mark it ``missing_data: true`` or fix
   the date.
4. ``regime_class`` is one of the enum values declared at the top of
   ``catalogue.yaml``.
5. For each slice NOT marked ``missing_data: true``, the resolved
   ``dataset_path`` exists on disk under ``data_root_default`` (the
   runner honours a CLI override for alternate roots).  Slices marked
   ``missing_data: true`` are allowed to be unresolvable — downstream
   runners are expected to synth-fallback.
6. Each regime YAML file lists only slice IDs that exist in the
   catalogue AND whose ``regime_class`` matches the filename.
7. Each cross-asset pair references slice IDs that exist in the
   catalogue, date windows overlap (under the declared join rule), and
   ``join_rule`` is one of the supported values.
8. No ``pair_id`` collisions across cross-asset files.

Exit contract
-------------
- Exit 0  : no violations (``missing_data: true`` entries are skipped
  for file-existence checks but still checked for date validity,
  collisions, and regime consistency).
- Exit 1  : one or more violations; every violation is printed before
  exit so CI logs show the full set.

This module is intentionally dependency-light (PyYAML only) so it can
run in minimal CI containers.
"""
from __future__ import annotations

# Standard-lib-only imports keep the validator cheap to run in CI;
# PyYAML is already a transitive dependency of the rest of autoresearch.
import datetime as _dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Paths.  Resolved relative to repo root so the validator works from both
# `python -m research.autoresearch.slices.validate` and a direct
# `python research/autoresearch/slices/validate.py` invocation.
# ---------------------------------------------------------------------------

# Two levels up from this file (.../research/autoresearch/slices/validate.py)
# reaches research/autoresearch; three levels reaches the repo root.
_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[2]

CATALOGUE_PATH = _THIS_DIR / "catalogue.yaml"
REGIMES_DIR = _THIS_DIR / "regimes"
CROSS_ASSET_DIR = _THIS_DIR / "cross_asset"

# Join rules that the downstream runner implements — the validator
# rejects pair files that declare anything else so typos fail loudly.
SUPPORTED_JOIN_RULES = {"intersection", "union", "left_anchor", "right_anchor"}

# Minimum bar count default — may be overridden per-slice.  The validator
# itself cannot count parquet rows (would require pyarrow as a hard dep),
# so this is surfaced as metadata only; bar-count enforcement belongs in
# the runner where pyarrow is already imported.
DEFAULT_MIN_BARS = 200


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class SliceEntry:
    """In-memory view of a catalogue slice, post-parse.

    Only the fields that the validator or loader needs are materialised;
    unknown keys are preserved in ``raw`` so the loader can expose them
    without duplicating the YAML schema here.
    """

    id: str
    asset: str
    asset_class: str
    dataset_path: str
    timeframe: str
    start: str
    end: str
    regime_class: str
    description: str = ""
    notes: str = ""
    min_bars: int = DEFAULT_MIN_BARS
    missing_data: bool = False
    status: str = "active"
    successor_id: str | None = None
    source_bench_lane: str = ""
    # Any extra keys the YAML contained — kept verbatim for forward-compat.
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Catalogue:
    """Loaded catalogue plus enumerated regime/asset classes."""

    version: int
    schema_revision: int
    data_root_default: str
    regime_classes: list[str]
    asset_classes: list[str]
    slices: list[SliceEntry]

    def by_id(self) -> dict[str, SliceEntry]:
        """Return ``{slice_id: SliceEntry}`` for fast lookup."""
        return {s.id: s for s in self.slices}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _coerce_slice(raw: dict[str, Any]) -> SliceEntry:
    """Build a ``SliceEntry`` from a raw YAML dict.

    Missing optional fields get sensible defaults; missing required
    fields raise ``KeyError`` which the outer loader converts to a
    violation message so one malformed entry does not abort the whole
    validation pass.
    """
    return SliceEntry(
        id=raw["id"],
        asset=raw["asset"],
        asset_class=raw.get("asset_class", ""),
        dataset_path=raw["dataset_path"],
        timeframe=raw.get("timeframe", "1d"),
        start=str(raw["start"]),
        end=str(raw["end"]),
        regime_class=raw["regime_class"],
        description=raw.get("description", ""),
        notes=raw.get("notes", ""),
        min_bars=int(raw.get("min_bars", DEFAULT_MIN_BARS)),
        missing_data=bool(raw.get("missing_data", False)),
        status=raw.get("status", "active"),
        successor_id=raw.get("successor_id"),
        source_bench_lane=raw.get("source_bench_lane", ""),
        raw=dict(raw),
    )


def load_catalogue(path: str | Path | None = None) -> Catalogue:
    """Parse ``catalogue.yaml`` into a ``Catalogue`` dataclass.

    Raises ``FileNotFoundError`` if the catalogue is missing — that is
    a structural failure, not a validation failure, so it aborts early.

    ``path`` defaults to the module-level ``CATALOGUE_PATH``.  We resolve
    it lazily (inside the function body) so unit tests can
    ``monkeypatch.setattr(V, "CATALOGUE_PATH", ...)`` without fighting
    Python's default-arg capture semantics.
    """
    p = Path(path) if path is not None else Path(CATALOGUE_PATH)
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    slices: list[SliceEntry] = []
    for s in raw.get("slices", []):
        slices.append(_coerce_slice(s))

    return Catalogue(
        version=int(raw.get("version", 1)),
        schema_revision=int(raw.get("schema_revision", 1)),
        data_root_default=raw.get("data_root_default", "the-similarity-data/data"),
        regime_classes=list(raw.get("regime_classes", [])),
        asset_classes=list(raw.get("asset_classes", [])),
        slices=slices,
    )


def load_regime_file(path: Path) -> dict[str, Any]:
    """Parse a single ``regimes/<class>.yaml`` file."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_pair_file(path: Path) -> dict[str, Any]:
    """Parse a single ``cross_asset/*.yaml`` file."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Validators — each returns a list of violation strings.  An empty list
# means "this check passed".
# ---------------------------------------------------------------------------

def _parse_iso(date_str: str) -> _dt.date | None:
    """Strict ISO-date parser.  Returns None on failure (caller reports).
    We use ``datetime.date.fromisoformat`` — it rejects anything that is
    not YYYY-MM-DD, which is exactly the strictness we want.
    """
    try:
        return _dt.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def validate_catalogue_structure(
    cat: Catalogue,
    *,
    data_root: Path | None = None,
    today: _dt.date | None = None,
    check_data_files: bool = False,
) -> list[str]:
    """Enforce invariants 1-5 on the catalogue itself.

    ``data_root`` and ``today`` are injectable so unit tests can pin
    them to deterministic values without touching the filesystem clock.

    ``check_data_files`` gates invariant 5 (dataset_path must exist).
    Parquet data files are outside the git repo (catalog-based, refreshed
    by GitHub Actions), so worktrees created via ``git worktree add`` do
    not replicate them.  CI runs the validator without data; nightly
    data-pipeline jobs (and local runs with the data mount present) can
    pass ``check_data_files=True`` via ``--check-data``.
    """
    violations: list[str] = []
    today = today or _dt.date.today()
    data_root = data_root or (REPO_ROOT / cat.data_root_default)

    allowed_regimes = set(cat.regime_classes)

    # 1. Duplicate IDs ------------------------------------------------------
    seen_ids: dict[str, int] = {}
    for entry in cat.slices:
        seen_ids[entry.id] = seen_ids.get(entry.id, 0) + 1
    for slice_id, n in seen_ids.items():
        if n > 1:
            violations.append(
                f"duplicate slice id '{slice_id}' appears {n} times in catalogue"
            )

    for entry in cat.slices:
        # 2/3. Date ordering + not-in-future ---------------------------------
        start = _parse_iso(entry.start)
        end = _parse_iso(entry.end)
        if start is None:
            violations.append(f"{entry.id}: start '{entry.start}' is not ISO YYYY-MM-DD")
        if end is None:
            violations.append(f"{entry.id}: end '{entry.end}' is not ISO YYYY-MM-DD")
        if start and end and not (start < end):
            violations.append(
                f"{entry.id}: start ({entry.start}) must be strictly < end ({entry.end})"
            )
        if end and end > today:
            violations.append(
                f"{entry.id}: end {entry.end} is after today {today.isoformat()}"
            )

        # 4. Regime enum ----------------------------------------------------
        if entry.regime_class not in allowed_regimes:
            violations.append(
                f"{entry.id}: regime_class '{entry.regime_class}' not in "
                f"allowed set {sorted(allowed_regimes)}"
            )

        # 5. File existence (skip missing_data entries) ---------------------
        # Intentionally NOT fatal when missing_data=True — synth fallback.
        # Also gated on check_data_files: parquet data lives outside the
        # git repo and is absent in minimal CI + fresh worktrees.
        if check_data_files and not entry.missing_data:
            resolved = (data_root / entry.dataset_path).resolve()
            if not resolved.exists():
                violations.append(
                    f"{entry.id}: dataset_path does not exist — "
                    f"resolved={resolved} (mark missing_data: true if intentional)"
                )

        # Deprecated status must have a successor pointer --------------------
        if entry.status == "deprecated" and not entry.successor_id:
            violations.append(
                f"{entry.id}: status=deprecated requires successor_id"
            )

    return violations


def validate_regime_files(
    cat: Catalogue,
    regimes_dir: Path | None = None,
) -> list[str]:
    """Enforce invariant 6: regime YAML files must agree with the catalogue.

    For each `<regime>.yaml`:
      * filename stem must be in catalogue.regime_classes
      * every slice_id must exist in the catalogue
      * that slice's regime_class must equal the filename stem

    ``regimes_dir`` defaults to the module-level ``REGIMES_DIR`` resolved
    at call time (NOT at function-definition time).  This matters because
    unit tests ``monkeypatch.setattr(V, "REGIMES_DIR", tmp_dir)`` to point
    the validator at a synthetic tree — Python binds default args once at
    def-time, so a literal ``regimes_dir: Path = REGIMES_DIR`` default
    would capture the repo path forever and ignore monkeypatches.
    """
    violations: list[str] = []
    by_id = cat.by_id()
    allowed_regimes = set(cat.regime_classes)

    # Late-bind the default to honor test monkeypatches (see docstring).
    if regimes_dir is None:
        regimes_dir = REGIMES_DIR

    if not regimes_dir.exists():
        violations.append(f"regimes directory missing: {regimes_dir}")
        return violations

    for yaml_path in sorted(regimes_dir.glob("*.yaml")):
        stem = yaml_path.stem
        if stem not in allowed_regimes:
            violations.append(
                f"regimes/{yaml_path.name}: filename stem '{stem}' is not a "
                f"declared regime class {sorted(allowed_regimes)}"
            )
            continue

        data = load_regime_file(yaml_path)
        declared = data.get("regime_class")
        if declared != stem:
            violations.append(
                f"regimes/{yaml_path.name}: regime_class field '{declared}' "
                f"does not match filename stem '{stem}'"
            )

        slice_ids = data.get("slice_ids", []) or []
        for sid in slice_ids:
            entry = by_id.get(sid)
            if entry is None:
                violations.append(
                    f"regimes/{yaml_path.name}: slice_id '{sid}' not in catalogue"
                )
            elif entry.regime_class != stem:
                violations.append(
                    f"regimes/{yaml_path.name}: slice '{sid}' has regime_class "
                    f"'{entry.regime_class}' in catalogue, file expects '{stem}'"
                )
    return violations


def validate_pair_files(
    cat: Catalogue,
    cross_asset_dir: Path | None = None,
) -> list[str]:
    """Enforce invariant 7/8: cross-asset pair files are internally consistent.

    * Both legs exist in the catalogue.
    * Declared ``join_rule`` is in ``SUPPORTED_JOIN_RULES``.
    * Date windows overlap (non-empty intersection).
    * ``pair_id`` is unique across all files.

    ``cross_asset_dir`` defaults to the module-level ``CROSS_ASSET_DIR``
    resolved at call time.  See ``validate_regime_files`` for why a
    literal ``= CROSS_ASSET_DIR`` default would break test monkeypatches.
    """
    violations: list[str] = []
    by_id = cat.by_id()
    seen_pair_ids: dict[str, str] = {}

    # Late-bind the default to honor test monkeypatches (see docstring).
    if cross_asset_dir is None:
        cross_asset_dir = CROSS_ASSET_DIR

    if not cross_asset_dir.exists():
        # Missing cross_asset dir is non-fatal — author may not have added
        # pairs yet.  We just skip the checks.
        return violations

    for yaml_path in sorted(cross_asset_dir.glob("*.yaml")):
        data = load_pair_file(yaml_path)
        if not data:
            continue

        pid = data.get("pair_id")
        if not pid:
            violations.append(f"cross_asset/{yaml_path.name}: missing pair_id")
            continue

        if pid in seen_pair_ids:
            violations.append(
                f"cross_asset/{yaml_path.name}: duplicate pair_id '{pid}' "
                f"(already in {seen_pair_ids[pid]})"
            )
        seen_pair_ids[pid] = yaml_path.name

        left_id = data.get("left")
        right_id = data.get("right")
        left = by_id.get(left_id) if left_id else None
        right = by_id.get(right_id) if right_id else None
        if left is None:
            violations.append(
                f"cross_asset/{yaml_path.name}: left '{left_id}' not in catalogue"
            )
        if right is None:
            violations.append(
                f"cross_asset/{yaml_path.name}: right '{right_id}' not in catalogue"
            )

        join_rule = data.get("join_rule")
        if join_rule not in SUPPORTED_JOIN_RULES:
            violations.append(
                f"cross_asset/{yaml_path.name}: join_rule '{join_rule}' not "
                f"in {sorted(SUPPORTED_JOIN_RULES)}"
            )

        # Date-overlap check ---------------------------------------------
        if left and right:
            ls, le = _parse_iso(left.start), _parse_iso(left.end)
            rs, re_ = _parse_iso(right.start), _parse_iso(right.end)
            if ls and le and rs and re_:
                overlap_start = max(ls, rs)
                overlap_end = min(le, re_)
                if overlap_start > overlap_end:
                    violations.append(
                        f"cross_asset/{yaml_path.name}: no date overlap — "
                        f"left=[{left.start}..{left.end}] "
                        f"right=[{right.start}..{right.end}]"
                    )
    return violations


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def run_all_validators(
    *,
    data_root: Path | None = None,
    today: _dt.date | None = None,
    check_data_files: bool = False,
) -> list[str]:
    """Run every validator and concatenate the violations."""
    cat = load_catalogue()
    violations: list[str] = []
    violations.extend(
        validate_catalogue_structure(
            cat,
            data_root=data_root,
            today=today,
            check_data_files=check_data_files,
        )
    )
    violations.extend(validate_regime_files(cat))
    violations.extend(validate_pair_files(cat))
    return violations


def main(argv: list[str] | None = None) -> int:
    """Entry point used by CI and direct invocation.

    ``--check-data`` turns on invariant 5 (dataset_path must exist on
    disk).  Off by default because fresh git worktrees do not replicate
    the parquet data package.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate the canonical benchmark slice catalogue."
    )
    parser.add_argument(
        "--check-data",
        action="store_true",
        help="Also check that each slice's dataset_path exists on disk "
        "(skipped for missing_data: true entries).",
    )
    args = parser.parse_args(argv)

    violations = run_all_validators(check_data_files=args.check_data)
    if not violations:
        print("[slices.validate] OK — catalogue + regime + pair files pass invariants")
        return 0
    print(f"[slices.validate] FAILED — {len(violations)} violation(s):")
    for v in violations:
        print(f"  - {v}")
    return 1


if __name__ == "__main__":  # pragma: no cover — exercised via CLI
    sys.exit(main(sys.argv[1:]))
