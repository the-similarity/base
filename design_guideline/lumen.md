# Lumen Design Guideline

Lumen lives at `/workstation/lumen`. It mounts the SAME `<Workstation>` component that drives `/workstation` and reskins it with a painterly background, floating white cards, a forest-green accent, and Instrument Serif display type. No engine logic differs; every visual change happens through CSS-variable cascade.

Code anchors:
- Page: `the-similarity-app/app/workstation/lumen/page.tsx`
- Scoped stylesheet: `the-similarity-app/app/workstation/lumen/_components/styles.tsx` (the `LUMEN_CSS` template literal)
- Sidebar / topbar / cmdk / tweaks / shared: `the-similarity-app/app/workstation/lumen/_components/`
- Embedded engine: `the-similarity-app/components/workstation/workstation.tsx` (untouched)

## Purpose and audience

Lumen is the demo-first surface. It is what you show a prospective customer or investor when they ask "what does the product look like?" The flagship Workstation at `/workstation` is the working tool; Lumen is the same tool wearing a portrait-frame jacket. The visual language signals "research desk in a research library", not "Bloomberg in a hedge-fund pit".

Audience: design-sensitive viewers seeing the product for the first time. Designer, founder, design-aware investor. Also: the team itself, when we want to dogfood the workstation in a less industrial mode.

"Good" looks like: the painterly gradient is visible at the edges, the white cards float, the workstation feels embedded in a calm room rather than projected onto a CRT.

## Relationship to DESIGN_LANGUAGE.md

Lumen takes the base document as a starting point and overrides via the `.lumen-app { --bg: ...; --ink: ...; --accent: ... }` block in `styles.tsx` lines 30 to 153. The mechanism (described in the page docstring lines 10 to 22) is a token cascade: the embedded `<Workstation>` reads the same `--bg`, `--ink`, `--accent` etc. it does on `/workstation`, but they resolve to different values inside the `.lumen-app` ancestor.

Inheritance:
- Tabular numbers, restraint on motion, semantic color split between positive and negative.
- The dense three-column workstation grid (Lumen does not change it).
- The nine-lens trust radar and analog cards.

Deviations:
1. **Surface tone.** Background is a painterly gradient `linear-gradient(160deg, #4a7a5a, #6b9a72, #c4b896, #8a6a4a, #3d2f1f)` with two layered overlays (`::before` radial gradients, `::after` SVG fractal noise blended with `mix-blend-mode: overlay`). See `.lumen-painterly` in `styles.tsx` lines 200 to 223. The base document forbids gradients on chrome; Lumen treats the painterly element as background art, not chrome, and the workstation cards still sit on flat white.
2. **Accent.** Forest green `#0a6b48` (`--accent` in `styles.tsx` line 131) replaces the workstation's oxblood `#5a2b2b`. Mapped onto `--positive` so cone fills come out green-on-green. Six-color analog ramp `--c-analog-1` through `--c-analog-6` (line 143) replaces the workstation's gray-ramp default.
3. **Display serif.** Instrument Serif (line 150) replaces Newsreader. Loaded via Google Fonts `<link>` injected in `lumen/page.tsx` line 186 because Lumen must not depend on the app-level font setup.
4. **Card model.** Lumen wraps the workstation in two floating cards instead of letting it occupy the whole viewport. The wrapping uses `:has(.workstation)` (`styles.tsx` line 350) to detect the embedded workstation and turn `.lumen-main` into a transparent layout container so the workstation's two children (chart card, lens panel) become individual floating Lumen cards on the painterly background.

## Voice and tone

Same quant-newsroom voice as the workstation. Lumen does not soften the copy. The chrome is calmer, the words are not.

Real strings from the UI:

- Topbar crumbs (set in `lumen/page.tsx` line 217): `["Workspace", "Retrieve"]`
- Brand wordmark inside the sidebar (Instrument Serif italic): `Similarity` with `Lumen` as the subline, see `_components/sidebar.tsx`.
- Cmd+K palette items inherit from the lumen `_components/cmdk.tsx`.
- The embedded workstation's copy is unchanged ("No datasets registered yet", `engine v4.14 · nine lenses`, etc.) because the same component renders it.

