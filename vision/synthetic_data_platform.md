# Synthetic Data Platform — Vision

**Status:** Draft 2026-04-15. This is the broader product vision. Today's MVP scope lives in [synthetic_copies_worlds_eval_mvp.md](synthetic_copies_worlds_eval_mvp.md).

---

## One-line pitch

A synthetic data platform with two products that share one eval spine:

- **Synthetic Copies** — privacy-audited, realism-first *datasets* cloned from real ones.
- **Synthetic Worlds** — controllable, headless *environments* that produce datasets on demand.
- **Eval** — the fidelity/privacy/utility scorecard both products are graded against.

The wedge: other tools give you synthetic data *or* a simulator. We give you both, measured by the same ruler, so you can pick per task.

---

## Why this shape

1. **Copies and worlds solve opposite failure modes.** Copies preserve the statistical fingerprint of a real dataset (good when you have one and can't share it). Worlds generate distributions you've never seen (good when reality is too rare, too slow, or too expensive to sample).
2. **Eval is the moat.** Anyone can bolt on a GAN or a simulator. Few can tell a customer *how good* the output actually is on three axes that matter: realism, privacy leakage, and downstream task utility. Making eval first-class turns "synthetic data" from a vibe into a measurable product.
3. **Shared artifact contract.** Copies and worlds both emit the *same* artifact shape (dataset + manifest + eval report). This means one CLI, one batch runner, one pricing unit, one integration surface for customers.

---

## Product pillars

### Synthetic Copies — privacy-audited, realism-first datasets
- **Input:** a real tabular / time-series dataset the customer can't share.
- **Output:** a synthetic dataset that (a) preserves marginal + joint distributions within tolerance, (b) passes a membership-inference / nearest-neighbor privacy audit, (c) trains a downstream model to within X% of the real-data baseline.
- **Wedge:** privacy score is shipped *with* every dataset, not sold as an add-on. Realism and utility numbers are published on the manifest.

### Synthetic Worlds — controllable headless environments
- **Input:** a scenario spec (parameters, regime, horizon, seed).
- **Output:** a deterministic rollout dataset + a manifest describing the generating process.
- **Wedge:** every world is *controllable* (you can sweep parameters), *headless* (runs on CI, no GUI), and *reproducible* (seed + params = byte-identical output). Worlds are first-class artifacts, not throwaway scripts.

### Eval — the scorecard both products are graded against
Three axes, scored 0-100 each, published on every manifest:
- **Fidelity** — distributional and task-level realism vs. a reference.
- **Privacy** — membership inference, nearest-neighbor distance, attribute leakage.
- **Utility** — train-on-synthetic / test-on-real (TSTR) and inverse (TRTS) deltas.

Eval is the single integration point that unlocks a marketplace: anyone's generator can plug in and be scored on the same leaderboard.

---

## Artifact contract (high level)

Every run of *any* product emits the same three things, co-located in one directory:

1. **Dataset file(s)** — Parquet (tabular / time-series) or NPZ (tensors). Named `data.parquet` or `data.npz` at the artifact root.
2. **Manifest** — `manifest.json`, describing: product (`copies` | `worlds`), generator version, seed, params/config, input dataset hash (copies only), output row count, column schema, timestamps.
3. **Eval report** — `eval.json`, containing fidelity / privacy / utility subscores plus a single headline score, and a human-readable `eval.md` summary.

The contract is codified by the Contract Agent (task #2); this doc specifies the *shape*, not the field names.

Why this matters: with a stable artifact layout, every downstream tool (CLI, dashboard, marketplace, regression harness) is generic. Copies and worlds are swappable behind it.

---

## Non-goals (for the platform, not just today)

- We are not building a general-purpose ML training platform. Eval consumes models, it doesn't serve them.
- We are not building a data labeling or annotation tool.
- We are not competing with sim engines on physics fidelity. Worlds are *statistical* environments for model/agent training, not digital twins.
- We are not shipping a hosted UI as V1. CLI + artifacts first; UI follows once the artifact shape is frozen.

---

## Follow-ups / Not yet shipped

Deliberately out of scope for MVP but planned for V1 of Copies:

- **Gaussian copula** (numeric + categorical via empirical CDF) — classic i.i.d. tabular baseline for inputs without serial structure.
- **Tabular GAN / diffusion / VAE** and **LLM-based tabular** — higher-capacity generators.
- **Time-series copies beyond block bootstrap** (stationary bootstrap, TimeGAN-style, state-space surrogates).

All plug into the same artifact contract and eval spine — only the generator module changes.

---

## Roadmap sketch (post-MVP)

1. **MVP (today):** block bootstrap (moving-block) and regime-aware block bootstrap copies generators (`BlockBootstrapGenerator`, `RegimeBlockBootstrapGenerator`), two worlds runners, one eval scorecard, CLI + batch runner, tests. See [synthetic_copies_worlds_eval_mvp.md](synthetic_copies_worlds_eval_mvp.md).
2. **V1:** additional copies backends (Gaussian copula, tabular GAN, diffusion), multiple worlds (finance, queueing, epi), eval leaderboard.
3. **V2:** marketplace — third-party generators plug into the eval harness and appear on a public scorecard.
4. **V3:** hosted UI, per-seat pricing, SSO, tenanted artifact storage.

---

## Links

- MVP scope: [[synthetic_copies_worlds_eval_mvp]]
- Broader five-pillar vision: `vision/VISION.md`
- Module contracts (codified by Contract Agent): see task #2
