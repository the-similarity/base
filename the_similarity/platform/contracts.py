"""Unified platform contracts — the canonical object model for every pillar.

This module is the *single source of truth* for the cross-pillar object
model that underpins every surface on the synthetic environment platform:
finance retrieval, synthetic copies generation, worlds simulation, world
events, NL-to-time-series, sweeps, and evaluation. Everything that
persists — registry rows, artifact manifests, scorecard summaries,
scenario definitions, dataset registrations — flows through one of the
dataclasses defined here.

Relationship to :mod:`the_similarity.platform.artifacts`
---------------------------------------------------------
The older :class:`~the_similarity.platform.artifacts.RunArtifact` remains
the on-disk ``artifact.json`` shape for backward compatibility with the
TS worlds runner, the registry, and every adapter that reads files
written before this module existed. ``RunRecord`` (defined here) is a
*strict superset* of ``RunArtifact`` — it adds ``status`` and ``pillar``
fields for the registry / UI, but :meth:`RunRecord.from_run_artifact`
and :meth:`RunRecord.from_dict` both gracefully consume the legacy
shape (missing fields default to ``"succeeded"`` + a ``pillar`` inferred
from ``kind``). The legacy ``artifacts_schema.json`` still validates
``artifact.json`` files; the new ``platform_schema.json`` covers the
full multi-type object model for the TS / API side.

Cross-pillar reuse invariants
-----------------------------
- Every persisted row carries a ``run_id`` (UUID4 hex) that is unique
  across all pillars. The registry indexes on it; any FK reference
  (``ArtifactRecord.run_id``, ``ScorecardSummary.run_id``) points back
  to exactly one :class:`RunRecord`.
- All timestamps are ISO-8601 UTC with seconds precision, produced via
  :func:`the_similarity.platform.artifacts.iso_now`. Strings sort
  lexicographically, which is how the registry implements "newest
  first" without a date column.
- ``config``, ``summary``, ``params``, ``metadata``, ``thresholds``,
  ``details`` dicts must be JSON-serializable. The dataclasses do NOT
  coerce values — non-serializable inputs fail loudly at ``json.dumps``
  rather than silently being stringified.
- Dataclasses are mutable (not ``frozen=True``) so runners can build
  them incrementally. Once a record is *written* (registry row, file on
  disk), consumers MUST treat it as immutable: mutate a field -> mint a
  new ``run_id`` and re-register.
- Enum string values (:class:`RunKind`, :class:`RunStatus`,
  :class:`ScorecardKind`) are frozen wire values. Adding a new member
  is additive; renaming or removing is a breaking change for every
  registry row and TS consumer.

Field-contract freeze warning
-----------------------------
Every field name, type, and default below is part of the platform's
public contract. Changing any of them breaks:
- the SQLite registry (column -> field mapping),
- the HTTP API (Pydantic mirror models),
- the TypeScript consumers (validate against ``platform_schema.json``),
- every ``artifact.json`` already on disk.

Safe changes: add a new *optional* field (with a default), add a new
enum value. Unsafe changes: rename, remove, change the type of, or
flip the optionality of any existing field. When in doubt, open an
RFC in ``obsidian_thesim/topics/platform-contracts.md`` first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

# Re-use the existing primitives from `artifacts.py` so this module does
# not duplicate the ISO-timestamp helper or the UUID factory. Keeping
# those primitives in one place means a future change (e.g. bumping to
# nanosecond precision) only lands once.
from the_similarity.platform.artifacts import (
    RunKind,
    iso_now,
    new_run_id,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    """Lifecycle state of a run row in the registry.

    Inheriting from ``str`` keeps JSON round-tripping trivial and matches
    the pattern used by :class:`RunKind`. The state machine is
    deliberately linear (no retry / cancelled states) for MVP — add new
    members when runners grow the corresponding behavior.

    Members
    -------
    PENDING:
        Row reserved in the registry but the runner has not started
        producing outputs. Used when the UI wants to show a pending
        row ahead of the actual execution.
    RUNNING:
        Runner has started; partial artifacts may exist on disk. UI
        may poll for updates.
    SUCCEEDED:
        Run completed; all artifacts written and ``summary`` populated.
        Default for legacy ``RunArtifact`` rows that predate
        ``status``.
    FAILED:
        Run aborted before completion. ``summary`` should include a
        ``reason`` key if available; consumers must still tolerate a
        missing reason (fail-loud, not cryptic).
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ScorecardKind(str, Enum):
    """Category of a :class:`ScorecardSummary`.

    The six members cover the full evaluation surface across pillars:

    - ``FIDELITY`` / ``PRIVACY`` / ``UTILITY`` mirror the synthetic
      scorecards (see ``the_similarity/synthetic/contracts.py``).
    - ``CONTROLLABILITY`` covers worlds-runner scenario adherence
      (prompt -> observed trajectory match).
    - ``CALIBRATION`` covers forecast-cone coverage quality (P10/P50/
      P90 empirical vs nominal).
    - ``BACKTEST`` covers strategy-level evaluation (hit rate,
      calibration, CRPS over a rolling window).
    """

    FIDELITY = "fidelity"
    PRIVACY = "privacy"
    UTILITY = "utility"
    CONTROLLABILITY = "controllability"
    CALIBRATION = "calibration"
    BACKTEST = "backtest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Map from ``RunKind`` -> default ``pillar`` tag. Used when a legacy
