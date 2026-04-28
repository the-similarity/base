# Prudent Design Guideline

Prudent lives at `/prudent`. It is the natural-language to time-series surface: a journal where you write a paragraph about your day, the engine parses anchors and emotional deltas, and the parsed events become a series that can be compared against any past day or 7-day window. The feel is "literary journal meets analytics ledger".

Six routes share the same shell:
- `/prudent`: Today (parse + KPI + day chart + rhyme heatmap + tag donut + thread ribbon)
- `/prudent/thread`: vertical scroll of every entry, newest first
- `/prudent/rhymes`: self-similarity view, top rhyme pairs and archetypes
- `/prudent/tags`: share of weighted events by tag
- `/prudent/patterns`: recurring motifs across entries
- `/prudent/entries`: flat list of every logged entry
- `/prudent/engine`: engine-internals view (parse trace)

Code anchors:
- Layout / shell / scoped styles: `the-similarity-app/app/prudent/layout.tsx`
- Default body: `the-similarity-app/app/prudent/_components/today-view.tsx`
- Engine context (state, accent, theme): `the-similarity-app/app/prudent/_components/engine-context.tsx`
- Sidebar / topbar / header: `the-similarity-app/app/prudent/_components/shell.tsx`
- Engine math: `the-similarity-app/app/prudent/engine.ts`
- Storage: `the-similarity-app/app/prudent/storage.ts`
- Sub-route pages: `the-similarity-app/app/prudent/{thread,rhymes,tags,patterns,entries,engine}/page.tsx`

## Purpose and audience

User: someone who keeps a journal and is curious about pattern. They write a paragraph, see it parsed live into anchored events ("ran into a friend" `+12`, "deadline pressure" `-8`), then watch the parsed trajectory show up against past trajectories. The product asks "your week rhymes with the week of day -23; keep writing."

Audience is closer to a Notion/Day-One user than a Bloomberg user. Prudent is the most literary surface in the product. Writing space is generous. The composer is the largest single element on screen.

"Good" looks like: a writing surface that wants to be written into, a parsed readout that feels like a conversation back, and a sidebar that anchors the user without demanding attention.

## Relationship to DESIGN_LANGUAGE.md

Prudent inherits the base document's semantic-only color rule (green for positive deltas, warm for negative) and the tabular-numbers discipline. Almost everything else differs because the surface is conversational, not instrument-grade.

Inheritance:
- Tabular numbers via `.tnum` utility class (line 183 in `layout.tsx`).
- Mono labels via `.mono` utility class.
- Restrained motion.
- High-contrast values vs muted labels.

Deviations:
1. **Width.** No 1100px container. Prudent is two-column: a sticky 56px-icon-rail-plus-280px-sidebar on the left, a fluid main column on the right with `padding: 18px 24px 28px 24px` (`layout.tsx` lines 76 to 82). The main column compresses but does not center.
2. **Background.** `--app-bg: #FAFAFA` (warm white) for the main canvas, `--panel: #FFFFFF` for cards, `--rail: #1F2328` (near-black) for the icon rail. The dark icon rail is a deliberate signature; it grounds the literary palette.
3. **Body type.** Inter for body. The composer textarea uses Newsreader serif at 19px (`layout.tsx` line 398). The mix of sans body and serif composer is the central typographic gesture.
4. **Accent.** Default `#3B82F6` blue, with three other choices: ember (orange), teal, plum. User-toggled via the floating tweaks panel. Not green; this is a journaling product, not a finance product.
5. **Scroll model.** Prudent opens its own scroll viewport. `.prudent-root` sets `height: 100vh; overflow-y: auto` because `app/globals.css` pins `body { overflow: hidden }` for the workstation terminal layout. Layout docstring (`layout.tsx` lines 29 to 36) calls out the invariant explicitly.

## Voice and tone

Reflective and quiet. First-person from the user's perspective. The product talks back like an attentive editor, not an oracle.

Real strings from the UI:

