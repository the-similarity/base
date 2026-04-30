# Execution Plans

Execution plans are versioned working memory for complex agent initiatives.
They are lighter than product specs but stricter than ad hoc TODOs.

## Layout

- `active/` — plans currently being executed.
- `completed/` — finished plans kept for audit and future agent context.
- `../templates/exec-plan-template.md` — required structure for new plans.

## Use An Execution Plan When

- Work spans more than one PR.
- Multiple agents may work in parallel.
- The task crosses package or product boundaries.
- The acceptance criteria require manual judgment or new validation tools.
- A rollback or migration path matters.

## Lifecycle

1. Copy the template into `active/<slug>.md`.
2. Fill in goal, scope, validation, risks, and task slices.
3. Keep the progress log current as PRs land.
4. Move the plan to `completed/` when done.
5. Update `../quality-scorecard.md` if the work changes harness maturity.
