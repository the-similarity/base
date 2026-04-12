# Research automation and auto-research

## What this note is for

This note captures Karpathy-style research loops we can adapt for The Similarity:

- one editable surface
- one locked evaluator
- one human instruction file
- a fixed experiment budget
- an append-only experiment log

## Why it matters here

The Similarity already has a natural evaluation stack:

- walk-forward backtests
- calibration
- CRPS
- hit rate

That makes it a good fit for auto-research style iteration, because the agent can optimize against a real score instead of an ambiguous “looks better” judgment.

## Practical adaptation

Use the loop to test one hypothesis at a time:

1. write a short research brief
2. let an agent edit only the allowed files
3. run a frozen evaluator
4. keep the winner, revert the loser
5. summarize the result into Obsidian

## Good candidate use cases

- JEPA-style latent lenses
- forecast calibration tuning
- regime-aware ranking weights
- window length / scale-factor sweeps
- feature-store and caching improvements

## Related notes

- [[karpathy_autoresearch]]
- [[JEPA]]
- [[Walk-forward validation]]
- [[Research hub]]