- Composer placeholder: see the `SAMPLE` constant in `layout.tsx` line 58. It is a 70-word first-person paragraph that demonstrates the writing register the product wants ("Woke up heavy, kind of anxious about the deadline. ... Dinner was calm, read a little before bed."). New copy in this surface should match that register.
- Composer empty parsed state (`layout.tsx` line 455): `No anchors detected yet, keep writing, the engine finds them as you type.`
- Composer save button (`layout.tsx` line 597): `Log to thread`
- Composer footer status (`layout.tsx` line 530): `<n> chars · <m> events · source: api/regex/idle`
- Sidebar primary CTA: `+ New entry`
- Sidebar nav items (`shell.tsx` lines 92 to 103): `Today` (with today's `Mon Mar 14` hint), `Thread` (with `30d` hint), `Rhymes`, `Tags`, `Patterns`, `Entries` (count badge)
- Rhymes hero (rhymes/page.tsx line 54): `This week rhymes with the week of day −23.`
- Rhymes hero subline: `RMSE 0.42 · 73% shape match`
- Tweaks panel sections (`layout.tsx` lines 712 to 714): `accent`, `theme`, `compare`. The `compare` options are `rhyme`, `yesterday`, `none`.

Rules:
- The composer ALWAYS speaks like a writing teacher: "keep writing", "the engine finds them as you type". Never like a chatbot.
- Use `−` (minus sign U+2212) for day-offset numbers in prose: `day −23`, not `day -23`.
- Em dashes are forbidden in user-facing copy outside the SAMPLE placeholder, which mimics how a person actually writes. Use commas, semicolons, or two short sentences.
- Numbers always carry `tnum`. The events count and chars count tick rapidly while the user types; non-tabular digits would shudder.

## Typography

Three families, pulled from the `--mono` and `--serif` custom properties on `.prudent-root` (`layout.tsx` lines 124 to 126), with Inter as the body default declared on `.prudent-root` itself (line 126):

- `Inter`: body, sidebar nav, controls, all chrome.
- `Newsreader`: composer textarea (19px, `letter-spacing: -0.005em`, `line-height: 1.6`), parsed readout (13.5px italic), rhymes hero quote (22px italic).
- `JetBrains Mono`: mono labels, kbd, the `.mono` utility, the `tnum` count strip.

Font-feature-settings on `.prudent-root` (line 130): `'cv11','ss01','cv03'`. The `cv03` flag swaps in the alternate `l` (single-story) which reads cleaner at the smaller body sizes Prudent uses.

Sizes worth memorizing:

| Element | Size | Family |
|---|---|---|
| Composer textarea | 19px | Newsreader 1.6 |
| Composer parsed readout | 13.5px | Newsreader italic 2.1 |
| Composer events count chip | 10px | mono uppercase |
| Sidebar nav item | 13px | Inter 500 |
| Sidebar primary CTA `+ New entry` | 13px | Inter 500 |
| Tweaks panel header | 11px | mono uppercase, `letter-spacing: 0.06em` |
| Tweaks row label | 9.5px | mono uppercase 0.08em |
| Rhymes hero quote | 22px | Newsreader italic |
| Body default | inherit | Inter 1.55 |

## Color

Tokens are defined on `.prudent-root` in `layout.tsx` lines 98 to 137. Dark mode is a sibling block at lines 138 to 161, gated by a `.prudent-dark` class on the same element.

Light theme:

| Token | Value | Usage |
|---|---|---|
| `--app-bg` | `#FAFAFA` | Page canvas |
| `--sidebar` | `#FFFFFF` | Sidebar surface |
| `--panel` | `#FFFFFF` | Cards |
| `--text` | `#14161A` | Primary text |
| `--ink` | `#14161A` | Display text, near-black buttons |
| `--muted` | `#6B7280` | Secondary text |
| `--faint` | `#9CA3AF` | Tertiary, dividers |
| `--line` | `#ECEEF1` | Hairlines |
| `--line-mid` | `#E3E6EA` | Stronger hairlines |
| `--hover` | `#F3F4F6` | Hover background |
| `--accent` | `#3B82F6` | Default blue, tweakable |
| `--accent-mid` | `#93C5FD` | Mid step |
| `--accent-soft` | `#DBEAFE` | Soft pill background |
| `--accent-ink` | `#1D4ED8` | Soft pill text |
| `--warm` | `#F97316` | Negative-delta warm orange |
| `--warm-strong` | `#EA580C` | Strong negative |
| `--warm-soft` | `#FED7AA` | Soft negative pill |
| `--cool` | `#0E7490` | Calm pillar |
| `--green` | `#16A34A` | Positive delta on parsed events |
| `--rail` | `#1F2328` | Dark icon rail |
| `--rail-ink` | `#9CA3AF` | Icon rail text |
| `--rail-active` | `#2A2F36` | Icon rail active state |

Accent palette (in `engine-context.tsx`, the `ACCENT_HEX` map): `blue`, `ember`, `teal`, `plum`. The user picks one through the floating Tweaks panel; the choice persists to localStorage. No green accent option; that would muddy the semantic split with `--green`.

Dark mode (`.prudent-dark` block):
- `--app-bg: #0E0F11`
- `--sidebar: #131518`
- `--panel: #17191C`
- `--text: #EDEEF0`
- `--green: #22C55E` (boosted for contrast)
- `--accent-soft: #1E3A8A`

## Layout and density

Page shell:
- `.prudent-root` is `height: 100vh; overflow-y: auto; overflow-x: hidden`. It is the only scroll viewport (the global body is locked).
- `<div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)" }}>` (`layout.tsx` line 69) wraps Sidebar + main.
- `<Sidebar>` is `position: sticky; top: 0` with internal layout `display: flex; height: 100vh`.
- `<main>` is `flex: 1; padding: 18px 24px 28px 24px; display: flex; flex-direction: column; gap: 18px`. The 18px vertical gap is the canonical card-to-card distance.

Sidebar internals:
- 56px dark icon rail (`background: var(--rail)`) with the brand mark, a help glyph, and a circular avatar.
- 280px nav column (`padding: 16px 14px`). Holds the `+ New entry` ink-filled CTA, the nav items, and any sidebar metadata.

Main grids (`.prudent-grid-top`, `.prudent-grid-mid` defined in the scoped style at lines 189 to 206):
- `.prudent-grid-top` is `340px 1fr` two-column above 1280px, single-column below.
- `.prudent-grid-mid` is `1.4fr 1fr` two-column above 1280px, single-column below.

Cards:
- `border-radius: 10px` is the canonical card radius. Composer modal uses 12px.
- `border: 1px solid var(--line)` for cards, `1px solid var(--line-mid)` for stronger separation (e.g. tweaks panel).
- Card padding varies: `20px 22px` for content cards on `/prudent/rhymes`, `26px 30px` for the rhymes hero, `18px 22px` for composer body, `14px 22px` for composer footer.

Density rules:
- Sub-route pages own their own scoped `<style>` blocks for responsive overrides (e.g. `thread/page.tsx` lines 54 to 80). Each sub-route can collapse its grid below 1100/900/820px independently because the layout-level grid doesn't know what its child needs.

## Component patterns

By file. Read the source before forking.

- **Sidebar.** `_components/shell.tsx` exports `Sidebar`. Two columns: `<div>` 56px icon rail + `<div>` 280px nav. Active state derived from `usePathname()` via `navIdForPathname()` (lines 66 to 74). Each nav row is a Next `<Link>` so the URL is the source of truth.
- **TopBar / PageHeader / Footer.** `shell.tsx` exports these helpers. They are mounted by `layout.tsx` so every sub-route inherits them.
- **Composer modal.** `layout.tsx` lines 318 to 611. Backdrop click closes; click inside `stopPropagation()`s. Header shows date-time stamp `Mon, Mar 14 · 9:42am · parsing live`. Body is the textarea over the parsed readout. Footer carries the `<n> chars · <m> events` strip and Cancel + Log buttons. Read-only mode shows `Close` instead of `Cancel` and disables the textarea.
- **Tweaks panel.** `layout.tsx` lines 627 to 718. `position: fixed; bottom: 16; right: 16; width: 248`. Three rows: accent swatches, theme segmented, compare segmented. Each segmented uses ink-filled active state (`background: var(--ink); color: var(--app-bg)`).
- **EngineProvider.** `_components/engine-context.tsx`. Owns entries, composer text, tweaks. Mutates accent/theme CSS variables on `.prudent-root` via the rootRef passed down from layout. Persists tweaks to localStorage.
- **TodayView.** `_components/today-view.tsx`. Composes KeyMetrics, DayTrajectory, RhymeHeatmap, TagDonut, ThreadRibbon. Uses `useParsedNarrative(text)` to derive the live series.
- **Sub-route page.** Pattern: `"use client"` + `useEngine()` + a single returned `<div>` with scoped `<style>` for responsive overrides. See `thread/page.tsx`, `rhymes/page.tsx`.
- **Pill chip.** Inline-styled. Background `var(--accent-soft)`, text `var(--accent-ink)`, padding `2px 7px`, border-radius `10`. Used for the events-count chip in the composer and the parsed-source chip in the footer.

## Motion

- `100ms ease` for tweaks-panel button transitions on background and color.
- `120ms ease` for accent swatch transform/scale.
- `filter: brightness(0.98)` on `button:hover:not(:disabled)` (line 211): the subtle button hover.

The composer textarea has no animation. Resize is `resize: vertical` only (read-only mode disables it). The parsed readout updates synchronously on each keystroke; do not add a fade.

The accent swatch active state uses `transform: scale(1.05)` plus a 2px ink ring via `box-shadow: 0 0 0 2px var(--panel), 0 0 0 3px rgba(20,22,26,0.25)` (line 670). That is the entire interaction-feedback budget.

## States

Empty:
- Today screen with zero entries: shows the demo-seed banner that pops 14 days into storage on click. See `today-view.tsx` line 86: `const showDemoBanner = entries.length === 0;`. Banner disappears as soon as any entry exists.
- `/prudent/thread` empty: shows `<EmptyState onCompose={openComposer} />` with a CTA back to the composer.
- `/prudent/rhymes` empty (fewer than 7 days of history): shows `<EmptyState have={history.length} onCompose={openComposer} />`.

Loading:
- The parse runs in two paths: regex-fast (synchronous) and api-tagged (async). The composer footer source pill shows `source: api`, `source: regex`, or `source: idle`. There is no spinner; the parsed readout simply re-renders when better data arrives.

Read-only:
- Clicking an entry card on `/prudent/thread` opens the composer in read-only mode (`useEngine().openReadOnly(entry)`). The header subline switches to `day −N · logged YYYY-MM-DD`, the textarea is disabled, the footer shows `Close` instead of `Cancel`, and the source pill is hidden.

Error:
- Not yet defined. When the parse API fails, the source pill should surface `source: regex` and the readout falls back to the regex parser. There is no error toast at this stage.

## Don'ts

- Do not put any non-prefixed selector in the layout's scoped `<style>`. Everything must start with `.prudent-root` or `.prudent-root.prudent-dark`. The layout docstring (lines 29 to 36) explains why: the global `body { overflow: hidden }` rule clashes with Prudent's own scroll, and a leaking selector would break the workstation.
- Do not drop the icon rail. The dark `--rail` column is the visual signature that ties Prudent's literary palette to the broader product.
- Do not theme on `document.documentElement`. EngineContext writes accent/theme through `rootRef.current` to `.prudent-root` so the surface is route-scoped.
- Do not put the composer or tweaks panel inside a route file. They are mounted at the layout level so they work on every sub-route. The layout docstring (lines 17 to 27) documents the bug from the previous revision when they only mounted at `/prudent`.
- Do not use the workstation's oxblood `--accent` `#5a2b2b`. Prudent has its own four-accent picker; choose blue/ember/teal/plum.
- Do not put a 1100px container around prudent content. The base document's container rule does not apply here.
- Do not add a third grid breakpoint inside `layout.tsx`. The two-column-to-single-column collapse at 1280px is the rule. Sub-routes can add their own narrower breakpoints in their own `<style>` blocks.
- Do not use em dashes in user-facing copy. The SAMPLE placeholder is the single exception because it imitates how a person actually writes.
