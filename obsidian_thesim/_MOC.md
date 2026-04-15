# Map of content

Vault for **The Similarity**: research ingests, what we learn while building, and links back to the repo. Agents maintain compiled notes; **you** use Obsidian to read and navigate.

## Start here

- [[Welcome]]
- [[Engineers start here]] — **hires**: API, matcher, config, tests
- [[Research hub]] — **all repo research as Obsidian nodes** (surveys + atomic topics)
- [[Start here — non-technical readers]] — LLM Q&A entry path
- [[Engine map]] — where code lives and what it does
- [[Nine-method pipeline]] — tiered matcher mental model
- [[Vision pillars]] — product thesis (from repo vision)
- [[Repo research and docs]] — `research/` and `docs/` paths in the codebase

## Folders

| Folder        | Purpose |
|---------------|---------|
| `raw/`        | Web Clipper, papers, excerpts, images → compile into notes |
| `research/`   | **Surveys** + **`full-text/`** copies of repo `research/**/*.md` |
| `topics/`     | **One idea per file** (methods + concepts) for retrieval / graph |
| `concepts/`   | Short technical anchors linking into `topics/` |
| `outputs/`    | Plots, Marp, exports |

## Concepts

- [[Benchmark slices]] — canonical dataset membership and date bounds
- [[Keep-discard thresholds]] — numeric gates for experiment decisions
- [[Experiment ledger]] — append-only run log and query API
- [[Experiment report format]] — standardized comparison report schema
- [[JEPA data representation]] — log-returns, channels, temporal splits
- [[JEPA integration surface]] — production engine placement (paused pending world model research)
- [[Experimental feature flags]] — Config toggles for JEPA and future experiments
- [[Retrieval evaluation harness]] — top-k overlap, rank lift, walk-forward comparison
- [[Projector calibration lane]] — autoresearch lane for forecast cone tuning
- [[retrieval_bench]] — Tier 1 vs Tier 2 measurement lane (PR #113)
- [[projector_v2]] — adaptive-conformal + regime + joint-path projector variants (PR #114)
- [[trust_filter]] — gated projection trust (PR #111)
- [[finance_pilot]] — target user, success gates, pilot shape (PR #111)

## Phase 1 findings — 2026-04-14

- [[phase_1_findings_414]] — **compiled research record** across all three tracks
- [[Tier 2 methods — bench 414]] — Tier 2 is a 37× runtime sink with no measurable CRPS win on SPY; preliminary discard-as-default
- [[Adaptive conformal calibration 414]] — −14% CRPS, −0.033 calibration error; winning projector variant, awaits real-data confirmation
- [[Trust filter and decision rules 414]] — search → project → trust-gate → decide → review, opt-in modules; pilot-shaped not pitch-ready

## Phase 2 findings — 2026-04-14/15

- [[phase_2_findings_414]] — **compiled research record** across all three tracks
- [[Slice catalogue v1 — 414]] — 27 slices, 4 regime classes, 3 cross-asset pairs, append-only
- [[Autoresearch canonical core — 414]] — canonical ledger + gates + reports + rejection log for every future lane
- [[Foundation-model baselines 414]] — infra shipped, first-run mostly synthetic fallback; wavelet classical is the baseline to beat
- [[Rejected directions 414]] — `rejections.jsonl` backfilled with tier2-as-default + regime-aware-widening

## Backlog (optional)

- [ ] Add `raw/` ingest + one compiled [[topics/Concepts index|concept]] note
- [ ] Expand any [[topics/Methods index|method]] note when implementation changes