# ``RunArtifact`` (which has no ``pillar`` field) is loaded into a
# ``RunRecord``. The mapping is intentionally coarse: pillar tags are
# free-form strings and callers may override at construction time.
#
# COPIES/SWEEP default to ``"synthetic"`` because the historical copies
# pipeline sits under the synthetic pillar; WORLDS -> ``"worlds"``;
# EVAL -> ``"eval"`` (cross-pillar evaluation is itself a pillar in the
# UI nav). FINANCE/EVENTS/NL_TS map 1:1 to their matching pillar tags.
_DEFAULT_PILLAR_FOR_KIND: Dict[RunKind, str] = {
    RunKind.COPIES: "synthetic",
    RunKind.WORLDS: "worlds",
    RunKind.SWEEP: "synthetic",
    RunKind.EVAL: "eval",
    RunKind.FINANCE: "finance",
    RunKind.EVENTS: "events",
    RunKind.NL_TS: "nl_ts",
    # The personalized setup scanner is a finance-pillar feature — its
    # universe is finance instruments and its outputs (alerts, cones)
    # surface in the finance workstation.
    RunKind.SETUP_SCAN: "finance",
}


def _coerce_kind(value: Any) -> RunKind:
    """Accept either a :class:`RunKind` or its raw string value.

    ``from_dict`` receives JSON-decoded dicts where enums arrive as
    bare strings. We centralise the coercion so every constructor
    gets identical semantics (and the same ``ValueError`` on an
    unknown member).
    """
    if isinstance(value, RunKind):
        return value
    return RunKind(value)


def _coerce_status(value: Any) -> RunStatus:
    """Mirror of :func:`_coerce_kind` for :class:`RunStatus`."""
    if isinstance(value, RunStatus):
        return value
    return RunStatus(value)


def _coerce_scorecard_kind(value: Any) -> ScorecardKind:
    """Mirror of :func:`_coerce_kind` for :class:`ScorecardKind`."""
    if isinstance(value, ScorecardKind):
        return value
    return ScorecardKind(value)


