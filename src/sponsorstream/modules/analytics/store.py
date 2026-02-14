"""SQLite-backed analytics store for campaign reporting."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CampaignStats:
    """Aggregated campaign stats for pacing and reporting."""

    impressions: int
    spend: float
    avg_score: float
    avg_pacing_weight: float


class AnalyticsStore:
    """Stores campaign events and provides aggregate reports."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._ensure_parent_dir()
        self._init_schema()

    def _ensure_parent_dir(self) -> None:
        path = Path(self._db_path)
        if path.parent.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    request_id TEXT,
                    placement TEXT,
                    campaign_id TEXT NOT NULL,
                    creative_id TEXT NOT NULL,
                    score REAL,
                    pacing_weight REAL,
                    cost REAL,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaign_events_ts ON campaign_events (ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaign_events_campaign ON campaign_events (campaign_id)"
            )

    def record_match(
        self,
        *,
        ts: datetime,
        request_id: str,
        placement: str,
        campaign_id: str,
        creative_id: str,
        score: float,
        pacing_weight: float,
        cost: float,
        metadata: dict | None = None,
    ) -> None:
        payload = json.dumps(metadata or {})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO campaign_events (
                    ts, event_type, request_id, placement, campaign_id, creative_id,
                    score, pacing_weight, cost, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts.astimezone(timezone.utc).isoformat(),
                    "match",
                    request_id,
                    placement,
                    campaign_id,
                    creative_id,
                    score,
                    pacing_weight,
                    cost,
                    payload,
                ),
            )

    def campaign_stats(
        self,
        campaign_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> CampaignStats:
        clauses = ["campaign_id = ?"]
        params: list[object] = [campaign_id]
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since.astimezone(timezone.utc).isoformat())
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until.astimezone(timezone.utc).isoformat())
        where = " AND ".join(clauses)
        query = (
            "SELECT COUNT(*) AS impressions, "
            "COALESCE(SUM(cost), 0) AS spend, "
            "COALESCE(AVG(score), 0) AS avg_score, "
            "COALESCE(AVG(pacing_weight), 0) AS avg_pacing_weight "
            "FROM campaign_events WHERE " + where
        )
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return CampaignStats(
            impressions=int(row["impressions"] or 0),
            spend=float(row["spend"] or 0.0),
            avg_score=float(row["avg_score"] or 0.0),
            avg_pacing_weight=float(row["avg_pacing_weight"] or 0.0),
        )

    def campaign_report(
        self,
        campaign_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict:
        stats = self.campaign_stats(campaign_id, since=since, until=until)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT creative_id, COUNT(*) AS impressions, AVG(score) AS avg_score
                FROM campaign_events
                WHERE campaign_id = ?
                GROUP BY creative_id
                ORDER BY impressions DESC
                LIMIT 5
                """,
                (campaign_id,),
            ).fetchall()
        top_creatives = [
            {
                "creative_id": row["creative_id"],
                "impressions": int(row["impressions"] or 0),
                "avg_score": float(row["avg_score"] or 0.0),
            }
            for row in rows
        ]
        return {
            "campaign_id": campaign_id,
            "impressions": stats.impressions,
            "spend": stats.spend,
            "avg_score": stats.avg_score,
            "avg_pacing_weight": stats.avg_pacing_weight,
            "top_creatives": top_creatives,
        }

    def summary(self, since: datetime | None = None) -> list[dict]:
        clauses = []
        params: list[object] = []
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since.astimezone(timezone.utc).isoformat())
        where = " AND ".join(clauses) if clauses else "1=1"
        query = (
            "SELECT campaign_id, COUNT(*) AS impressions, COALESCE(SUM(cost), 0) AS spend, "
            "COALESCE(AVG(score), 0) AS avg_score "
            "FROM campaign_events WHERE " + where + " GROUP BY campaign_id ORDER BY spend DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "campaign_id": row["campaign_id"],
                "impressions": int(row["impressions"] or 0),
                "spend": float(row["spend"] or 0.0),
                "avg_score": float(row["avg_score"] or 0.0),
            }
            for row in rows
        ]

    def recent_stats(self, campaign_id: str, window: timedelta) -> CampaignStats:
        since = datetime.now(timezone.utc) - window
        return self.campaign_stats(campaign_id, since=since)
