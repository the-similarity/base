# JEPA next-task backlog (TradingView paused)

This is the current execution backlog after explicitly dropping TradingView work for now.

The goal is to focus the project on:
- JEPA evaluation,
- autoresearch discipline,
- benchmark quality,
- and engine-side validation.

---

## Priority 0 — do next

### 1. Run the real JEPA baseline

**What**
- Execute the full baseline command from `research/autoresearch/playbooks/JEPA_BASELINE_RUNBOOK.md`.
- Produce the canonical baseline artifacts:
  - `progress/autoresearch/reports/baseline-jepa-report.json`
  - append baseline entry to `progress/autoresearch/experiments.jsonl`

**Why**
Everything JEPA-related now depends on a real baseline, not just the smoke test.

**Done when**
- the baseline report exists,
- the ledger contains the first real baseline run,
- metrics are recorded for at least the equities and crypto daily slices.

---

### 2. Formalize benchmark slices

**What**
Define exact benchmark membership and dates for:
- `equities-daily-core`
- `crypto-daily-core`
- `stress-regimes-core`

**Why**
The manifests currently name the slices conceptually, but reproducible autoresearch requires exact dataset membership and date windows.

**Done when**
- each slice has explicit symbol list + timeframe + date bounds,
- benchmark manifests stop relying on vague descriptions only.

---

### 3. Build the JEPA retrieval-only prototype outside production

**What**
Create the first latent retrieval experiment outside the production matcher.

Likely location:
- `the-similarity-playground/`
- or a dedicated JEPA research script under `research/autoresearch/`

**Why**
We want to learn whether JEPA adds value before touching `the_similarity/core/matcher.py`.

**Done when**
- embeddings can be generated for baseline windows,
- nearest-neighbor retrieval can be compared against the current engine,
- the experiment is runnable from a bounded lane.

---

## Priority 1 — immediately after baseline

### 4. Add a retrieval evaluation harness

**What**
Build a repeatable comparison harness for:
- baseline top-k analogs,
- JEPA-reranked top-k analogs,
- side-by-side outputs and rank movement.

**Why**
Without a retrieval harness, JEPA evaluation will drift into anecdotal examples.

**Done when**
- we can compare top-k overlap,
- inspect rank lift for chosen reference cases,
- emit machine-readable comparison artifacts.

---

### 5. Tighten keep/discard thresholds

**What**
Turn the current acceptance rules into stricter thresholds.

Suggested examples:
- minimum CRPS improvement,
- maximum allowed calibration regression,
- maximum runtime increase,
- explicit “discard if retrieval gains do not survive walk-forward”.

**Why**
The current rules are directionally correct but still too qualitative for autonomous iteration.

**Done when**
- benchmark manifests encode operational thresholds,
- two different agents would reach the same keep/discard decision from the same metrics.

---

### 6. Make the ledger the real source of experimental memory

**What**
Start using `progress/autoresearch/experiments.jsonl` for every real run.

Required fields should always include:
- run id,
- benchmark id,
- lane id,
- metrics before/after,
- keep/discard decision,
- artifact paths,
- concise rationale.

**Why**
Autoresearch without durable memory just repeats dead ends.

**Done when**
- every JEPA experiment appends a real ledger entry,
- baseline and follow-up experiments are traceable by artifact.

---

## Priority 2 — model/data preparation

### 7. Define the JEPA data representation

**What**
Decide the first JEPA training representation:
- close vs returns,
- normalized returns vs raw prices,
- optional extra channels (volume, realized vol),
- temporal train/val/test split policy.

**Why**
For JEPA, data representation matters more than model branding.

**Done when**
- there is one documented first-pass representation,
- the train/val/test temporal split is fixed,
- leakage risks are documented.

---

### 8. Create the first minimal JEPA training/export path

**What**
Add a minimal research-only path that can:
- build windows,
- train or freeze a simple encoder,
- export embeddings for retrieval experiments.

**Why**
The project needs an actual latent artifact, not just planning documents.

**Done when**
- one encoder/export path exists,
- embeddings can be cached and re-used by the retrieval harness.

---

### 9. Standardize baseline-vs-JEPA comparison reports

**What**
Define a consistent report structure per experiment.

Include:
- benchmark id,
- datasets used,
- retrieval examples,
- backtest metrics,
- runtime,
- recommendation.

**Why**
This makes experiments auditable and reviewable instead of conversational only.

**Done when**
- every serious JEPA run leaves one report artifact behind.

---

## Priority 3 — engine-facing preparation

### 10. Specify the `jepa_similarity` integration surface

**What**
Write a small design spec for where JEPA would eventually live in:
- config,
- `ScoreBreakdown`,
- matcher enrichment,
- caching.

**Why**
We should know the intended seam before we start proving whether it deserves to exist.

**Done when**
- the intended interface is clear,
- no production wiring has happened yet.

---

### 11. Add experiment-safe feature flags

**What**
Prepare future JEPA integration so it can be turned on/off cleanly.

**Why**
Autoresearch loops need reversible switches more than clever code.

**Done when**
- future JEPA scoring can be disabled without invasive code edits.

---

### 12. Strengthen the projector/calibration lane

**What**
Use the autoresearch framework for core-engine improvements unrelated to TradingView, especially:
- cone calibration,
- CRPS improvements,
- uncertainty-width behavior.

**Why**
If TradingView is paused, forecast quality becomes one of the highest-leverage engine tasks.

**Done when**
- projector experiments have their own benchmark-backed loop,
- improvements are measured through calibration + CRPS, not visuals alone.

---

## Cleanup / organizational tasks

### 13. Reconcile duplicate Karpathy notes

**What**
There are still duplicate/parallel note variants such as:
- `research/notes/karpathy_autoresearch.md`
- `research/notes/karpathy-autoresearch-and-research-ops.md`
- related Obsidian mirrors/topic notes

**Why**
The repo should have one canonical research note per concept where possible.

**Done when**
- duplicates are either merged or clearly deprecated,
- the Obsidian graph points at the canonical note.

---

### 14. Clean unrelated dirty files before the next focused branch

**What**
Resolve or separate unrelated local modifications, especially:
- `CLAUDE.md`
- `.obsidian/*`
- `the-similarity-data/manifests/catalog.json`
- stray note variants

**Why**
Autoresearch works best in a clean branch with a narrow diff.

**Done when**
- the next JEPA execution lane starts from a clean working tree or explicitly isolated scope.

---

### 15. Review and merge PR #64

**What**
Review the already-open framework PR and merge it if acceptable.

**Why**
The actual JEPA experiment work should branch off the shared framework, not re-create it locally.

**Done when**
- PR #64 is merged,
- the next JEPA lane starts on top of that base.

---

## Recommended execution order

1. Merge/review PR #64.
2. Run the real JEPA baseline.
3. Formalize benchmark slices.
4. Build JEPA retrieval-only prototype.
5. Add retrieval evaluation harness.
6. Tighten keep/discard thresholds.
7. Define JEPA data representation.
8. Build the minimal JEPA embedding export path.
9. Only then consider production matcher integration.

---

## Rule of thumb

Until JEPA wins on benchmarked retrieval + walk-forward evidence:
- keep it outside the production matcher,
- keep every experiment bounded,
- log every run,
- and prefer reversible scaffolding over deep integration.