The Lumen-only strings are the topbar crumbs, the sidebar nav labels, and the tweaks panel labels (accent / theme / compare).

## Typography

Three families. All three are loaded via the `<link rel="stylesheet">` injected at the top of the route (`lumen/page.tsx` lines 182 to 187):

- `--serif: 'Instrument Serif'`: display, used for the brand wordmark and the lumen brand-name.
- `--sans: 'Inter'`: body, controls, sidebar nav, topbar crumbs.
- `--mono: 'JetBrains Mono'`: kbd chips, mono labels, status counts.

Font-feature-settings on `.lumen-app` (line 63): `'cv11', 'ss01', 'ss03'`. These are the Inter character-variant flags that swap in the single-story `g`, alternate `i`, and curly `f` ligature. They are explicit because the rest of the app does not turn them on; Lumen does because the painterly background reads as more editorial.

Sizes worth memorizing:

| Element | Class | Size |
|---|---|---|
| Brand wordmark | `.lumen-brand-name` | 18px Instrument Serif |
| Brand sublabel chip | `.lumen-brand-sub` | 10px uppercase mono |
| Sidebar nav item | `.lumen-nav-item` | 13px Inter 450 |
| Sidebar nav label group | `.lumen-nav-label` | 10.5px uppercase, `letter-spacing: 0.08em`, color `var(--ink-4)` |
| Topbar crumbs | `.lumen-crumbs` | 13px |
| Body default | `.lumen-app` | 14px Inter 1.45 line-height |

## Color

Lumen tokens are defined twice in `styles.tsx`. The first block (lines 47 to 73) sets the Lumen-native variables (`--surface`, `--surface-2`, etc.) used by the Lumen chrome. The second block (lines 106 to 153) shadows the global tokens (`--bg`, `--ink`, `--accent`, `--c-query`, `--c-cone-line` etc.) so the embedded workstation picks up the Lumen palette.

Light theme:

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#f4f1ea` | Paper beige, behind the painterly art |
| `--surface` | `#ffffff` | Floating Lumen cards |
| `--ink` | `#161614` | Primary text |
| `--ink-3` | `#7a7a75` | Muted labels |
| `--accent` | `#0a6b48` | Forest green |
| `--accent-soft` | `#e7f0ea` | Pill backgrounds |
| `--positive` / `--c-cone-line` | `#0a6b48` | Up trends and cone line |
| `--negative` | `#b14a3a` | Muted brick |
| `--c-analog-1` | `#0a6b48` | Top analog (forest green) |
| `--c-analog-2` | `#b07c1d` | Second analog (warm ochre) |
| `--c-analog-3` | `#2e5d8c` | Third analog (slate blue) |
| `--c-analog-4` | `#7d3aa9` | Fourth analog (plum) |

Dark mode is opt-in: the tweaks panel toggles a `.dark` class on `.lumen-app` (page.tsx line 131). The dark overrides start at `styles.tsx` line 158 and parallel the light tokens. The dark `--accent` softens to `#2c8862` so the cone fill stays readable.

The painterly background has four presets exposed via the tweaks panel (page.tsx lines 72 to 78): `painterly`, `dusk`, `paper`, `charcoal`. Switching presets writes a new `background` style on the `.lumen-painterly` ref directly. Do not hardcode the gradient string anywhere else.

## Layout and density

Page shell (`styles.tsx` lines 30 to 69):
- `.lumen-app` is `100vw × 100vh` with `position: relative` and `overflow: hidden`. It is the cascade root.
- `.lumen-painterly` is absolutely positioned `inset: 0` with `z-index: 0`. Painterly art lives here.
- `.lumen-shell` (formerly `.app`) is the grid container: `position: relative; z-index: 1; padding: 14px; grid-template-columns: 220px 1fr; gap: 14px`. The 14px gutter is the load-bearing decision: it is what makes the cards float instead of touching.

