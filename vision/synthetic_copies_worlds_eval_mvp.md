# Synthetic MVP — Copies / Worlds / Eval (2026-04-15)

**Status:** FROZEN for today. This is the single source of truth nine parallel agents are building against. If you want to change scope, message team-lead — do not silently diverge.

Platform vision: [[synthetic_data_platform]].

---

## Product definition

Three components, built today, that together form the smallest coherent demo of the platform:

### 1. Synthetic Copies (MVP)
Take a real tabular dataset → emit a synthetic copy that preserves distributions and passes a privacy audit.

- **Pitch:** *"Privacy-audited, realism-first datasets."*
- **MVP generator:** one method — a Gaussian copula fit to marginals + correlation, with categorical columns handled via empirical CDF. This is the simplest thing that is honestly "synthetic data" and can be scored on all three eval axes. Anything fancier (GAN, diffusion) is out of scope today.
- **Input:** one Parquet / CSV file with tabular columns (numeric + low-cardinality categorical).
- **Output:** a synthetic dataset with the same schema, N rows (default: match input), plus manifest + eval report.

### 2. Synthetic Worlds (MVP)
Run a headless, parameterized environment → emit a time-series rollout dataset.

- **Pitch:** *"Controllable, headless environments."*
- **MVP worlds:** two canonical ones —
  1. **`world.regime_switch`** — a two-regime AR(1) process with a controllable switch probability and noise level. Parameterizes *market-like* regime shifts.
  2. **`world.queue`** — an M/M/1 queue with controllable arrival rate, service rate, horizon. Parameterizes *ops-like* load dynamics.
- **Input:** a scenario config (dict / YAML) with params + seed + horizon.
- **Output:** a Parquet rollout (`t`, plus world-specific columns) + manifest + eval report.
- **Determinism requirement:** same config + seed ⇒ byte-identical output. Non-negotiable.

### 3. Eval (MVP)
Score any dataset (copy or world rollout) on three axes vs. a reference.

- **Pitch:** *"One ruler for every synthetic dataset."*
- **MVP scores:**
  - **Fidelity** — per-column KS statistic (numeric) / TVD (categorical), aggregated to 0-100.
  - **Privacy** — nearest-neighbor distance ratio (synthetic→real vs. real→real holdout), plus a simple membership-inference AUC; aggregated to 0-100 (higher = more private).
  - **Utility** — TSTR: train a logistic regression / gradient-boosted baseline on synthetic, test on real holdout; report accuracy ratio vs. TRTR baseline as 0-100.
- **Output:** `eval.json` (machine) + `eval.md` (human). Single headline score = weighted mean of the three axes.

---

## Artifact contract (high-level shape)

Every run writes an artifact directory:

```
artifacts/<run_id>/
├── data.parquet           # the dataset (copies or world rollout)
├── manifest.json          # provenance
├── eval.json              # machine-readable scores
└── eval.md                # human-readable summary
```

