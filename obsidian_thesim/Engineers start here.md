# Engineers start here

This vault is for **future hires** as well as stakeholders: same graph, but these pages **name files, APIs, and behavior** so you can jump into the repo fast.

## Repo you’re in

- **Engine (Python):** `the_similarity/` — matcher, scorer, projector, backtester, `api.py`
- **This vault:** `obsidian_thesim/` — research mirror + topic nodes; **canonical research sources** are still `research/` at repo root (also copied under `obsidian_thesim/research/full-text/`)

## Read first (in order)

1. Root **`CLAUDE.md`** — worktrees, tests, architecture bullets (source of truth for “what exists”).
2. [[topics/Code — public API quickstart]] — `load` / `search` / `project` usage.
3. [[topics/Code — matcher tiers and modules]] — `find_matches`, tiering, imports.
4. [[topics/Code — Config and ScoreBreakdown]] — weights, `active_methods`, score fields.
5. [[topics/Code — method modules table]] — one Python file per technique.
6. [[topics/Code — tests and running locally]] — pytest commands.

## Still useful

- [[Full research notes from repo]] — long-form methodology write-ups.
- [[Research hub]] — surveys + `topics/` concept atoms (theory language).
- [[Engine map]] — module responsibilities (shorter than the code notes above).

## Conventions

- New scoring method: touch `config.py` weights + `active_methods`, `scorer.py` `ScoreBreakdown`, matcher wiring, API contracts if any, tests. See comments at top of `the_similarity/config.py`.
- Prefer **small commits**, **feature branches** per `CLAUDE.md` when shipping code (this vault may land on `main` by team choice).

## Related

- [[Welcome]]
- [[_MOC]]