# ---------------------------------------------------------------------------
# RunRecord — the canonical run row
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """The canonical platform run row — superset of legacy ``RunArtifact``.

    Every pillar (finance, synthetic, worlds, events, nl_ts, eval) emits
    instances of this dataclass. The registry persists one row per
    ``run_id`` and the UI lists them by ``created_at`` DESC filtered on
    ``pillar`` or ``kind``.

    Backward compatibility
    ----------------------
    :meth:`from_run_artifact` accepts a legacy
    :class:`~the_similarity.platform.artifacts.RunArtifact` and
    :meth:`from_dict` tolerates the legacy field set (no ``status`` /
    ``pillar`` keys), defaulting ``status`` to ``SUCCEEDED`` and
    ``pillar`` to the mapping in :data:`_DEFAULT_PILLAR_FOR_KIND`.
    ``artifact_paths``/``provenance`` are retained on the optional
    :attr:`artifact_paths` / :attr:`provenance` fields so legacy dicts
    carry through without data loss.
    """

    run_id: str
    kind: RunKind
    config: Dict[str, Any]
    seed: Optional[int]
    status: RunStatus
    summary: Dict[str, Any]
    created_at: str
    pillar: str
    # Preserved from the legacy ``RunArtifact`` shape so round-trips
    # from old ``artifact.json`` files do not drop data. Both default
    # to empty dicts for runs that don't carry disk artifacts.
    artifact_paths: Dict[str, str] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict suitable for ``json.dumps`` or the registry.

        Enum fields serialize to their string value; every other field is
        passed through unchanged. Nested dicts are NOT deep-copied — we
        treat written records as immutable so copying would be wasted
        work on the hot path.
        """
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "config": self.config,
            "seed": self.seed,
            "status": self.status.value,
            "summary": self.summary,
            "created_at": self.created_at,
            "pillar": self.pillar,
            "artifact_paths": self.artifact_paths,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunRecord":
        """Reconstruct a :class:`RunRecord` from a JSON-decoded dict.

        Accepts BOTH the new shape (with ``status`` and ``pillar``) and
        the legacy :class:`RunArtifact` shape. Missing fields are filled
        from conservative defaults:

        - ``status`` -> :attr:`RunStatus.SUCCEEDED` (legacy artifacts
          only existed once their run completed, so this is the
          correct historical assumption).
        - ``pillar`` -> derived from :data:`_DEFAULT_PILLAR_FOR_KIND`.
        - ``artifact_paths`` / ``provenance`` -> empty dicts.

        Unknown keys are ignored (forward compat). Required fields
        (``run_id``, ``kind``, ``config``, ``summary``, ``created_at``)
        missing raises ``KeyError`` — callers must supply them.
        """
        kind = _coerce_kind(d["kind"])
        # Default status/pillar for legacy rows. ``.get`` rather than
        # ``["status"]`` because the legacy shape truly lacks the key.
        status = _coerce_status(d.get("status", RunStatus.SUCCEEDED.value))
        pillar = d.get("pillar") or _DEFAULT_PILLAR_FOR_KIND.get(kind, "unknown")
        return cls(
            run_id=d["run_id"],
            kind=kind,
            config=d["config"],
            seed=d.get("seed"),
            status=status,
            summary=d["summary"],
            created_at=d["created_at"],
            pillar=pillar,
            artifact_paths=d.get("artifact_paths", {}) or {},
            provenance=d.get("provenance", {}) or {},
        )

    # -- legacy interop ----------------------------------------------------

    @classmethod
    def from_run_artifact(
        cls,
        artifact: Any,
        *,
        status: Optional[RunStatus] = None,
        pillar: Optional[str] = None,
    ) -> "RunRecord":
        """Promote a legacy ``RunArtifact`` to a ``RunRecord``.

        Parameters
        ----------
        artifact:
            A :class:`~the_similarity.platform.artifacts.RunArtifact`
            instance. Typed as ``Any`` to avoid a circular import at
            module-load time (``artifacts.py`` imports stay one-way).
        status:
            Override the default :attr:`RunStatus.SUCCEEDED` (legacy
            artifacts were always written post-completion).
        pillar:
            Override the :data:`_DEFAULT_PILLAR_FOR_KIND` lookup.

        Notes
        -----
        The legacy ``artifact_paths`` and ``provenance`` dicts carry
        through unchanged so the resulting record can be re-written as
        an ``artifact.json`` without data loss.
        """
        return cls(
            run_id=artifact.run_id,
            kind=artifact.kind,
            config=artifact.config,
            seed=artifact.seed,
            status=status if status is not None else RunStatus.SUCCEEDED,
            summary=artifact.summary,
            created_at=artifact.created_at,
            pillar=pillar
            if pillar is not None
            else _DEFAULT_PILLAR_FOR_KIND.get(artifact.kind, "unknown"),
            artifact_paths=dict(artifact.artifact_paths),
            provenance=dict(artifact.provenance),
        )


# ---------------------------------------------------------------------------
# ArtifactRecord — file-level metadata
# ---------------------------------------------------------------------------


@dataclass
class ArtifactRecord:
    """File-level metadata for one artifact belonging to a run.

    A :class:`RunRecord` references N artifacts on disk via its
    ``artifact_paths`` dict. :class:`ArtifactRecord` is the *expanded*
    form used by the registry's artifact table and the API's
    ``GET /runs/{run_id}/artifacts`` endpoint — it carries content type,
    size, and optional checksum for integrity verification.

    Fields
    ------
    run_id:
        FK to :class:`RunRecord.run_id`.
    name:
        Logical artifact name (``"scorecard"``, ``"telemetry"``,
        ``"real_parquet"``). Mirrors the key side of
        ``RunRecord.artifact_paths``.
    path:
        Relative to the run directory. Kept relative so runs stay
        portable when moved / rehosted.
    content_type:
        MIME-ish descriptor (``"application/json"``, ``"text/csv"``,
        ``"application/x-parquet"``, ``"application/x-jsonl"``).
        Consumers dispatch on this to pick a reader.
    size_bytes:
        Optional — runners may omit to avoid an extra ``os.stat`` call.
    checksum:
        Optional SHA-256 hex. Computed lazily because full-file hashes
        are expensive for multi-GB parquet files.
    created_at:
        ISO-8601 UTC; may trail the parent run's ``created_at`` when
        artifacts are written incrementally.
    """

    run_id: str
    name: str
    path: str
    content_type: str
    created_at: str
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict representation — straight field pass-through."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArtifactRecord":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            run_id=d["run_id"],
            name=d["name"],
            path=d["path"],
            content_type=d["content_type"],
            created_at=d["created_at"],
            size_bytes=d.get("size_bytes"),
            checksum=d.get("checksum"),
        )


# ---------------------------------------------------------------------------
# ScorecardSummary — condensed scorecard row
# ---------------------------------------------------------------------------


@dataclass
class ScorecardSummary:
    """Condensed scorecard row indexed by the registry.

    The full scorecard (raw metric tensors, nested report objects)
    stays on disk as an artifact — see the ``the_similarity/synthetic``
    module's ``Scorecard`` dataclass. :class:`ScorecardSummary` is the
    *row-level* record the UI grids over.

    Fields
    ------
    run_id:
        FK to :class:`RunRecord.run_id`. One run may emit multiple
        scorecards (e.g. fidelity + privacy + utility for a copies
        run); the UI groups them by ``run_id`` and ``kind``.
    kind:
        :class:`ScorecardKind` — chooses the visual category and the
        set of thresholds applied.
    overall_score:
        Optional aggregate in ``[0, 1]``. ``None`` when the scorecard
        does not normalize (e.g. raw backtest CRPS).
    passed:
        Optional pass/fail result of applying ``thresholds`` to the
        full scorecard. ``None`` when no gate was configured.
    thresholds:
        Numeric thresholds used for the gate (``{"ks_max": 0.1,
        ...}``). Must be JSON-serializable.
    details:
        Small nested metric snapshot — headline values only. Full
        detail lives in the on-disk artifact.
    """

    run_id: str
    kind: ScorecardKind
    thresholds: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    overall_score: Optional[float] = None
    passed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict; enum -> string value."""
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "thresholds": self.thresholds,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScorecardSummary":
        """Reconstruct from a JSON-decoded dict."""
        return cls(
            run_id=d["run_id"],
            kind=_coerce_scorecard_kind(d["kind"]),
            overall_score=d.get("overall_score"),
            passed=d.get("passed"),
            thresholds=d.get("thresholds", {}) or {},
            details=d.get("details", {}) or {},
        )


