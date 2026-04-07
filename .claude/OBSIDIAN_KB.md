# Obsidian research wiki — agent playbook (`obsidian_thesim/`)

This vault is the **personal / project knowledge base** for The Similarity. It is inspired by the “LLM-maintained markdown wiki + Obsidian as viewer” workflow (ingest → compile → query → file outputs back). Agents should **grow this tree** as research and coding progress.

## Goals

- **Research**: papers, articles, repos, datasets — captured, summarized, and cross-linked.
- **Build memory**: decisions, invariants, and “what we learned” from implementation live next to citations, not only in code comments.
- **Compounding**: answers and explorations should **land as new or updated `.md` (and sometimes images)** in the vault when useful for the future.

## Suggested layout (create directories as needed)

| Path | Purpose |
|------|--------|
| `obsidian_thesim/raw/` | **Ingest**: Web Clipper exports, PDF sidecars, pasted excerpts, downloaded images tied to a source. Keep filenames stable; avoid editing these heavily — **compile** downstream. |
| `obsidian_thesim/` (or `wiki/`, `concepts/`) | **Compiled wiki**: summaries, concept notes, methods cheatsheets, MOCs (“Maps of Content”), backlinks to `raw/` and to repo paths. |
| `obsidian_thesim/outputs/` (optional) | **Generated artifacts**: Marp decks,matplotlib exports, diagrams — or merge into the main tree once stable. |

Indexes: maintain at least one **high-level index** (e.g. `_MOC.md` or `00-Index.md`) listing major topics and recent additions so large vaults stay navigable without “fancy RAG” at first.

## Data ingest → compile

1. **Ingest** into `raw/` (user may use Obsidian Web Clipper + local images; you may add clippings from approved sources).
2. **Compile** incrementally: for each new raw item, add a short wiki note with summary, key claims, limitations, and `[[wikilinks]]` to related concepts and code areas.
3. **Categorize** by concept: when the same idea appears in multiple sources, add or refresh a **concept article** and link out; avoid duplicate conflicting summaries — consolidate with dated “changelog” bullets if needed.

## IDE / Obsidian

- The user **views** raw + wiki + visualizations in Obsidian. You **maintain** the markdown and suggested folder structure.
- Prefer standard markdown + wikilinks; plugins (e.g. Marp) are optional — if you generate Marp, save under `outputs/` or a `slides/` folder and link from the relevant concept note.

## Q&A and outputs

- For substantive questions, **prefer writing a durable note** (or updating one) over a one-off chat reply when the insight has reuse value.
- **File outputs back**: slide outlines, comparison tables, small diagrams — if they clarify the wiki, commit them into the vault and link from the index.
- When citing the codebase, use **real relative paths** from repo root.

## Linting / health (periodic)

When the user asks or when the vault has grown:

- Spot **broken links**, duplicate concept names, and notes that contradict each other; propose merges or “see also” links.
- Flag **missing summaries** for items in `raw/` with no compiled note.
- Suggest **new article candidates** (interesting connections between methods, papers, and modules).

## Git and scope

- Same rules as the rest of the repo: work on a **feature branch**, small commits, no secrets.
- Large binaries: prefer links + small excerpts in `raw/`; do not bloat the repo without explicit approval.

## What not to do

- Do not replace the entire vault in one shot without a clear user request.
- Do not delete user-authored narrative without confirmation.
- Do not reformat `.obsidian/` for aesthetics alone.
