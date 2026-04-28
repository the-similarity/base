# Design guidelines

The repo-root folder `design_guideline/` holds per-surface visual rules. Each surface has its own audience, density, and palette; one universal doc cannot cover them. The folder supplements [[design-language]] (the universal base at `docs/design/DESIGN_LANGUAGE.md`); it does not replace it.

## Why per-surface

The product spans four surfaces with different visual identities:

- **Workstation** at `/workstation`: Bloomberg-Lite analog finder. Three-column terminal, oxblood `--accent` `#5a2b2b`, Newsreader serif on warm-paper `#faf9f6`. See [[workstation]] and `the-similarity-app/components/workstation/workstation.tsx`.
- **Lumen** at `/workstation/lumen`: same Workstation engine reskinned via CSS-variable cascade. Painterly background, forest-green accent `#0a6b48`, Instrument Serif. The token-cascade trick lives in `the-similarity-app/app/workstation/lumen/_components/styles.tsx`.
- **Cadence** at `/cadence`: nine-screen health workstation rebuilt 2026-04-27. Sage-green accent `#5b8a72`, Instrument Serif metrics, painterly bg. Calm-clinical, not trading. See `the-similarity-app/app/cadence/_components/styles.tsx`.
- **Prudent** at `/prudent`: natural-language to time-series journal. Blue accent (tweakable to ember/teal/plum), Newsreader serif composer at 19px, dark icon rail. See [[prudent]] and `the-similarity-app/app/prudent/layout.tsx`.

Each surface uses its own scoped stylesheet and its own classname prefix (`.ws-*`, `.lumen-*`, `.cadence-*`, `.prudent-root`). Class-name collision with `app/globals.css` was the bug that motivated the prefix discipline; the layout docstrings call it out explicitly.

## What goes in each guideline

Every per-surface file in `design_guideline/` answers:

1. Purpose and audience.
2. What the surface inherits from the base doc, what it overrides, and why.
3. Voice and tone with real example copy strings from the running app.
4. Typography, color, layout, density, components, motion, states.
5. Don'ts specific to the surface.

Every claim is anchored to a real file path, a real CSS class name, or a real custom property. No generic design theory.

## Relationship to DESIGN_LANGUAGE.md

`docs/design/DESIGN_LANGUAGE.md` is the universal Bloomberg-Lite spec: 1100px container, tabular numbers, flat semantic palette, no gradients on chrome. Workstation is the most direct expression of that spec. Lumen, Cadence, and Prudent each deviate where their audience demands it. The deviations are documented per-surface so future agents know what is intentional vs accidental drift.

## When to add a new file

Add a fifth guideline when a new top-level product surface ships with its own visual identity (its own palette, font stack, and chrome). A second screen inside an existing surface does not warrant a new file. Examples that would warrant one: a strategy-builder pillar, a synthetic-data lab pillar, a public marketing surface that diverges from `the-similarity-landing/`.

## When NOT to update

- A bug fix that does not change the design rules.
- A copy string change inside an existing pattern.
- A single component moves files.

The git log covers those.

Cross-links: [[design-language]], [[case-study-pattern]], [[analog-palette]].
