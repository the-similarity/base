-- 0002_feedback.sql
-- ---------------------------------------------------------------------------
-- Personalized setup scanner v1 — thumbs-up/down feedback table.
--
-- Every alert and every analog the user sees can be marked
-- ``thumb=up|down`` with optional free-text. This is the goodrun feedback
-- moat per ``vision/personalized_setup_scanner.md`` — even when v1
-- doesn't compute on it yet, we MUST persist from day 1 so v2 has data
-- to train the goodrun filter on.
--
-- ``kind`` is either ``alert`` or ``analog``:
-- - ``alert``  — a live cross-instrument scanner hit fired to the user.
-- - ``analog`` — a historical match shown in the cold-backtest /
--                onboarding view.
--
-- ``alert_id`` and ``analog_id`` are NULLable because most rows reference
-- only one. Both are free-form strings (the alert / analog rows live
-- elsewhere — alerts in the API, analogs in the scan run). Keeping them
-- as plain TEXT means the engine layer doesn't need to model the
-- alert/analog tables to record feedback against them.
--
-- The composite index on (user_id, setup_id) covers
-- ``compute_goodrun_score(user_id, setup_id)`` — the helper in
-- ``the_similarity/core/scorer.py`` that aggregates thumbs into a
-- per-setup confidence shift.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    setup_id    TEXT NOT NULL,
    alert_id    TEXT,
    analog_id   TEXT,
    kind        TEXT NOT NULL,
    thumb       TEXT NOT NULL,
    free_text   TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (setup_id) REFERENCES setups(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_user_setup ON feedback(user_id, setup_id);
CREATE INDEX IF NOT EXISTS idx_feedback_setup_id   ON feedback(setup_id);
CREATE INDEX IF NOT EXISTS idx_feedback_kind       ON feedback(kind);
