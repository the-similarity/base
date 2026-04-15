# Phase 2 findings — 2026-04-14/15

Second-pass execution of the [[Pitch deck 414|April 14 plan]], Phase 2 (**Build
the benchmark stack**). Three worktree agents ran in parallel across two
sessions (rate limit bisected Phase 2), landing three PRs: **#116 (2A
foundation-model lane), #117 (2B report/gate/rejection discipline), #118
(2C canonical slice catalogue).**

Companion to [[phase_1_findings_414]]. Compiled from merged PRs. Concept
notes: [[foundation_bench]], [[autoresearch_core]], [[benchmark_slices]].

---

## Setup

Phase 1 shipped three lanes (`retrieval_bench`, `projector-v2`, decision
layer). Each had its own:
- slice spec (inline in YAML)
- ledger schema (slightly different fields)
- report format (one markdown template per lane)
- gate logic (per-lane if/else)

That is fine at 3 lanes. It breaks at 10. Phase 2 rebuilt the **bench
infrastructure** so every future lane (foundation-model, JEPA,
synthetic-data, world-event) emits comparable artifacts and answers
comparable questions. And Phase 2 added an **external comparison lane**
(foundation models) so the engine is not only benched against itself.

---

## Finding 4 — Canonical slice catalogue is live (Track 2C)

### What shipped

- `research/autoresearch/slices/catalogue.yaml` — 27 slices, **append-only**,
  locked IDs
- Regime files:
  - `regimes/calm.yaml` — **5** slices (SPY 2013-2015, SPY 2017, NVDA
    accumulation 2016, AAPL 2019, BTC 2019 range)
  - `regimes/crisis.yaml` — **9** slices (COVID entry, rate-hike 2022,
    VIX spikes, BTC crashes, etc.)
  - `regimes/trend.yaml` — **9** slices (bull markets, parabolic runs)
  - `regimes/mean_reverting.yaml` — **4** slices (rangebound windows)
- Cross-asset pairs (3):
  - SPY vs NVDA during COVID
  - SPY vs BTC during COVID rally
  - BTC vs ETH during crypto winter 2022
- `slices/validate.py` + 16 validator tests (uniqueness, date sanity, regime
  labels match, pair legs exist, date overlap, join-rule validity)
- `slices/loader.py` — `load_slice(id)`, `load_regime(class)`,
  `load_cross_asset_pair(pair_id)`, frozen `SliceSpec` dataclasses
- Migrations:
  - `retrieval_bench/slices.yaml` now references catalogue IDs (dual-mode
    resolution keeps 1A tests green)
  - `projector-v2` benchmark YAML now references catalogue IDs

### Why it matters

Without the catalogue, every new lane had to redefine slices, which drifts,
and `validate.py` had no enforcement. With it:

1. **Longitudinal comparison is now mechanical.** Ledger rows from 1A, 1B,
   2A, and every future lane can be joined on slice ID.
2. **`append-only` is enforced.** Renaming a slice breaks every historical
   ledger row; the lint-level enforcement protects backtest integrity.
3. **Coverage is visible.** We can now answer "do we have any
   `mean_reverting` slices on crypto?" (answer: zero — known gap, logged).

### Root cause of the validator bug (worth a note for future agents)

First session's validator had `validate.py` defining:

```python
def run_all_validators(regimes_dir: Path = REGIMES_DIR, ...):
    ...
```

Python evaluates default-argument expressions **at function-def time**, not
call-time. When tests used `monkeypatch.setattr(V, "REGIMES_DIR", tmp_path)`,
the function had *already* captured the original `REGIMES_DIR` and the
patch did nothing — the validator silently read the real repo. Manifested
as 7 failing tests where "monkey-patched path" tests saw real data.

Fix: late-bind.

```python
def run_all_validators(regimes_dir: Path | None = None, ...):
    if regimes_dir is None:
        regimes_dir = REGIMES_DIR
```

This is a pattern worth remembering: **module-level constants captured in
function defaults are not patchable.** If the value must be overridable, it
must be looked up inside the function body.

### Known gaps

