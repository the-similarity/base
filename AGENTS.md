# The Similarity — Agent Instructions

All agent instructions live in **`CLAUDE.md`** (project root).

`AGENTS.md` exists as a convenience pointer for platforms that look for this
filename (e.g. OpenAI Codex). The canonical source of truth is always
`CLAUDE.md` — do not duplicate content here.

## Critical rules for parallel agents (Codex, worktree agents, etc.)

These are the highest-priority rules extracted from CLAUDE.md. Read CLAUDE.md for full context.

### Shared-file conflict prevention
When multiple agents run in parallel, they WILL conflict on files that every agent edits. **DO NOT edit these files:**
- **`obsidian_thesim/_MOC.md`** — the orchestrator does one consolidated update post-merge
- **`.gitignore`** — note needed entries in your PR description instead
- **`CHANGELOG.md`**, **`pyproject.toml`** — same: only one agent per batch, or orchestrator post-merge

### Merge discipline
- PRs should be merged **as they land, not batched**. Each merge changes main, creating cascading conflicts.
- If you're an autonomous agent: commit, push, open PR, done. Don't wait for other agents.

### Knowledge base
- Write concept notes to `obsidian_thesim/concepts/`, topic notes to `obsidian_thesim/topics/`
- **DO NOT** update `_MOC.md` — the orchestrator handles it
- Use `[[wikilinks]]` to cross-link

### Git
- NEVER commit to `main` directly — feature branches only
- Do NOT add Co-Authored-By trailers
- Commit granularly: one logical change per commit
