"""End-to-end NL-to-time-series demo — parse narratives, compile trajectories, register.

Demonstrates the v1 NL-to-time-series pipeline:

1. Define three inline natural-language narratives describing market scenarios.
2. Parse each narrative with a keyword-based parser into a NarrativeSchema
   (direction, magnitude, duration, volatility regime, catalyst keywords).
3. Compile each parsed schema into a synthetic trajectory using a simple
   piecewise-linear + noise compiler.
4. Register each compiled trajectory in a temporary platform registry as a
   RunRecord with kind=NL_TS.

Usage
-----
    python examples/nl_to_timeseries_demo.py

Design notes
------------
- v1 uses *keyword parsing*, not an LLM. The parser scans for directional
  words ("crash", "rally", "sideways"), magnitude modifiers ("sharp",
  "moderate"), and volatility cues ("volatile", "calm"). This is intentionally
  naive — the value is the end-to-end scaffold (schema, compiler, registry),
  not parsing quality. See ``vision/nl_to_timeseries.md``.
- All data is inline — no external files, no services, no API keys.
- Uses a temporary SQLite registry so the demo leaves no side effects.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — make the example runnable from the repo root without install.
# ---------------------------------------------------------------------------
_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy is required. Install with: pip install numpy")
    sys.exit(1)

try:
    from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
    from the_similarity.platform.contracts import RunRecord, RunStatus
    from the_similarity.platform.registry import RunRegistry
except ImportError as exc:
    print(f"ERROR: Could not import platform modules: {exc}")
    print("Run from the repo root or install the_similarity package.")
    sys.exit(1)


# =========================================================================
# 1. NarrativeSchema — structured output of parsing
# =========================================================================


@dataclass
class NarrativeSchema:
    """Structured representation of a natural-language market narrative.

    This is the intermediate representation between raw text and a compiled
    trajectory. The parser fills these fields; the compiler reads them.

    Fields
    ------
    direction:
        Overall price direction: "up", "down", or "sideways".
    magnitude:
        Strength modifier: "sharp" (>10%), "moderate" (3-10%), "mild" (<3%).
    duration_days:
        How many trading days the scenario spans.
    volatility:
        Volatility regime: "high", "normal", or "low".
    catalyst_keywords:
        Keywords extracted from the narrative that triggered parsing decisions.
        Useful for debugging and explainability.
    raw_text:
        The original narrative text, preserved for provenance.
    """

    direction: str  # "up", "down", "sideways"
    magnitude: str  # "sharp", "moderate", "mild"
    duration_days: int
    volatility: str  # "high", "normal", "low"
    catalyst_keywords: List[str] = field(default_factory=list)
    raw_text: str = ""


# =========================================================================
# 2. Keyword parser
# =========================================================================

# Word lists for keyword-based classification. Each list is scanned in order;
# first match wins. This is intentionally crude — v2 will use an LLM.

_DOWN_WORDS = ["crash", "collapse", "plunge", "sell-off", "selloff", "decline",
               "drop", "fall", "bear", "recession", "downturn", "tank"]
_UP_WORDS = ["rally", "surge", "boom", "rise", "climb", "bull", "recovery",
             "rebound", "soar", "breakout", "upturn"]
_SIDEWAYS_WORDS = ["sideways", "range-bound", "flat", "consolidat", "chop",
                   "stagnant", "directionless"]

_SHARP_WORDS = ["sharp", "dramatic", "severe", "extreme", "massive", "violent",
                "crash", "collapse", "plunge", "surge", "soar"]
_MILD_WORDS = ["mild", "slight", "gentle", "gradual", "modest", "minor"]

_HIGH_VOL_WORDS = ["volatile", "turbulent", "chaotic", "wild", "whipsaw",
                   "erratic", "uncertain"]
_LOW_VOL_WORDS = ["calm", "quiet", "stable", "steady", "subdued", "muted"]


def parse_narrative(text: str) -> NarrativeSchema:
    """Parse a natural-language narrative into a NarrativeSchema.

    Algorithm (v1, keyword-based):
    1. Lowercase the text.
    2. Scan for direction words (down > up > sideways > default "sideways").
    3. Scan for magnitude words (sharp > mild > default "moderate").
    4. Extract duration from explicit mentions ("N days/weeks/months") or
       default to 60 trading days.
    5. Scan for volatility cues (high > low > default "normal").
    6. Collect all matched keywords for explainability.

    Parameters
    ----------
    text : str
        Free-form narrative describing a market scenario.

    Returns
    -------
    NarrativeSchema
        Structured parse result.
    """
    lower = text.lower()
    keywords: List[str] = []

    # --- Direction ---
    direction = "sideways"
    for word in _DOWN_WORDS:
        if word in lower:
            direction = "down"
            keywords.append(word)
            break
    if direction == "sideways":
        for word in _UP_WORDS:
            if word in lower:
                direction = "up"
                keywords.append(word)
                break
    if direction not in ("up", "down"):
        for word in _SIDEWAYS_WORDS:
            if word in lower:
                keywords.append(word)
                break

    # --- Magnitude ---
    magnitude = "moderate"
    for word in _SHARP_WORDS:
        if word in lower:
            magnitude = "sharp"
            keywords.append(word)
            break
    if magnitude == "moderate":
        for word in _MILD_WORDS:
            if word in lower:
                magnitude = "mild"
                keywords.append(word)
                break

    # --- Duration ---
    # Look for patterns like "3 months", "60 days", "2 weeks"
    duration_days = 60  # default
    import re

    # Match "N months" -> N * 21 trading days
    m = re.search(r"(\d+)\s*months?", lower)
    if m:
        duration_days = int(m.group(1)) * 21

    # Match "N weeks" -> N * 5 trading days
    m = re.search(r"(\d+)\s*weeks?", lower)
    if m:
        duration_days = int(m.group(1)) * 5

    # Match "N days" (most specific, wins)
    m = re.search(r"(\d+)\s*(?:trading\s+)?days?", lower)
    if m:
        duration_days = int(m.group(1))

    # --- Volatility ---
    volatility = "normal"
    for word in _HIGH_VOL_WORDS:
        if word in lower:
            volatility = "high"
            keywords.append(word)
            break
    if volatility == "normal":
        for word in _LOW_VOL_WORDS:
            if word in lower:
                volatility = "low"
                keywords.append(word)
                break

    # Deduplicate keywords while preserving order
    seen = set()
    unique_kw = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_kw.append(kw)

    return NarrativeSchema(
        direction=direction,
        magnitude=magnitude,
        duration_days=duration_days,
        volatility=volatility,
        catalyst_keywords=unique_kw,
        raw_text=text,
    )


# =========================================================================
# 3. Trajectory compiler
# =========================================================================

# Magnitude -> approximate total return (absolute value, as fraction of 1.0)
_MAGNITUDE_MAP = {
    "sharp": 0.15,
    "moderate": 0.06,
    "mild": 0.02,
}

# Volatility -> daily noise standard deviation (as fraction of price)
_VOLATILITY_MAP = {
    "high": 0.025,
    "normal": 0.012,
    "low": 0.005,
}


def compile_trajectory(
    schema: NarrativeSchema,
    *,
    seed: int = 42,
    start_price: float = 100.0,
) -> np.ndarray:
    """Compile a NarrativeSchema into a synthetic price trajectory.

    Algorithm (v1, piecewise-linear + noise):
    1. Compute the total return from direction + magnitude.
    2. Build a linear drift from start_price to start_price * (1 + return).
    3. Add Gaussian noise scaled by the volatility regime.
    4. Ensure prices stay positive (floor at 1.0).

    The result is intentionally simple — a real compiler would use regime
    models, mean-reversion, volatility clustering, etc. The value here is
    the end-to-end contract (schema -> trajectory -> registry).

    Parameters
    ----------
    schema : NarrativeSchema
        Parsed narrative to compile.
    seed : int
        RNG seed for reproducibility.
    start_price : float
        Initial price level.

    Returns
    -------
    np.ndarray
        Price trajectory of shape ``(duration_days,)``.
    """
    rng = np.random.default_rng(seed)
    n = schema.duration_days

    # Total return: direction * magnitude
    total_return = _MAGNITUDE_MAP.get(schema.magnitude, 0.06)
    if schema.direction == "down":
        total_return = -total_return
    elif schema.direction == "sideways":
        total_return = 0.0

    # Linear drift component
    end_price = start_price * (1.0 + total_return)
    drift = np.linspace(start_price, end_price, n)

    # Noise component: cumulative sum of daily returns (random walk overlay)
    daily_vol = _VOLATILITY_MAP.get(schema.volatility, 0.012)
    noise = rng.normal(0, daily_vol * start_price, size=n)
    cumulative_noise = np.cumsum(noise)

    # Combine drift + noise
    trajectory = drift + cumulative_noise

    # Floor at 1.0 to prevent negative prices
    trajectory = np.maximum(trajectory, 1.0)

    return trajectory


# =========================================================================
# 4. Registry integration
# =========================================================================


def register_nl_ts_run(
    schema: NarrativeSchema,
    trajectory: np.ndarray,
    registry_path: str,
    *,
    seed: int = 42,
) -> str:
    """Register an NL-to-time-series run in the platform registry.

    Creates a RunRecord of kind=NL_TS with the parsed schema as config
    and trajectory summary statistics as the summary dict.

    Parameters
    ----------
    schema : NarrativeSchema
        The parsed narrative (stored as run config).
    trajectory : np.ndarray
        The compiled trajectory (summary stats stored, not raw data).
    registry_path : str
        Path to the SQLite registry database.
    seed : int
        RNG seed used for compilation.

    Returns
    -------
    str
        The ``run_id`` assigned to this run.
    """
    run_id = new_run_id()

    # Summary: headline stats of the compiled trajectory
    summary = {
        "start_price": float(trajectory[0]),
        "end_price": float(trajectory[-1]),
        "min_price": float(np.min(trajectory)),
        "max_price": float(np.max(trajectory)),
        "total_return_pct": float((trajectory[-1] / trajectory[0] - 1) * 100),
        "n_timesteps": len(trajectory),
        "direction": schema.direction,
        "magnitude": schema.magnitude,
        "volatility": schema.volatility,
    }

    # Config: the full parsed schema for reproducibility
    config = {
        "direction": schema.direction,
        "magnitude": schema.magnitude,
        "duration_days": schema.duration_days,
        "volatility": schema.volatility,
        "catalyst_keywords": schema.catalyst_keywords,
        "raw_text": schema.raw_text,
        "seed": seed,
    }

    record = RunRecord(
        run_id=run_id,
        kind=RunKind.NL_TS,
        config=config,
        seed=seed,
        status=RunStatus.SUCCEEDED,
        summary=summary,
        created_at=iso_now(),
        pillar="nl_ts",
    )

    registry = RunRegistry(registry_path)
    registry.register_run(record)
    registry.close()

    return run_id


# =========================================================================
# 5. Inline narratives
# =========================================================================

NARRATIVES = [
    (
        "COVID crash scenario: A sharp, volatile sell-off over 30 trading days "
        "as pandemic fears trigger global liquidation. Markets plunge with "
        "extreme uncertainty and chaotic price action."
    ),
    (
        "Post-vaccine recovery rally: A steady, moderate climb over 3 months "
        "as vaccine rollout drives optimism. Volatility gradually calms as "
        "the recovery broadens."
    ),
    (
        "Sideways consolidation: Range-bound trading for 6 weeks with low "
        "volatility. Markets digest previous gains in a quiet, steady holding "
        "pattern before the next catalyst."
    ),
]


# =========================================================================
# 6. Main demo
# =========================================================================


def main() -> None:
    """Run the end-to-end NL-to-time-series pipeline."""
    print("=" * 70)
    print("NL-to-Time-Series — End-to-End Demo (v1)")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "registry.db")

        for i, narrative in enumerate(NARRATIVES, 1):
            print(f"\n{'─' * 70}")
            print(f"Narrative {i}:")
            print(f"  \"{narrative[:80]}...\"")

            # --- Parse ---
            schema = parse_narrative(narrative)
            print(f"\n  Parsed:")
            print(f"    direction:   {schema.direction}")
            print(f"    magnitude:   {schema.magnitude}")
            print(f"    duration:    {schema.duration_days} days")
            print(f"    volatility:  {schema.volatility}")
            print(f"    keywords:    {schema.catalyst_keywords}")

            # --- Compile ---
            trajectory = compile_trajectory(schema, seed=42 + i)
            print(f"\n  Compiled trajectory:")
            print(f"    start:       ${trajectory[0]:.2f}")
            print(f"    end:         ${trajectory[-1]:.2f}")
            print(f"    min:         ${np.min(trajectory):.2f}")
            print(f"    max:         ${np.max(trajectory):.2f}")
            print(f"    return:      {(trajectory[-1]/trajectory[0] - 1)*100:+.2f}%")
            print(f"    timesteps:   {len(trajectory)}")

            # --- Register ---
            run_id = register_nl_ts_run(schema, trajectory, db_path, seed=42 + i)
            print(f"\n  Registered run: {run_id}")

        # --- Verify registry ---
        print(f"\n{'─' * 70}")
        print("Registry verification:")
        registry = RunRegistry(db_path)
        runs = registry.list(kind=RunKind.NL_TS)
        registry.close()
        print(f"  Total NL_TS runs: {len(runs)}")
        for run in runs:
            summary = run.summary if isinstance(run.summary, dict) else {}
            print(f"  - {run.run_id[:12]}... "
                  f"dir={summary.get('direction', '?')} "
                  f"ret={summary.get('total_return_pct', 0):+.1f}%")

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"  Pipeline:     keyword parser + piecewise-linear compiler (v1)")
    print(f"  Narratives:   {len(NARRATIVES)}")
    print(f"  Runs:         {len(runs)} registered in temp registry")
    print()
    print("  NOTE: v1 uses keyword parsing, not an LLM. The value is the")
    print("  end-to-end scaffold (schema, compiler, registry), not parsing")
    print("  quality. See vision/nl_to_timeseries.md.")
    print("=" * 70)


if __name__ == "__main__":
    main()
