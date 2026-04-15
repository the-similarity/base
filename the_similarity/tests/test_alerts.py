"""Tests for the alert system (6b).

Covers:
- AlertManager CRUD (watchlist create/get/list/update/delete)
- Alert evaluation with threshold triggers
- Cooldown deduplication
- Alert history and acknowledgement
- Custom notification channels
"""
from __future__ import annotations


import pytest

from the_similarity.core.alerts import AlertManager
from the_similarity.core.scorer import MatchResult, ScoreBreakdown


@pytest.fixture
def alert_mgr(tmp_path):
    return AlertManager(db_path=tmp_path / "alerts_test.db")


def _make_match(score: float = 85.0, start: int = 100, end: int = 160) -> MatchResult:
    return MatchResult(
        start_idx=start,
        end_idx=end,
        confidence_score=score,
        score_breakdown=ScoreBreakdown(dtw=0.9, pearson_warped=0.8),
        regime="trending_up",
    )


class TestWatchlistCRUD:
    def test_create_watchlist(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="user1",
            name="BTC breakout",
            query_values=[1.0, 2.0, 3.0, 4.0, 5.0],
            threshold=75.0,
            symbol="BTC",
        )
        assert wl.id
        assert wl.user_id == "user1"
        assert wl.name == "BTC breakout"
        assert wl.threshold == 75.0
        assert wl.symbol == "BTC"
        assert wl.enabled is True

    def test_get_watchlist(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="user1", name="Test", query_values=[1.0, 2.0, 3.0],
        )
        fetched = alert_mgr.get_watchlist(wl.id)
        assert fetched is not None
        assert fetched.id == wl.id
        assert fetched.query_values == [1.0, 2.0, 3.0]

    def test_get_nonexistent(self, alert_mgr):
        assert alert_mgr.get_watchlist("nonexistent") is None

    def test_list_watchlists(self, alert_mgr):
        alert_mgr.create_watchlist(user_id="u1", name="A", query_values=[1.0, 2.0])
        alert_mgr.create_watchlist(user_id="u1", name="B", query_values=[3.0, 4.0])
        alert_mgr.create_watchlist(user_id="u2", name="C", query_values=[5.0, 6.0])

        u1_lists = alert_mgr.list_watchlists("u1")
        assert len(u1_lists) == 2
        u2_lists = alert_mgr.list_watchlists("u2")
        assert len(u2_lists) == 1

    def test_update_watchlist(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Old", query_values=[1.0, 2.0], threshold=70.0,
        )
        updated = alert_mgr.update_watchlist(wl.id, name="New", threshold=90.0)
        assert updated is not None
        assert updated.name == "New"
        assert updated.threshold == 90.0

    def test_update_nonexistent(self, alert_mgr):
        assert alert_mgr.update_watchlist("nonexistent", name="X") is None

    def test_delete_watchlist(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Del", query_values=[1.0, 2.0],
        )
        assert alert_mgr.delete_watchlist(wl.id) is True
        assert alert_mgr.get_watchlist(wl.id) is None

    def test_delete_nonexistent(self, alert_mgr):
        assert alert_mgr.delete_watchlist("nonexistent") is False

    def test_watchlist_with_webhook(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Hook",
            query_values=[1.0, 2.0],
            channels=["log", "webhook"],
            webhook_url="https://example.com/hook",
        )
        fetched = alert_mgr.get_watchlist(wl.id)
        assert fetched.channels == ["log", "webhook"]
        assert fetched.webhook_url == "https://example.com/hook"

    def test_watchlist_with_active_methods(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Methods",
            query_values=[1.0, 2.0],
            active_methods=["dtw", "pearson_warped"],
        )
        fetched = alert_mgr.get_watchlist(wl.id)
        assert fetched.active_methods == ["dtw", "pearson_warped"]


