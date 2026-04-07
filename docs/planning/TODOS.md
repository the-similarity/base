# TODOS

## Deferred: Tier 1 nomination scoring (Phase 2f)

**What:** Replace fixed-weight prefilter (`0.4*SAX + 0.4*MP + 0.2*Pearson`) with rank-credit nomination system across SAX + MP (potentially wavelet later).

**Why:** The current blend uses fixed weights that may not be optimal. A nomination system would surface candidates that multiple independent methods agree on, which is more robust than a weighted sum.

**Pros:** Potentially better recall — candidates nominated by multiple methods are more likely to be genuine matches. More principled than arbitrary weight tuning.

**Cons:** Added complexity (5-phase pipeline vs current single-pass). Unclear if it moves the needle — SAX already has no-false-dismissal guarantees. Risk of over-engineering before empirical validation.

**Context:** Current Tier 1 works well in testing. This should only be pursued after the backtester (Phase 4c) can measure whether Tier 1 quality is actually the bottleneck vs. Tier 2 scoring or weight tuning. The plan originally proposed running wavelet on all SAX survivors (~2000 candidates) which would dominate latency — if revisited, start with SAX + MP nomination only.

**Depends on:** Phase 4c backtester (to validate the need).

---

## Deferred: Refactor `_enrich_tier2()` to registry pattern

**What:** Replace 7 repetitive try/except blocks (~90 lines) in `matcher.py:_enrich_tier2()` with a registry of `(method_name, norm_key, score_fn, field_name)` tuples and a loop (~15 lines).

**Why:** DRY violation — each method follows the same pattern (normalize candidate → call method → assign to breakdown field → catch exceptions). Adding Phase 4a (Koopman forward evolution) will make it 8 repetitions.

**Pros:** Each new method becomes a one-line tuple addition. Easier to scan, harder to introduce inconsistencies between methods.

**Cons:** Methods with special behavior (Bempedelis stores alpha/beta/r2, TE needs forward window) require either a richer tuple schema or post-loop special-casing. Slight loss of explicitness for edge cases.

**Context:** Best time to do this is right before or alongside Phase 4a implementation, when the 8th method addition makes the repetition impossible to ignore. The registry should handle the common case (normalize → score → assign) and allow hooks for special behavior.

**Depends on:** Nothing — can be done anytime. Natural pairing with Phase 4a.

---

## Enable GitHub branch protection on main

**What:** Require CI status checks to pass before merging PRs to main.

**Why:** Without this, CI is advisory only — broken PRs can still be merged. The CI workflow runs tests but doesn't block anything.

**Context:** This is a GitHub UI setting, not a code change. Go to Settings → Branches → Branch protection rules → Add rule for `main` → Check "Require status checks to pass before merging" and select both `Python Tests` and `Frontend Tests`. Do this after the CI workflow PR is merged so the status checks exist to select.

**Depends on:** CI workflow being merged first.