- No mean-reverting crypto slice (BTC's 2019 range is listed but short)
- No 2008 GFC slice (dataset doesn't go back that far for most symbols)
- `btc-parabola-2017` marked `missing_data: True` (dataset starts 2019-09-23)
- Only 3 cross-asset pairs; equity-vs-rates pair absent

### Code pointers

- `research/autoresearch/slices/` — whole lane
- `obsidian_thesim/concepts/benchmark_slices.md` — concept doc
- `obsidian_thesim/topics/Slice catalogue v1 — 414.md` — current contents +
  counts

---

## Finding 5 — Autoresearch core package standardizes every future lane
(Track 2B)

### What shipped

Five modules under `research/autoresearch/core/`:

- `ledger.py` — `LedgerEntry` dataclass, `append_entry()`, `entries_for_lane()`,
  `latest_run()`, `compare_runs()`. Schema: `run_id`, `benchmark_id`, `lane_id`,
  `timestamp`, `status`, `decision`, `summary`, `slices`, `metrics_before`,
  `metrics_after`, `regressions`, `artifacts`, `notes`, optional `git_sha`,
  optional `extra`.
- `metrics_delta.py` — paired-bootstrap (n=1000, seed=42) significance on
  `(candidate − baseline)` per metric. Returns `MetricDelta(name, baseline_mean,
  candidate_mean, delta, p_value, ci_low, ci_high, better_direction)`.
- `gates.py` — declarative `Gate(name, metric, threshold, direction, required)`;
  `evaluate_gates(deltas, gates) → GateDecision(keep, reasons, gate_results)`.
- `report.py` — `LaneReport(entries, deltas, gates, metadata).render_markdown()`;
  produces the canonical report markdown template every lane uses.
- `rejection_log.py` — appender + query for `progress/autoresearch/rejections.jsonl`.
  Schema: `direction_id`, `lane_id`, `summary`, `killed_at`, `evidence_refs`,
  `revisit_conditions`, optional `extra`.

Plus:

- **46 unit tests** (happy path + edge cases per module)
- Ports of 1A + 1B reports into canonical format (`*-v1-canonical.md`)
- Deprecation shims on old lane-specific `ledger.py`/`report.py`/`compare.py`
  pointing at `core.*`
- `obsidian_thesim/concepts/autoresearch_core.md`
- `obsidian_thesim/topics/Rejected directions 414.md`

### Rejection log bootstrapped

Two entries backfilled:

1. **`tier2_as_default`** (preliminary)
   - Killed at: 2026-04-15T05:37:08Z
   - Evidence: `retrieval-bench-tiers-v1-2026-04-15T05:37:08Z`
   - Revisit condition: "expanded-slice rerun on NVDA/TSLA/BTC + seed=314
     shows any regime where Tier 2 improves CRPS"
2. **`regime_aware_widening`** (hard)
   - Killed at: 2026-04-15T05:20:38Z
   - Evidence: `projector-v2-regime_aware_widening-2026-04-15T05:20:38Z`
   - Revisit condition: "someone refits the per-regime multiplicative
     factors against real residuals"

The `revisit_conditions` field is the interesting invariant. An agent in six
months reading the log can mechanically answer "has the world changed enough
to re-test this?" by checking the condition. It forces the killer to say what
would change their mind.

### Why gates are declarative, not code

Previous Phase 1 lanes hand-wrote gate logic in each `compare.py`. That works
when there are 3 lanes. It does not scale because:

- Cross-lane comparison is impossible if each lane defines "improvement"
  differently.
- Thresholds become implicit (magic numbers in if/else).
- When a lane's verdict flips from KEEP to DISCARD after a rerun, nobody can
  tell what specifically changed.

`Gate(name, metric, threshold, direction, required)` makes every gate a
single line of declarative config. Two agents reviewing the same bench
arrive at the same verdict.

### Code pointers

- `research/autoresearch/core/` — whole package
- `progress/autoresearch/rejections.jsonl` — live log
- `the_similarity/tests/test_autoresearch_core.py` — test coverage
- `obsidian_thesim/concepts/autoresearch_core.md`

---

## Finding 6 — Foundation models bench ran, with caveats (Track 2A)

### What shipped

- Lane: `research/autoresearch/foundation_bench/`
- 5 model adapters exposing a common `ForecastAdapter.predict_quantiles(...)`:
  - `timesfm` (Google, 200M params)
  - `chronos` (Amazon, T5 variant)
  - `moirai` (Salesforce)
  - `moment` (CMU foundation model)
  - `wavelet_baseline` (classical: db4 wavelet denoise + AR(p) + bootstrap)
- Walk-forward `run_bench.py` with `--n-trials`, `--slices`, synthetic-fallback
  path when parquet absent, budget cap with `status: "skipped_budget"`
- 39 tests (11 runner + 2 report + 3 ledger + 23 adapter)
- First sweep artifact: `progress/autoresearch/reports/foundation-bench-v1.md`,
  20 per-cell JSONs under `reports/foundation-bench/`, ledger row
  `foundation-bench-v1-2026-04-15T17:50:20Z`
- `obsidian_thesim/concepts/foundation_bench.md`
- `obsidian_thesim/topics/Foundation-model baselines 414.md`

### The honest verdict — v1 sweep was mostly synthetic fallback

Of 20 cells (4 slices × 5 models):
- **4 real cells** — `wavelet_baseline` on every slice (runs locally)
- **16 fallback cells** — TimesFM / Chronos / Moirai / MOMENT. No HF weights
  downloadable in this env; adapters fell back to AR(1) / bootstrap cones.

Every fallback cell is marked `status: "partial_synthetic_fallback"` in the
ledger and report. **The numbers below are not a meaningful foundation-model
evaluation yet.** The payload from v1 is the *runner, the report template,
the ledger schema, and the 39 tests* — not the numerical verdicts.

### What we can read off v1 anyway

Mean across 4 slices (`spy-bull-2016-2019`, `spy-covid-2020`,
`spy-rate-hike-2022`, `btc-long-run`):

| Model | Mean CRPS | Mean cal err | Mean hit | Fallback cells | Explainability |
|-------|-----------|--------------|----------|----------------|----------------|
| timesfm | 0.0934 | 0.108 | 0.42 | 4/4 | low |
| chronos | 0.0934 | 0.108 | 0.42 | 4/4 | low |
| moirai | 0.1071 | 0.633 | 0.33 | 4/4 | low |
| moment | 0.0934 | 0.108 | 0.42 | 4/4 | low |
| **wavelet_baseline** | **0.1083** | **0.279** | **0.48** | **0/4** | **medium** |

timesfm/chronos/moment are all identical because they all fell back to the
same AR(1)/bootstrap cone. Moirai's cone is different (wider) which is why
its calibration error is huge. None of these are the real models.

`wavelet_baseline` is the only trustworthy number. It shipped **0.48 mean hit
rate** — the best in the sweep — and moderate calibration on real data. It
is not a foundation model but it is a classical baseline we can beat.

### Why this still matters

The plan's Rule #4 — "benchmark before belief" — required an external
comparison lane before making any claim that the engine is doing something
no standard model can. We now have:

1. The bench **infrastructure** that will eat real weights the moment an
   environment can download them.
2. A **classical baseline** (wavelet) the engine must actually clear to be
   credible.
3. A **published scorecard template** (`foundation-bench-v1.md`) that every
   future bench will follow.

The real-weights rerun is Phase 2-followup, not Phase 3.

### Code pointers

- `research/autoresearch/foundation_bench/` — lane
- `progress/autoresearch/reports/foundation-bench-v1.md` — scorecard
- `progress/autoresearch/reports/foundation-bench/` — per-cell JSONs
- `the_similarity/tests/test_foundation_bench_*.py` — tests

---

## Cross-cutting — what these three together say about Phase 2

### The good signals

- **Infrastructure is now the product.** The canonical ledger + gates +
  report means every future bench spends its effort on the *numbers*, not
  on building scaffolding.
- **Rejected directions don't die quietly anymore.** `rejections.jsonl` +
  `revisit_conditions` is the institutional memory we did not have at
  Phase 1.
- **Slice IDs are locked.** A ledger row from today is joinable to a ledger
  row from 2027.
- **Classical baselines are on the board.** Wavelet is beatable. That is
  more useful than an unreachable TimesFM number.

### The warning signals

- Foundation-model v1 is mostly synthetic. If we pitch "our engine beats
  foundation models on these slices" we'd be lying on four out of five.
  The bench exists; the finding does not yet.
- The canonical core `gates.py` has 8 tests. Gate bugs are the kind of bug
  that silently flips every bench verdict. This deserves a second review
  pass and a property-based test suite next sprint.
- The slice catalogue is missing 2008 data and equity-vs-rates cross-asset.
  Several named regime classes (mean-reverting crypto) have ≤1 slice.

### What Phase 3 (world-model / JEPA) needs to do

- **Reuse everything.** The JEPA lane should emit canonical ledger rows
  through `core.ledger`, score against canonical gates, render through
  `core.report`, use catalogue slice IDs. Zero new scaffolding.
- **Integrate via projector or confidence seams, not via the matcher.**
  Phase 1 already established the matcher as well-understood; the world
  model should enter as a projector variant or a confidence-signal source,
  not replace retrieval.

## Ledger rows

```bash
grep -E '"run_id": "(retrieval-bench-tiers-v1|projector-v2-|foundation-bench-v1)' \
  progress/autoresearch/experiments.jsonl
```

## Related notes

- [[phase_1_findings_414]] — prior sprint
- [[foundation_bench]] concept
- [[autoresearch_core]] concept
- [[benchmark_slices]] concept
- [[Slice catalogue v1 — 414]]
- [[Autoresearch canonical core — 414]]
- [[Foundation-model baselines 414]]
- [[Rejected directions 414]]