Card discipline:
- Sidebar `.lumen-sidebar` is a glass card: `background: rgba(255,255,255,0.72); backdrop-filter: blur(20px) saturate(120%); border-radius: var(--radius-lg)`. The translucency is what gives the painterly background a chance to show through.
- `.lumen-main` is a solid white card by default. When it contains a `<Workstation>` it becomes transparent (the `:has(.workstation)` rule on line 350) and lets the workstation's own children carry the card chrome.
- `.lumen-topbar` becomes its own thin pill card when the workstation is embedded (`:has(.workstation) > .lumen-topbar` rule line 375).

Density: looser than the workstation, by 2 to 4px in most places. Sidebar nav items are 6px 10px instead of the workstation's tighter rhythm. Section padding inside cards is 14px to 22px (see `.lumen-card-pad` and `.lumen-card-pad-lg`).

## Component patterns

- **Painterly background.** `.lumen-painterly` with two pseudo-elements. Never put real content inside it; it is decorative art and `pointer-events: none`.
- **Glass sidebar card.** `.lumen-sidebar`. Houses brand cluster (`.lumen-brand`), nav groups (`.lumen-nav-group` containing `.lumen-nav-item` rows), and a footer cluster (`.lumen-sidebar-foot`).
- **Topbar pill.** `.lumen-topbar` with `.lumen-crumbs` left and `.lumen-top-actions` right. Houses the Cmd+K trigger.
- **Workstation host.** A flex container with `min-height: 0` and `overflow: hidden` (page.tsx line 230). Critical: without `min-height: 0` the embedded workstation pushes past the card bottom edge.
- **Cmd+K palette.** `_components/cmdk.tsx`. Accent-aware item rows.
- **Tweaks panel.** Floating bottom-right. Three rows: accent swatch picker, background preset, dark toggle. Mutates CSS variables directly via the ref-on-root pattern (page.tsx lines 92 to 105).
- **Embedded `<Workstation>`.** `lumen/page.tsx` line 236. Imports the standalone component as-is. The `effectiveSettings` derivation (lines 154 to 158) is the only place Lumen needs to mirror its dark toggle into the workstation's `settings.theme`.

## Motion

- `100ms` for sidebar nav item background transitions (`styles.tsx` line 298). Tight because the user is scanning a list.
- `120ms` for icon button color transitions.
- No marquee. Lumen has no rolling ticker.

The painterly art is static; the noise overlay does not animate. If you ever animate it, use a 30s+ cycle or you will trigger motion sickness.

## States

Empty, loading, error, offline are inherited from the embedded `<Workstation>` because Lumen does not own that surface area. The `.ws-banner--warn` and `.ws-banner--info` rules from `globals.css` still apply inside the cascade because Lumen does not shadow those classnames.

Lumen-only state surfaces:
- Tweaks panel feedback: the active accent swatch shows `transform: scale(1.05)` and a 2px ink ring.
- Cmd+K palette empty state: handled in `_components/cmdk.tsx`.

## Don'ts

- Do not edit `components/workstation/workstation.tsx` to make Lumen work. The token-cascade trick is the design. If you need a Lumen-only behavior in the workstation, extract the workstation into a smaller component and let Lumen wrap it differently: do not branch on a route name.
- Do not add un-prefixed selectors to `LUMEN_CSS`. The header docstring at `styles.tsx` lines 22 to 26 is explicit: "any class without a `lumen-` prefix can collide with `globals.css`." The previous bug that motivated this rule (the empty-main-panel collision with `.app`'s `grid-template-rows`) is documented in the same comment.
- Do not write an animated painterly background. The static gradient + radial overlays + fractal-noise SVG is the look. Animating it pulls focus from the workstation.
- Do not put route-level state in `globals.css`. Lumen is route-scoped on purpose; everything must stay under `.lumen-app`.
- Do not set CSS custom properties on `document.documentElement` from Lumen code. Always write through the `rootRef` to the `.lumen-app` element so a navigation away does not leave Lumen tokens leaking onto another route.
- Do not change the painterly preset names (`painterly`, `dusk`, `paper`, `charcoal`). They are a contract with the `<TweaksPanel>` keyboard shortcuts.
- Do not import Workstation styles into Lumen. Lumen never imports from `components/workstation/*` styles; it only imports the React component.
