# Tomorrow Design Guideline

Tomorrow lives at `/tomorrow`. It is the Lumen version of Prudent: the same
journal, saved entries, similar-day views, themes, repeats, entry table, and
local-reader checks, presented in a calmer Lumen-style shell.

Code anchors:
- Route layout: `the-similarity-app/app/tomorrow/layout.tsx`
- Design tokens and scoped CSS: `the-similarity-app/app/tomorrow/_components/tokens.ts`, `styles.tsx`
- Design primitives: `button.tsx`, `card.tsx`, `popover.tsx`, `sidebar.tsx`, `status-badge.tsx`, `avatar.tsx`, `empty-state.tsx`
- Product logic: `engine.ts`, `storage.ts`, `use-parse.ts`
- Route pages: `the-similarity-app/app/tomorrow/{thread,rhymes,tags,patterns,entries,engine}/page.tsx`
- Experiment page: `the-similarity-app/app/tomorrow/experiment/page.tsx`

## Product Brief

User: someone who journals and wants a useful read on today without manually
reviewing old entries.

Workflow replaced: scattered journal entries plus memory. Tomorrow turns a
paragraph into a saved day, a few simple charts, and comparable past days.

Magic moment: the user writes a normal paragraph and gets a plain read on what
today may do next, plus one move to make the day easier.

First 30 seconds: open `/tomorrow`, click New entry, write a paragraph, watch
the read update, then save it.

## Relationship to Prudent and Lumen

Tomorrow preserves Prudent's content and behavior. It shares the same persisted
entry namespace, `prudent:entries:v1`, so existing Prudent entries appear in
Tomorrow and new Tomorrow entries appear in Prudent.

Tomorrow does not share visual tweak state with Prudent. Its tweaks persist
under `tomorrow:tweaks:v1`.

Tomorrow borrows Lumen's visual language:
- plain white or black background behind the app shell
- glass sidebar card
- floating white panels
- forest accent by default
- TradingView-style system font stack plus JetBrains Mono

## Local Desktop Direction

Tomorrow should be ready to become an Electron app. The desktop version should:
- run fully local by default
- use a small Whisper model for cheap on-device voice notes
- save entries locally first
- feed transcribed text into the same Tomorrow reader
- keep cloud calls optional, never required for the core daily read

## PR 300 Product Lesson

PR 300 shipped Ghost5 as a focused paid route on top of the Lumen Workstation:
one shell, real graphs, fewer option chips, and a tight paid product boundary.
Tomorrow should follow that lesson:
- keep the left icon rail
- keep many useful graphs, but name them plainly
- hide research controls from normal users
- make Pro feel like a focused local daily product, not a black-box lab
- show saved-day comparisons like Ghost5 shows its histories

## Design System Rules

All Tomorrow-specific selectors must be scoped under `.tomorrow-app` or
`.tomorrow-root`. Do not write route styles into `app/globals.css`.

Use the primitives in `_components/` before adding inline UI:
- `Button` for actions
- `Card` for repeated framed content
- `Popover` for floating panels
- `StatusBadge` for compact state
- `Avatar` for identity
- `EmptyState` for empty route states
- `Sidebar` for route navigation

Keep components boring and aligned: 8px card radius, 7px control radius,
14px shell gutter, tabular numbers, short transitions, no gradient or animated
background.

## Implementation Constraints

Do not change `/prudent` to make Tomorrow work. Tomorrow is a parallel route for
side-by-side comparison.

Do not point Tomorrow at `/api/tomorrow/parse`; it intentionally reuses the
existing `/api/prudent/parse` endpoint until the parser API is renamed.

Do not introduce a `tomorrow:entries:*` key unless the product explicitly stops
sharing data with Prudent.

## Daily Read Loop

Tomorrow's engine follows the product sketch:

1. Previous natural-language entries are parsed into events.
2. Events turn into charts.
3. Tomorrow compares today with saved days.
4. Similar saved days show what often happened next.
5. The app writes the result back in plain language.
6. The user gets one next move, not a wall of numbers.

The UI surface for this is the "What might happen next" card on `/tomorrow`.

The deeper lab surface is `/tomorrow/experiment`. It must answer the user in
plain language first: "what will happen today?" Supporting panels can show
versions of the day, trust checks, changed parts, and case studies, but they
must support that natural-language answer rather than replacing it with raw
metrics.
