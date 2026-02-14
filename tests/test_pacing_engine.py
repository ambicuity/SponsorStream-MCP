"""Tests for the BudgetPacingEngine."""

from datetime import datetime, timezone

from sponsorstream.modules.analytics.store import AnalyticsStore
from sponsorstream.modules.pacing.engine import BudgetPacingEngine


def test_pacing_allows_without_analytics():
    engine = BudgetPacingEngine(None)
    decision = engine.evaluate({"campaign_id": "camp-1"})
    assert decision.allow is True
    assert decision.weight == 1.0


def test_pacing_blocks_when_daily_budget_exhausted(tmp_path):
    db_path = tmp_path / "analytics.db"
    store = AnalyticsStore(str(db_path))
    store.record_match(
        ts=datetime.now(timezone.utc),
        request_id="req-1",
        placement="inline",
        campaign_id="camp-1",
        creative_id="cr-1",
        score=0.9,
        pacing_weight=1.0,
        cost=1.0,
    )
    engine = BudgetPacingEngine(store)
    decision = engine.evaluate(
        {
            "campaign_id": "camp-1",
            "daily_budget": 0.5,
            "total_budget": 10.0,
            "cpm": 1000.0,
            "pacing_mode": "even",
        }
    )
    assert decision.allow is False
    assert decision.reason == "daily_budget_exhausted"
