# Rejected directions — narrative snapshot (2026-04-14)

This is the human-readable companion to `progress/autoresearch/rejections.jsonl`. It exists so a future agent surveying the repo doesn't re-propose a direction we already killed, and so the decisions carry the "why" in prose — not just thresholds.

For the mechanical "has this direction been killed?" check, use `research.autoresearch.core.rejection_log.is_rejected(direction_id)`. See [[autoresearch_core]] for the full schema.

## Current kill list

### 1. `tier2_as_default` — make the 9-method Tier 1+2 pipeline the engine default

- **Lane**: `retrieval-bench-tiers-v1-lane`
- **Killed at**: 2026-04-15T05:37:08Z
- **Verdict class**: preliminary discard
- **Evidence**: ledger row `retrieval-bench-tiers-v1-2026-04-15T05:37:08Z`; report at `progress/autoresearch/reports/retrieval-bench-v1.md`.

**What we tried.** Run the full 9-method Tier 1 + Tier 2 pipeline as the retrieval default on three SPY regime slices: bull 2016–2019, COVID 2020, and the rate-hike 2022. Baseline was Tier 1 (SAX+MASS → DTW+Pearson). Decision rule: keep only if CRPS improved on ≥ 3/3 slices **and** runtime stayed within a 3× budget of Tier 1.

**What happened.**

- Runtime multiplier: **37×** baseline (well outside the 3× budget).
- CRPS improved on only **1/3** slices.
- Forward-return correlation: 0.436 → **0.314** (−28%).
- P10/P90 calibration error: 0.05 → **0.175** (nearly 4× worse).
- Hit rate: 0.625 → 0.542.

**Why it was killed.** The Tier 2 methods enriched the shortlist with neighbours that DTW+Pearson had already down-ranked for good reason. The extra noise hurt both accuracy and calibration, and the 37× runtime alone disqualified it as a default. The engine defaults were **NOT changed** by this run.

**Revisit conditions** (from the log): *"expanded-slice rerun on NVDA/TSLA/BTC + seed=314 shows any regime where Tier 2 improves CRPS."* In other words — if a single-ticker regime surfaces where Tier 2 beats Tier 1 on CRPS at fair runtime, we re-open the conversation. Until then: don't propose Tier 1+2 as the default again.

**Commentary.** This is a *preliminary* kill, not a hard one, because three SPY regimes is a narrow slice pack. The right unlock is a wider slice pack, not a parameter tweak inside Tier 2 — we already know the tier is honest about which matches it finds.

### 2. `regime_aware_widening` — multiplicative per-regime widening of projector v2 quantile bands

- **Lane**: `projector-v2-lane-v1`
- **Killed at**: 2026-04-15T05:20:38Z
- **Verdict class**: **hard discard**
- **Evidence**: ledger row `projector-v2-regime_aware_widening-2026-04-15T05:20:38Z`; report at `progress/autoresearch/reports/projector-v2-v1.md`.

**What we tried.** Projector v2 variant that widens the P10/P90 (and all other) quantile bands by a multiplicative factor that depends on the detected regime. Tested on spy-1d and btc-1d.

**What happened.**

- CRPS: 0.191 → **0.196** (Δ +0.00533).
- Joint-path CRPS: 0.2118 → **0.2167** (Δ +0.00486).
- Hit rate: flat at 0.50.
- Calibration error: unchanged at 0.10.

**Why it was killed.** The multipliers were hand-picked constants rather than fit from residuals. They widened bands uniformly across the distribution without regard to actual regime-conditional dispersion — so every probability level paid the widening tax, and CRPS (an integral over the full distribution) got worse. Engine defaults were **NOT changed**.

**Revisit conditions** (from the log): *"someone refits the per-regime multiplicative factors against real residuals."* A hard kill because the *shape* of the idea is fine — regime-conditional widening is a sensible widening direction — but a specific hand-picked parameterisation doesn't survive. The revisit is gated on real work (fit the multipliers), not on new data.

**Commentary.** The pattern here generalises: a widening that is uniform across quantile levels cannot improve CRPS unless it's paired with a tightening somewhere else in the distribution. Future widening variants should either be shape-aware (widen tails more than the median) or come with a companion tightening mechanism that keeps the integral honest.

## How to add to this list

When a lane kills a direction:

1. Append a `RejectionEntry` to `progress/autoresearch/rejections.jsonl` via `research.autoresearch.core.rejection_log.append_rejection`. Include the evidence ledger row, a one-paragraph summary, and at least one actionable revisit condition.
2. Add a narrative section to this note with the same shape as the two above (What we tried / What happened / Why it was killed / Revisit conditions / Commentary).
3. Leave the ledger and the rejection log in peace — they are append-only. Corrections go in via a new row that carries `notes.supersedes = "<old_run_id>"`.

## Related

- [[autoresearch_core]] — the canonical schema, gate vocabulary, and code paths.
- [[retrieval_bench]] — the lane that killed `tier2_as_default`.
- [[projector_v2]] — the lane that killed `regime_aware_widening`.
- [[Keep-discard thresholds]] — the threshold decisions these verdicts ran against.