**manifest.json** (high-level fields — Contract Agent codifies exact types in task #2):
- `run_id` (str, ULID)
- `product` (`"copies"` | `"worlds"`)
- `generator` (str, e.g. `"copies.gaussian_copula"` / `"world.regime_switch"`)
- `version` (str, semver of the generator)
- `seed` (int)
- `params` (dict — generator-specific config)
- `input_hash` (str, sha256 of input file — copies only; null for worlds)
- `row_count` (int)
- `schema` (list of {name, dtype})
- `created_at` (ISO-8601 UTC)

**eval.json** (high-level):
- `fidelity` ({score: 0-100, breakdown: {...}})
- `privacy` ({score: 0-100, breakdown: {...}})
- `utility` ({score: 0-100, breakdown: {...}})
- `headline` (0-100, weighted mean)
- `reference` (path or hash of the reference dataset used)

Rule of thumb for all agents: *if a field isn't in this doc or the contracts module, don't invent one today — extend after MVP.*

---

## MVP scope matrix — what's IN, what's OUT

| Area | IN (today) | OUT (cut) |
|---|---|---|
| Copies generator | 1 method: Gaussian copula (numeric + categorical) | GANs, diffusion, VAEs, LLM-based tabular, time-series copies |
| Worlds | 2 worlds: regime-switch AR(1), M/M/1 queue | Physics sims, agents, multi-entity, image/video worlds |
| Eval | KS/TVD fidelity, NN-ratio + MI-AUC privacy, TSTR utility | Per-column detailed reports, fairness audits, DP accounting |
| CLI | `synth copies run`, `synth worlds run`, `synth eval run`, `synth batch` | Web UI, REST API, hosted runs, auth |
| Batch runner | YAML sweep of params, parallel local exec, writes to `artifacts/` | Distributed/remote execution, scheduling, retries |
| Tests | pytest for each module + one end-to-end batch | Benchmarks, fuzzing, property-based tests |
| Docs | This spec + module contract docstrings + a 1-page README | User guide, tutorial, hosted docs site |
| Storage | Local filesystem under `artifacts/` | S3, GCS, Postgres, any remote backend |

---

## Success metrics — Definition of Done (today)

A day is a win when **all** of the following are true:

- [ ] `vision/synthetic_data_platform.md` and `vision/synthetic_copies_worlds_eval_mvp.md` merged (task #1 — this PR).
- [ ] Module contracts module landed — a single file defining the dataclasses for manifest + eval (task #2).
- [ ] Copies generator runs end-to-end: `synth copies run --input <parquet> --out <dir>` produces a valid artifact directory that passes the contract check (task #4).
- [ ] Both worlds runnable: `synth worlds run --world regime_switch --params ...` and `--world queue --params ...` produce deterministic artifacts (task #3).
- [ ] Fidelity + privacy + utility scorecards all implemented and callable on any artifact directory (tasks #5, #6, #7).
- [ ] CLI / batch runner can execute a YAML sweep of copies+worlds+eval end-to-end (task #8).
- [ ] Tests pass: `pytest` green for every new module (task #9).
- [ ] At least one world-eval sweep artifact committed, showing three seeds × two worlds × scored (task #10).
- [ ] All PRs land on `main` and CI is green.

Stretch (if we're ahead):
- Plot the fidelity/privacy/utility triangle per artifact.
- A Makefile / justfile target that runs the full demo.

---

## Non-goals (today, explicitly cut)

- **No hosted service.** Local CLI only.
- **No auth, no tenancy.** Single-user local.
- **No differential-privacy accounting.** Privacy score is empirical (MI + NN), not cryptographic.
- **No image / video / text data.** Tabular + time-series only.
- **No multi-file datasets.** One input → one output artifact.
- **No streaming.** Batch rollouts only.
- **No frontend / dashboard.** Markdown and JSON are the UI.
- **No marketplace plumbing.** Eval is local; leaderboard is out.

---

## The product wedges (for pitches / copy)

- **Synthetic Copies:** *"Privacy-audited, realism-first datasets — every copy ships with its own receipt."*
- **Synthetic Worlds:** *"Controllable headless environments — reproducible data on demand, scored by the same ruler as real-world copies."*
- **Eval:** *"One scorecard for any synthetic dataset. Fidelity, privacy, utility — published with every artifact."*

---

## Agent coordination notes

- **Module contracts (task #2) is load-bearing.** Generators (tasks #3, #4) and scorers (#5–#7) import from it. If you're blocked on contract shape, ping the Contract Agent.
- **Shared-file rules (from CLAUDE.md):** do not edit `obsidian_thesim/_MOC.md`, `.gitignore`, `CHANGELOG.md`, `pyproject.toml` from worktree agents. Note any additions you need in your PR body instead.
- **Determinism is a contract, not a nice-to-have** for worlds — PRs without seed-stability tests will be sent back.
- **Merge as PRs land**, not in a batch. Cascading conflicts otherwise.

---

## Demos

Two canonical commands that run from a fresh clone with no manual setup. Both
are deterministic given their seed. See `the_similarity/synthetic/demos/README.md`
for the full list of output artifacts per command.

**Copies demo** — fit + sample + score against the shipped 500-row fixture:

```bash
python -m the_similarity.synthetic.cli \
  --input the_similarity/synthetic/demos/sample.csv \
  --n 500 --seed 42 \
  --out artifacts/demo-copies
```

**Worlds demo** — headless 500-tick rollout of the bundled `small_village` scenario:

```bash
cd the-similarity-fractal && \
  npm run sim:headless -- \
    --scenario scenarios/small_village.json \
    --seed 42 --steps 500 \
    --out artifacts/demo-worlds.jsonl
```
