-- 0001_setups.sql
-- ---------------------------------------------------------------------------
-- Personalized setup scanner v1 — multi-tenant setups table.
--
-- A "setup" is a user-defined chart region (instrument + timeframe + index
-- range) that the cross-instrument scanner uses as the query window. Each
-- row is owned by exactly one ``user_id`` (string FK; we don't model the
-- users table here — auth lives in the API and emits user IDs we trust).
--
-- Storage shape mirrors the goodruns table style (flat, JSON-as-TEXT
-- region series) so it's grep-able from sqlite3 and survives schema
-- evolution without column rewrites.
--
-- Region representation
-- ---------------------
-- ``region_start_ts`` / ``region_end_ts`` are ISO-8601 UTC strings and
-- bound the matched window in wall-clock time. ``region_series_json`` is
-- a JSON array of floats — the actual price series the scanner uses as
-- the query. We persist the series itself (not just indices into a remote
-- dataset) so the setup keeps working even if the upstream data source
-- repaginates or rebuilds its index.
--
-- Indexes
-- -------
-- ``idx_setups_user_id`` — covers the dominant read: "list all setups for
--                          this user, newest first".
-- ``idx_setups_instrument`` — covers the scanner's reverse lookup: which
--                              users have an active setup on this symbol.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS setups (
    id                  TEXT    PRIMARY KEY,
    user_id             TEXT    NOT NULL,
    name                TEXT    NOT NULL,
    instrument          TEXT    NOT NULL,
    timeframe           TEXT    NOT NULL,
    region_start_ts     TEXT    NOT NULL,
    region_end_ts       TEXT    NOT NULL,
    region_series_json  TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_setups_user_id    ON setups(user_id);
CREATE INDEX IF NOT EXISTS idx_setups_instrument ON setups(instrument);
