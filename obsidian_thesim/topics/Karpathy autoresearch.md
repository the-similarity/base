# Karpathy autoresearch

**Idea in one breath:** give an agent a **small writable surface**, a **fixed benchmark**, a **keep/discard rule**, and let it run a disciplined experiment loop.

## Why we care

This is not just a language-model training trick. It is a **research operations pattern** that fits The Similarity surprisingly well.

We already have:
- modular code,
- benchmark-style backtesting,
- explicit metrics like CRPS and calibration,
- agent-assisted workflows.

So the key takeaway is: we can automate more research **without** giving up control, if we keep the loop narrow and reversible.

## The core loop

Karpathy's `autoresearch` repo (March 2026) distills the pattern into five elements:

1. one editable surface (only `train.py` is mutable),
2. one locked evaluator (`prepare.py` stays fixed),
3. one human instruction file (`program.md`),
4. a fixed experiment budget (five-minute training runs),
5. an append-only experiment log (`results.tsv`).

The human's job shifts to writing the **program/instructions** and improving the research organization itself.

## What parts are worth copying

- bounded write scope,
- fixed evaluation budgets,
- one clear keep/discard decision,
- durable experiment logs,
- human-written playbooks for agents.

## What parts not to copy literally

- one-file-only mutation for everything,
- one scalar metric for all decisions,
- endless looping directly on production code.

## Practical adaptation for The Similarity

Use the loop to test one hypothesis at a time:

1. write a short research brief,
2. let an agent edit only the allowed files,
3. run a frozen evaluator (walk-forward backtest, calibration, CRPS, hit rate),
4. keep the winner, revert the loser,
5. summarize the result into Obsidian.

Good candidate use cases:

- JEPA-style latent lenses,
- forecast calibration tuning,
- regime-aware ranking weights,
- window length / scale-factor sweeps,
- feature-store and caching improvements.

## Best use for this project

The strongest application is to JEPA and other experimental methods:
1. propose a bounded change,
2. run fixed walk-forward benchmarks,
3. keep only real improvements,
4. log failures so agents do not rediscover them forever.

## Read next

- [[karpathy-autoresearch-and-research-ops]]
- [[JEPA]]
- [[Backtesting and walk-forward]]
- [[Calibration and coverage]]

## Related

- [[Research hub]]
- [[Concepts index]]
