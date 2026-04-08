# Code — tests and running locally

From repo root (see root **`CLAUDE.md`** for worktree rules):

```bash
python -m pytest the_similarity/tests/ -v
```

Slow / integration subset:

```bash
python -m pytest the_similarity/tests/ -v -m slow
```

## Expectations

- All tests green before merge to `main` per team workflow.
- When you add a method or change `ScoreBreakdown`, extend **`the_similarity/tests/`** — grep for existing matcher/scorer tests as templates.

## Related

- [[Engineers start here]]