class TestAlertEvaluation:
    def test_alert_fires_above_threshold(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0], threshold=70.0,
            cooldown_seconds=0,  # no cooldown for testing
        )
        matches = [_make_match(score=85.0)]
        alert = alert_mgr.evaluate(wl.id, matches)
        assert alert is not None
        assert alert.confidence_score == 85.0
        assert alert.watchlist_id == wl.id
        assert "85.0" in alert.message

    def test_no_alert_below_threshold(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0], threshold=90.0,
        )
        matches = [_make_match(score=80.0)]
        alert = alert_mgr.evaluate(wl.id, matches)
        assert alert is None

    def test_no_alert_when_disabled(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0], threshold=50.0,
        )
        alert_mgr.update_watchlist(wl.id, enabled=False)
        matches = [_make_match(score=85.0)]
        alert = alert_mgr.evaluate(wl.id, matches)
        assert alert is None

    def test_no_alert_empty_matches(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0], threshold=50.0,
        )
        alert = alert_mgr.evaluate(wl.id, [])
        assert alert is None

    def test_cooldown_prevents_duplicate(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=3600,
        )
        matches = [_make_match(score=85.0)]

        # First alert fires
        alert1 = alert_mgr.evaluate(wl.id, matches)
        assert alert1 is not None

        # Second alert blocked by cooldown
        alert2 = alert_mgr.evaluate(wl.id, matches)
        assert alert2 is None

    def test_alert_selects_best_match(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        matches = [
            _make_match(score=75.0, start=0, end=60),
            _make_match(score=92.0, start=100, end=160),
            _make_match(score=80.0, start=200, end=260),
        ]
        alert = alert_mgr.evaluate(wl.id, matches)
        assert alert is not None
        assert alert.confidence_score == 92.0
        assert alert.match_start_idx == 100

    def test_nonexistent_watchlist_returns_none(self, alert_mgr):
        matches = [_make_match(score=99.0)]
        assert alert_mgr.evaluate("nonexistent", matches) is None


class TestAlertHistory:
    def test_list_alerts(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        alert_mgr.evaluate(wl.id, [_make_match(score=85.0)])
        alert_mgr.evaluate(wl.id, [_make_match(score=90.0)])

        alerts = alert_mgr.list_alerts("u1")
        assert len(alerts) == 2
        # Most recent first
        assert alerts[0].confidence_score == 90.0

    def test_list_alerts_by_watchlist(self, alert_mgr):
        wl1 = alert_mgr.create_watchlist(
            user_id="u1", name="A", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        wl2 = alert_mgr.create_watchlist(
            user_id="u1", name="B", query_values=[3.0, 4.0],
            threshold=70.0, cooldown_seconds=0,
        )
        alert_mgr.evaluate(wl1.id, [_make_match(score=85.0)])
        alert_mgr.evaluate(wl2.id, [_make_match(score=90.0)])

        wl1_alerts = alert_mgr.list_alerts("u1", watchlist_id=wl1.id)
        assert len(wl1_alerts) == 1
        assert wl1_alerts[0].confidence_score == 85.0

    def test_acknowledge_alert(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        alert = alert_mgr.evaluate(wl.id, [_make_match(score=85.0)])
        assert alert is not None
        assert alert.acknowledged is False

        assert alert_mgr.acknowledge_alert(alert.id) is True

        alerts = alert_mgr.list_alerts("u1")
        assert alerts[0].acknowledged is True

    def test_count_alerts(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        alert_mgr.evaluate(wl.id, [_make_match(score=85.0)])
        alert = alert_mgr.evaluate(wl.id, [_make_match(score=90.0)])

        assert alert_mgr.count_alerts("u1") == 2
        assert alert_mgr.count_alerts("u1", unacknowledged_only=True) == 2

        alert_mgr.acknowledge_alert(alert.id)
        assert alert_mgr.count_alerts("u1", unacknowledged_only=True) == 1

    def test_delete_watchlist_deletes_alerts(self, alert_mgr):
        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Test", query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
        )
        alert_mgr.evaluate(wl.id, [_make_match(score=85.0)])
        assert alert_mgr.count_alerts("u1") == 1

        alert_mgr.delete_watchlist(wl.id)
        assert alert_mgr.count_alerts("u1") == 0


class TestCustomNotifier:
    def test_register_and_fire_custom_notifier(self, alert_mgr):
        fired = []

        def custom_notify(alert, watchlist):
            fired.append((alert.confidence_score, watchlist.name))

        alert_mgr.register_notifier("custom", custom_notify)

        wl = alert_mgr.create_watchlist(
            user_id="u1", name="Custom",
            query_values=[1.0, 2.0],
            threshold=70.0, cooldown_seconds=0,
            channels=["custom"],
        )
        alert_mgr.evaluate(wl.id, [_make_match(score=85.0)])

        assert len(fired) == 1
        assert fired[0] == (85.0, "Custom")
