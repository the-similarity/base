# The Similarity

> "History doesn't repeat itself, but it often rhymes." — attributed to Mark Twain

Markets, regimes, and narratives keep changing the lyrics—but the **shape** of what came before still matters. The question isn't only "what happened last time?" It's **what rhymes with right now**, under what uncertainty, and what futures are consistent with that rhyme.

**The Similarity** is a structural intelligence platform: find analogues across time and domain, represent state, simulate and stress-test, and surface calibrated forecasts—not vibes, not a single chart, but a **tiered engine** (fast prefilter → rigorous scoring → enrichment → ranking) with explicit uncertainty.

This repository is the **core library**, **APIs**, **apps**, **data**, **synthetic tooling**, and **agent harness** that ship together. Finance is the proving ground; the same stack generalizes to synthetic data, synthetic worlds, 3D latent exploration, and narrative→time-series interfaces.

**This is the factory, not a slide deck.** 1,270+ tests under `the_similarity/tests/`, nine active similarity methods (plus 2D variants), a platform spine (runs, artifacts, registry, adapters), TradingView parity, and daily-refreshed-scale data pipelines—all in one monorepo with a CI gate that mirrors production installs.

Fork it, run it, break it, fix it. If you're here to **ship** structural intelligence—not just talk about it—welcome.

**Who this is for:**

- **Quant and systematic researchers** who want retrieval + calibration + backtests in one loop, not three glued scripts
- **ML / platform engineers** building synthetic datasets, registries, and evaluation harnesses with real contracts
- **Product builders** shipping UIs, APIs, and world runners on top of the same engine—no parallel "demo stack"

## Quick start

1. **Clone** this repo (or open it in your workspace).
2. **Run the CI mirror** — `bash scripts/ci_local.sh` (throwaway venv; matches what GitHub runs).
3. **Run the engine tests** — `python -m pytest the_similarity/tests/ -v`
4. **Skim** [`CLAUDE.md`](CLAUDE.md) — multi-instance rules, orchestrator, worktrees, Obsidian KB boundaries.
5. **Stop there.** If tests pass and the layout makes sense, you're in the right place.

## Install — real environments

**Requirements:** Python 3.11+ (see `pyproject.toml`), Git, Node.js for the Next.js app when you're working on `the-similarity-app/`.

### Engine + Python packages

From the repo root (matches PR gate: editable install + pytest + ruff in a clean venv):

```bash
python3.12 -m venv .venv   # 3.11+ works; CI prefers 3.12 when available
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
pip install pytest ruff
python -m pytest the_similarity/tests/ -v
ruff check the_similarity/
```

**Poetry:** if you use Poetry day-to-day, `poetry install` then `poetry run pytest the_similarity/tests/ -v` — but **`bash scripts/ci_local.sh` remains the merge gate** (throwaway venv, same commands as CI).

**Before you open a PR:** always run `scripts/ci_local.sh`. Local pytest alone can greenwash if your machine has stray site-packages.

### Where the important pieces live

| Surface | Path | What it is |
|---------|------|------------|
| **Public API** | `the_similarity/api.py` | `load`, `search`, `project`, `ensemble_project`, `backtest`, … |
| **Matcher pipeline** | `the_similarity/core/matcher.py` | Tiered SAX/MASS → DTW/Pearson → Tier-2 enrichment → final rank |
| **Config** | `the_similarity/config.py` | All method toggles and hyperparameters |
| **Platform spine** | `the_similarity/platform/` | Contracts, SQLite registry, artifact I/O, adapters |
| **Customer API** | `the-similarity-api/` | FastAPI app + platform routes |
| **Frontend** | `the-similarity-app/` | Next.js UI |
| **Data** | `the-similarity-data/` | Catalogs, manifests, refresh workflows |
| **Orchestrator** | `orchestrator/` | Task YAML, discovery, worktree agents (`python orchestrator/run.py`) |
| **Agent harness docs** | `docs/agent-harness/` | Operating model, exec plans, scorecards |
| **Research wiki** | `obsidian_thesim/` | Durable concepts and ADRs (agents maintain per `.claude/OBSIDIAN_KB.md`) |

## See it work

```
You:    I have a window of prices and want analogues + a forecast cone.

You:    Load the series, run search() with the default nine-method stack,
        then project() with confidence decay + Koopman blend.

Engine: Prefilter shrinks the candidate set, DTW/Pearson lock the tier-1
        shape, tier-2 methods enrich, scorer renormalizes weights,
        projector emits quantiles you can backtest later.

You:    Same story for synthetic_copies or a world run—adapters write
        RunRecords into the registry; the API lists artifacts.
```

That's **one engine**, multiple surfaces—retrieve, represent, simulate, evaluate, render, decide.

## The loop (how we think about shipping)

**Specify → Retrieve → Score → Forecast → Evaluate → Register**

- **Specify** — window, instruments, scenario (finance, copy, world).
- **Retrieve** — analogues with a cost-aware pipeline, not a single-distance hack.
- **Score** — `ScoreBreakdown` + dynamic weights (see `the_similarity/core/scorer.py`).
- **Forecast** — projector + ensemble paths; conformal and regime hooks where enabled.
- **Evaluate** — walk-forward backtests, calibration, CRPS-style metrics (`the_similarity/core/backtester.py`, `metrics.py`).
- **Register** — optional platform spine so every run is auditable later.

Parallel agents use **worktrees** (see `CLAUDE.md`): don't edit hot shared files like `obsidian_thesim/_MOC.md` from every branch.

## Pillars (product, one platform)

| Pillar | Role |
|--------|------|
| **Finance** | Fast feedback, measurable trust, production analogue search + forecasting |
| **Synthetic copies** | Realism-first synthetic data + fidelity / privacy / utility scorecards |
| **Synthetic worlds** | Headless runners, scenarios, stress and rare-event generation |
| **3D data space** | Exploration surface over latent state and regimes |
| **World event & narrative layers** | Multimodal and NL→time-series expansion |

## Docs

| Doc | What it covers |
|-----|----------------|
| [`CLAUDE.md`](CLAUDE.md) | **Canonical agent + git + CI rules** — read this first |
| [`AGENTS.md`](AGENTS.md) | Short pointer to `CLAUDE.md` for toolchains that expect `AGENTS.md` |
| [`docs/README.md`](docs/README.md) | Index of structured docs (architecture, harness, tutorials) |
| [`docs/agent-harness/`](docs/agent-harness/) | Operating model, exec plans, quality scorecard |
| [`vision/`](vision/) | Roadmap and product narrative |

## Troubleshooting

**Tests pass locally but CI fails?** Run `bash scripts/ci_local.sh` from a clean shell.

**Import errors in pytest?** You probably installed something globally; the script above fixes that.

**Which test command?** `python -m pytest the_similarity/tests/ -v` — slow integration: `-m slow`.

## License

MIT — see [`LICENSE`](LICENSE) and [`pyproject.toml`](pyproject.toml). Contribute via PR; **do not commit to `main` directly**—feature branches only (see `CLAUDE.md`).
