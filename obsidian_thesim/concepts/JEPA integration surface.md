# JEPA integration surface

Where JEPA would slot into the production engine — **pending world model research results.**

> Full spec: `docs/planning/JEPA_INTEGRATION_SPEC.md`

## Status

**Paused.** JEPA retrieval (10th scoring method in Tier 2) was tried and killed — it learned shape similarity, which DTW already does better. The research direction is now **JEPA as a world model** for forward dynamics prediction and synthetic scenario generation.

If world model research succeeds, JEPA likely enters production as a **projector replacement** (learned dynamics for the forecast cone) rather than a matching method. The config flags (`jepa_enabled`, `jepa_weight`, `jepa_embedding_path`) are already in place.

See: [[JEPA]], `research/autoresearch/playbooks/JEPA_WORLD_MODEL_LANE.md`
