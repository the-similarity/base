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
