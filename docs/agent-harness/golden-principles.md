# Golden Principles

Golden principles are stable preferences that keep a high-throughput,
agent-maintained codebase coherent. They should be specific enough for agents to
apply and mechanical enough to become checks over time.

## Principles

- Prefer explicit boundaries over implied conventions.
- Prefer small, independently mergeable PRs over broad multi-domain changes.
- Prefer repo-local knowledge over external memory.
- Prefer generated or checked references over hand-maintained guesses.
- Prefer boring, inspectable dependencies over opaque magic.
- Prefer mechanical enforcement for recurring review comments.
- Prefer scoped autonomy: strict boundaries centrally, local freedom inside them.

## Promotion Criteria

Promote a principle into tooling when any of these are true:

- The same review comment appears three times.
- Two agents make conflicting assumptions about the same boundary.
- A stale document causes a wrong implementation.
- A task requires manual QA that could be expressed as a repeatable check.

## Candidate Checks

- Documentation index links resolve.
- Active execution plans contain owners, status, validation, and rollback notes.
- Shared hot files are not edited by worker PRs.
- Package boundaries follow the architecture map.
- Public API changes update reference docs or generated schemas.
- UI changes include a reproducible smoke path.
