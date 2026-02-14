"""Budget pacing engine for campaign delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..analytics.store import AnalyticsStore


@dataclass(frozen=True)
class PacingDecision:
    """Decision returned by the pacing engine."""

    allow: bool
    weight: float
    reason: str


class BudgetPacingEngine:
    """Simple pacing engine with adaptive adjustments."""

    def __init__(self, analytics_store: AnalyticsStore | None = None) -> None:
        self._analytics = analytics_store

    def evaluate(self, payload: dict) -> PacingDecision:
        campaign_id = payload.get("campaign_id")
        if not campaign_id or self._analytics is None:
            return PacingDecision(allow=True, weight=1.0, reason="no_analytics")

        total_budget = payload.get("total_budget")
        daily_budget = payload.get("daily_budget")
        pacing_mode = payload.get("pacing_mode") or "even"
        cpm = payload.get("cpm") or 10.0
        target_ctr = payload.get("target_ctr")
        cost_per_impression = cpm / 1000.0

        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        today_stats = self._analytics.campaign_stats(campaign_id, since=today_start)
        total_stats = self._analytics.campaign_stats(campaign_id)

        spent_today = today_stats.spend
        spent_total = total_stats.spend

        if total_budget is not None and spent_total >= total_budget:
            return PacingDecision(allow=False, weight=0.0, reason="total_budget_exhausted")
        if daily_budget is not None and spent_today >= daily_budget:
            return PacingDecision(allow=False, weight=0.0, reason="daily_budget_exhausted")

        weight = 1.0
        if daily_budget is not None and daily_budget > 0:
            elapsed = (now - today_start).total_seconds()
            expected = daily_budget * (elapsed / 86400.0)
            if expected > 0 and spent_today > expected:
                over_ratio = spent_today / expected
                if pacing_mode == "accelerated":
                    weight = 1.0
                else:
                    weight = max(0.1, 1.0 / over_ratio)

        if pacing_mode == "adaptive" and target_ctr is not None:
            recent_stats = self._analytics.recent_stats(campaign_id, window=timedelta(hours=1))
            if recent_stats.avg_score < target_ctr:
                weight = max(0.1, weight * 0.8)

        reason = "paced" if weight < 1.0 else "within_budget"
        return PacingDecision(allow=True, weight=weight, reason=reason)
