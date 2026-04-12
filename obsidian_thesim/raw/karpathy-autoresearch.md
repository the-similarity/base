# Raw: Karpathy autoresearch source notes

## Primary source checked

- Andrej Karpathy, **karpathy/autoresearch** (GitHub repo, public README and `program.md`, March 2026)
  - https://github.com/karpathy/autoresearch

## Core operating ideas extracted

- narrow writable surface,
- fixed experiment budget,
- one trusted evaluation metric,
- keep/discard discipline,
- experiment ledger,
- human-authored markdown instructions for the agent.

## Why it matters for The Similarity

The strongest transferable idea is not the exact training code. It is the **research loop discipline**.

For this repo, the analogue would be:
- bounded method / projector / config experiments,
- fixed walk-forward benchmark suites,
- explicit scorecard-based keep/discard,
- durable result logging,
- agent playbooks for experiment lanes.

## Caution

`autoresearch` is a deliberately tiny repo with one main mutable file and one scalar metric. The Similarity should copy the discipline, not the literal topology.
