# Design Guidelines

Per-surface design rules for The Similarity. Each surface in this product has a different audience and therefore a different visual identity. This folder documents what each one is, what it inherits from the universal base, and where it deliberately breaks from that base.

## The base document

The universal design language lives at `docs/design/DESIGN_LANGUAGE.md`. It is the editorial Bloomberg-Lite spec: 1100px container, tabular numbers, light flat palette, semantic green/red, no gradients on chrome. Every surface in this folder treats that doc as the starting point. The guidelines here only document what each surface adds, restricts, or overrides.

If a rule is not mentioned in a surface guideline, the base document applies.

## The four surfaces

| File | Route | One-line summary |
|---|---|---|
| `workstation.md` | `/workstation` | Flagship analog finder. Three-column terminal, dense, instrument-grade. Researcher and PM audience. |
| `lumen.md` | `/workstation/lumen` | The same Workstation engine reskinned via CSS-variable cascade. Painterly background, floating white cards, forest-green accent. Demo-first surface. |
| `cadence.md` | `/cadence` | Health workstation. Nine screens over the user's own biomarkers. Sage-green palette, Instrument Serif metrics, calm clinical feel. Not a trading UI. |
| `prudent.md` | `/prudent` | Natural-language to time-series journal. Six sub-routes (today, thread, rhymes, tags, patterns, entries). Newsreader serif body, dark icon rail, blue accent by default. |

## When to update these

Change the relevant surface guideline when any of these land:

1. A new design token is introduced for the surface (a new accent, a new shadow scale, a new font weight).
2. A new component pattern becomes canonical for the surface (e.g. a new card variant used in three or more screens).
3. A deliberate deviation from `docs/design/DESIGN_LANGUAGE.md` is shipped. The reason for the deviation must be captured.
4. A surface is renamed, moved, or split.

Do not update these when:

- A bug fix changes the implementation but not the rule.
- A copy string changes inside an existing pattern.
- A single component moves files.

## When to add a new file

Add a new file when a fifth top-level product surface ships with its own visual identity. A second screen inside an existing surface does not warrant a new guideline. A new pillar (e.g. a synthetic-data surface, a strategy-builder surface) with its own palette, font stack, and chrome does.

## Voice for these docs

Builder talking to builder. Lead with the point. Cite real CSS class names, real component file paths, and real example copy from the running app. Do not paraphrase or invent.
