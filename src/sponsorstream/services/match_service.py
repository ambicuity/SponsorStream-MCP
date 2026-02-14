"""MatchService for campaign/creative matching."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..domain.policy_engine import PolicyEngine
from ..domain.targeting_engine import TargetingEngine
from ..models.mcp_requests import MatchRequest
from ..models.mcp_responses import CreativeCandidate, MatchResponse
from ..modules.analytics.store import AnalyticsStore
from ..modules.pacing.engine import BudgetPacingEngine
from ..ports.embedding import EmbeddingProvider
from ..ports.id_gen import (
    MatchIdProvider,
    RequestIdProvider,
    UuidMatchIdProvider,
    UuidRequestIdProvider,
)
from ..ports.vector_store import VectorHit, VectorStorePort

_WHITESPACE_RE = re.compile(r"\s+")


class MatchService:
    """Orchestrates the full creative-match pipeline."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStorePort,
        targeting_engine: TargetingEngine | None = None,
        policy_engine: PolicyEngine | None = None,
        request_id_provider: RequestIdProvider | None = None,
        match_id_provider: MatchIdProvider | None = None,
        analytics_store: AnalyticsStore | None = None,
        pacing_engine: BudgetPacingEngine | None = None,
        logger: Any = None,
    ) -> None:
        self._embed = embedding_provider
        self._store = vector_store
        self._targeting = targeting_engine or TargetingEngine()
        self._policy = policy_engine or PolicyEngine()
        self._req_id = request_id_provider or UuidRequestIdProvider()
        self._match_id = match_id_provider or UuidMatchIdProvider()
        self._analytics = analytics_store
        self._pacing = pacing_engine or BudgetPacingEngine(analytics_store)
        self._logger = logger

    def match(self, request: MatchRequest) -> tuple[MatchResponse, dict[str, Any]]:
        request_id = self._req_id.new_request_id()
        if self._logger:
            self._logger.info(
                "match_start",
                extra={
                    "trace_id": request_id,
                    "placement": request.placement.placement,
                    "top_k": request.top_k,
                },
            )

        text = _WHITESPACE_RE.sub(" ", request.context_text.strip())
        vector = self._embed.embed(text)
        vector_filter = self._targeting.build_filter(
            request.constraints, request.placement
        )
        raw_hits = self._store.query(
            vector=vector,
            vector_filter=vector_filter,
            top_k=request.top_k,
        )

        eligible = self._policy.apply(
            raw_hits,
            request.constraints,
            request.placement,
            context_text=request.context_text,
        )

        decisions: list[dict[str, Any]] = []
        for hit in raw_hits:
            reason = self._policy.reason(
                hit,
                request.constraints,
                request.placement,
                context_text=request.context_text,
            )
            decisions.append(
                {
                    "creative_id": hit.creative_id,
                    "campaign_id": hit.campaign_id,
                    "score": hit.score,
                    "reason": reason,
                }
            )

        candidates: list[CreativeCandidate] = []
        for hit in eligible:
            pacing = self._pacing.evaluate(hit.payload)
            if not pacing.allow:
                decisions.append(
                    {
                        "creative_id": hit.creative_id,
                        "campaign_id": hit.campaign_id,
                        "score": hit.score,
                        "reason": f"pacing:{pacing.reason}",
                    }
                )
                continue
            candidate = self._hit_to_candidate(hit, request_id, pacing.weight, pacing.reason)
            candidates.append(candidate)
            for d in decisions:
                if d.get("creative_id") == hit.creative_id:
                    d["match_id"] = candidate.match_id
                    d["pacing_weight"] = candidate.pacing_weight
                    break

            if self._analytics is not None:
                estimated_cost = (hit.payload.get("cpm") or 10.0) / 1000.0
                self._analytics.record_match(
                    ts=datetime.now(timezone.utc),
                    request_id=request_id,
                    placement=request.placement.placement,
                    campaign_id=hit.campaign_id,
                    creative_id=hit.creative_id,
                    score=candidate.score,
                    pacing_weight=candidate.pacing_weight,
                    cost=estimated_cost,
                    metadata={"pacing_reason": candidate.pacing_reason},
                )

        response = MatchResponse(
            candidates=candidates,
            request_id=request_id,
            placement=request.placement.placement,
        )
        audit_trace: dict[str, Any] = {
            "request_id": request_id,
            "placement": request.placement.placement,
            "context_text": request.context_text[:500],
            "constraints": request.constraints.model_dump(),
            "decisions": decisions,
        }
        if self._logger:
            self._logger.info(
                "match_done",
                extra={
                    "trace_id": request_id,
                    "placement": request.placement.placement,
                    "candidates_count": len(candidates),
                },
            )
        return response, audit_trace

    def _hit_to_candidate(
        self,
        hit: VectorHit,
        request_id: str,
        pacing_weight: float,
        pacing_reason: str,
    ) -> CreativeCandidate:
        score = max(0.0, min(1.0, hit.score * pacing_weight))
        match_id = self._match_id.new_match_id(request_id, hit.creative_id)
        payload = hit.payload

        return CreativeCandidate(
            creative_id=hit.creative_id,
            campaign_id=hit.campaign_id,
            advertiser_id=hit.advertiser_id,
            campaign_name=payload.get("campaign_name", ""),
            title=payload.get("title", ""),
            body=payload.get("body", ""),
            cta_text=payload.get("cta_text", ""),
            landing_url=payload.get("landing_url", ""),
            score=score,
            match_id=match_id,
            pacing_weight=pacing_weight,
            pacing_reason=pacing_reason,
        )