# ---------------------------------------------------------------------------
# Provenance — canonical reproducibility record (extended)
# ---------------------------------------------------------------------------


@dataclass
class Provenance:
    """Platform-level reproducibility record, superset of the synthetic shape.

    Mirrors :class:`the_similarity.synthetic.contracts.Provenance` but
    adds an ``env`` block for the runtime environment the run was
    produced in. Old synthetic provenance dicts (without ``env``)
    continue to load: :meth:`from_dict` treats ``env`` as optional and
    defaults to an empty dict.

    Fields
    ------
    source_id:
        Identifier for the source dataset/corpus. Optional — worlds
        and eval runs don't have a single source.
    generator_name:
        Name of the generator / runner (``"gaussian_copula"``,
        ``"the-similarity-fractal-headless"``, ``"analogue_search"``).
    generator_version:
        Semantic version bumped whenever output distribution changes.
    seed:
        RNG seed used. Optional for runs where a seed is not
        meaningful.
    created_at:
        ISO-8601 UTC timestamp.
    params:
        Free-form generator hyperparameters. Must be JSON-serializable.
    env:
        Runtime environment record. Expected keys: ``python`` (e.g.
        ``"3.12.4"``), ``node`` (``"20.11.0"`` or ``None`` when the
        run is pure Python), ``platform`` (e.g. ``"darwin-arm64"``),
        ``git_sha`` (commit hash or ``None`` in dev trees). The dict
        is free-form so new keys can be added without a version bump.
    """

    generator_name: str
    generator_version: str
    created_at: str
    source_id: Optional[str] = None
    seed: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict; all fields pass through unchanged."""
        return {
            "source_id": self.source_id,
            "generator_name": self.generator_name,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "created_at": self.created_at,
            "params": self.params,
            "env": self.env,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Provenance":
        """Reconstruct a :class:`Provenance` from a JSON-decoded dict.

        Accepts BOTH the legacy synthetic shape (no ``env``) and the new
        extended shape. ``source_id`` is optional (worlds / eval runs
        lack one) — old synthetic dicts always carried it but we tolerate
        its absence here. Unknown keys (e.g. the worlds runner's
        ``scenario`` / ``scenario_name``) are preserved into ``params``
        ONLY if explicitly provided there; stray top-level keys are
        dropped to keep the canonical shape clean.
        """
        return cls(
            source_id=d.get("source_id"),
            generator_name=d["generator_name"],
            # Support legacy worlds runner provenance which used
            # ``version`` rather than ``generator_version``.
            generator_version=d.get("generator_version") or d.get("version", ""),
            seed=d.get("seed"),
            created_at=d["created_at"],
            params=d.get("params", {}) or {},
            env=d.get("env", {}) or {},
        )


# ---------------------------------------------------------------------------
# ScenarioSpec — world / simulation scenario definition
# ---------------------------------------------------------------------------


@dataclass
class ScenarioSpec:
    """Scenario definition for worlds / simulation pillars.

    Scenarios are registered once and referenced by ``scenario_id``
    from :class:`RunRecord.config`. The same scenario may run with
    different seeds / parameter sweeps.

    Fields
    ------
    scenario_id:
        Stable ID (e.g. ``"small_village_v1"``). Used as FK from run
        configs.
    name:
        Human-readable name for UI display.
    version:
        Semantic version; bump when engine behavior changes.
    engine:
        Engine identifier (``"small_village"``, ``"queue.mm1"``,
        ``"boom_bust"``). The worlds runner dispatches on this.
    params:
        Default parameters; run configs override selectively.
    metadata:
        Free-form tags for filtering / UI (authors, references,
        tags). Must be JSON-serializable.
    """

    scenario_id: str
    name: str
    version: str
    engine: str
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioSpec":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            scenario_id=d["scenario_id"],
            name=d["name"],
            version=d["version"],
            engine=d["engine"],
            params=d.get("params", {}) or {},
            metadata=d.get("metadata", {}) or {},
        )


# ---------------------------------------------------------------------------
# DatasetSpec — dataset registration row
# ---------------------------------------------------------------------------


@dataclass
class DatasetSpec:
    """Dataset registration row — one per real or synthetic corpus.

    Datasets are the nouns the platform operates on: load -> index ->
    retrieve / train / backtest. :class:`DatasetSpec` is the *row* the
    UI grids over; the actual bulk data lives on disk under ``source``.

    Fields
    ------
    dataset_id:
        Stable ID (e.g. ``"spy-2020-2024"``, ``"synthetic:abc123"``).
    name:
        Human-readable display name.
    version:
        Semantic version (``"v1.0"``, ``"2024-04-15"``).
    source:
        Filesystem path (``"the-similarity-data/equity/spy.parquet"``),
        URL, or the synthetic-run pointer ``"synthetic:<run_id>"``.
    schema_uri:
        Optional URI pointing at a JSON schema describing the dataset
        columns — used by the loader to validate on read.
    n_rows, n_columns:
        Optional row/column counts; populated lazily after a scan.
    checksum:
        Optional SHA-256 hex of the source file(s).
    metadata:
        Free-form tags (pillar, tickers, date range, license).
    """

    dataset_id: str
    name: str
    version: str
    source: str
    schema_uri: Optional[str] = None
    n_rows: Optional[int] = None
    n_columns: Optional[int] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetSpec":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            dataset_id=d["dataset_id"],
            name=d["name"],
            version=d["version"],
            source=d["source"],
            schema_uri=d.get("schema_uri"),
            n_rows=d.get("n_rows"),
            n_columns=d.get("n_columns"),
            checksum=d.get("checksum"),
            metadata=d.get("metadata", {}) or {},
        )


# ---------------------------------------------------------------------------
# Setup scanner v1 — Setup, Feedback, ScanResult
# ---------------------------------------------------------------------------
#
# These three dataclasses are the contract Worktrees B (delivery), C
# (frontend), and D (public surfaces) mock against. The shape is frozen
# for v1 — additive changes only. See
# ``vision/setup_scanner_schema_contract.md`` for the wire-level
# specification.


@dataclass
class Setup:
    """A user-defined chart region that drives the cross-instrument scanner.

    A setup is owned by exactly one ``user_id`` (string FK; the users
    table itself lives in the API surface, not the engine — we trust the
    caller to supply a non-empty user identifier). The ``region_series``
    is the actual price series the scanner uses as the query window —
    persisting the values (not just indices) keeps the setup stable when
    upstream data sources repaginate or rebuild their indices.

    Lifecycle
    ---------
    Setups are mutable until first scanned, then immutable. The caller
    is responsible for stamping ``created_at`` once at insert and
    bumping ``updated_at`` on every meaningful edit.

    Fields
    ------
    id:
        Stable opaque ID — caller-supplied (e.g.
        ``"setup-<ulid>"``). Idempotent on re-insert via the registry's
        upsert.
    user_id:
        Multi-tenant FK. Must be non-empty.
    name:
        Human display name (``"BTC daily double-bottom"``).
    instrument:
        Symbol the region was drawn on (``"BTCUSDT"``,
        ``"XAUUSD"``).
    timeframe:
        Bar size (``"1h"``, ``"4h"``, ``"1d"``).
    region_start_ts / region_end_ts:
        ISO-8601 UTC bounds of the window (inclusive start, exclusive
        end), useful for UI display and audit trails.
    region_series:
        Float list of close prices (or whatever the user dragged over)
        — the scanner's query window. Length matches the bar count
        between ``region_start_ts`` and ``region_end_ts``.
    created_at / updated_at:
        ISO-8601 UTC.
    """

    id: str
    user_id: str
    name: str
    instrument: str
    timeframe: str
    region_start_ts: str
    region_end_ts: str
    region_series: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict — straight pass-through; ``region_series`` is a list."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "region_start_ts": self.region_start_ts,
            "region_end_ts": self.region_end_ts,
            "region_series": list(self.region_series),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Setup":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            id=d["id"],
            user_id=d["user_id"],
            name=d["name"],
            instrument=d["instrument"],
            timeframe=d["timeframe"],
            region_start_ts=d["region_start_ts"],
            region_end_ts=d["region_end_ts"],
            region_series=list(d.get("region_series", []) or []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class Feedback:
    """Thumbs-up/down feedback the user gave on an alert or analog.

    Persisted from day 1 even when v1 doesn't compute on it — this is
    the goodrun feedback moat per
    ``vision/personalized_setup_scanner.md``. v2 will aggregate these
    rows to derive a per-user goodrun filter.

    Either ``alert_id`` or ``analog_id`` is set (not both); the
    ``kind`` field disambiguates which surface produced the feedback.
    Both are kept as plain strings — the alert/analog rows live in
    other surfaces (alerts in the API, analogs in scan runs) and the
    engine doesn't need to model them to record feedback.

    Fields
    ------
    id:
        Caller-supplied opaque ID (e.g. ``"feedback-<ulid>"``).
    user_id:
        Multi-tenant FK. Must match the ``setup_id``'s owner.
    setup_id:
        FK to :class:`Setup.id`. Cascade-deletes with the setup.
    alert_id:
        FK-shaped string referencing the alert this feedback is for.
        ``None`` when ``kind == "analog"``.
    analog_id:
        FK-shaped string referencing the analog this feedback is for.
        ``None`` when ``kind == "alert"``.
    kind:
        Discriminator — ``"alert"`` or ``"analog"``.
    thumb:
        ``"up"`` or ``"down"``.
    free_text:
        Optional free-form note (max ~1KB; not enforced here, but the
        API layer should clamp).
    created_at:
        ISO-8601 UTC.
    """

    id: str
    user_id: str
    setup_id: str
    kind: str
    thumb: str
    alert_id: Optional[str] = None
    analog_id: Optional[str] = None
    free_text: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict — every field passes through unchanged."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "setup_id": self.setup_id,
            "alert_id": self.alert_id,
            "analog_id": self.analog_id,
            "kind": self.kind,
            "thumb": self.thumb,
            "free_text": self.free_text,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feedback":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            id=d["id"],
            user_id=d["user_id"],
            setup_id=d["setup_id"],
            alert_id=d.get("alert_id"),
            analog_id=d.get("analog_id"),
            kind=d["kind"],
            thumb=d["thumb"],
            free_text=d.get("free_text"),
            created_at=d.get("created_at", ""),
        )


@dataclass
class InstrumentScanResult:
    """One instrument's slice of a :class:`ScanResult`.

    Fields
    ------
    instrument:
        Symbol scanned (``"BTCUSDT"``, ``"EURUSD"``).
    analogs:
        List of dicts — each is the JSON-serialized form of a
        :class:`the_similarity.core.scorer.MatchResult` (start_idx,
        end_idx, dates, confidence_score, score_breakdown). Kept as
        plain dicts (not the dataclass) so this record can be
        registry-persisted via JSON without an engine import on the
        consumer side.
    forecast:
        JSON-serialized forecast cone — keys: ``bars`` (int),
        ``percentiles`` (list[int]),
        ``curves`` (dict[int, list[float]]). ``None`` when there were
        not enough analogs to project.
    error:
        If the per-instrument scan raised, the error message is recorded
        here so the top-level scan can still succeed partially.
        ``None`` on success.
    """

    instrument: str
    analogs: list = field(default_factory=list)
    forecast: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict."""
        return {
            "instrument": self.instrument,
            "analogs": list(self.analogs),
            "forecast": self.forecast,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstrumentScanResult":
        """Reconstruct from a JSON-decoded dict."""
        return cls(
            instrument=d["instrument"],
            analogs=list(d.get("analogs", []) or []),
            forecast=d.get("forecast"),
            error=d.get("error"),
        )


@dataclass
class ScanResult:
    """The output of one cross-instrument scanner run.

    A :class:`ScanResult` is what the API serializes to clients and
    what the registry persists (under
    :attr:`RunKind.SETUP_SCAN`). It carries:

    - ``setup_id`` / ``user_id`` — provenance link back to the originating
      :class:`Setup`.
    - ``per_instrument`` — full per-symbol breakdown.
    - ``top_n`` — flat ranked list of the highest-confidence analogs
      across the entire universe (each item is the same dict shape as
      ``InstrumentScanResult.analogs[i]`` plus an ``instrument`` key).

    Lifecycle
    ---------
    Mutated by the scanner during a run; immutable once persisted.
    """

    setup_id: str
    user_id: str
    created_at: str
    per_instrument: list = field(default_factory=list)
    top_n: list = field(default_factory=list)
    universe: list = field(default_factory=list)
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict; nested ``InstrumentScanResult``s flatten to dicts."""
        return {
            "setup_id": self.setup_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "per_instrument": [
                r.to_dict() if isinstance(r, InstrumentScanResult) else r
                for r in self.per_instrument
            ],
            "top_n": list(self.top_n),
            "universe": list(self.universe),
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScanResult":
        """Reconstruct from a JSON-decoded dict."""
        per_instrument_raw = d.get("per_instrument", []) or []
        per_instrument = [
            InstrumentScanResult.from_dict(r) if isinstance(r, dict) else r
            for r in per_instrument_raw
        ]
        return cls(
            setup_id=d["setup_id"],
            user_id=d["user_id"],
            created_at=d["created_at"],
            per_instrument=per_instrument,
            top_n=list(d.get("top_n", []) or []),
            universe=list(d.get("universe", []) or []),
            run_id=d.get("run_id"),
        )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------


__all__ = [
    "ArtifactRecord",
    "DatasetSpec",
    "Feedback",
    "InstrumentScanResult",
    "Provenance",
    "RunRecord",
    "RunStatus",
    "ScanResult",
    "ScenarioSpec",
    "ScorecardKind",
    "ScorecardSummary",
    "Setup",
    "iso_now",
    "new_run_id",
]
