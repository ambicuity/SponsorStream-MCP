"""MatchService for campaign/creative matching."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from functools import lru_cache
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

# Simple in-memory cache for match results
_MATCH_CACHE: dict[str, tuple[MatchResponse, dict[str, Any]]] = {}
_CACHE_MAX_SIZE = 100

# Embedding cache for repeated contexts
_EMBEDDING_CACHE: dict[str, list[float]] = {}
_EMBEDDING_CACHE_MAX_SIZE = 500


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
        
        # Use embedding cache to avoid re-embedding identical contexts
        vector = self._get_cached_embedding(text)
        
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

        # Compute boost factors from boost_keywords
        boost_lookup: dict[str, float] = {}
        if request.boost_keywords:
            for keyword, factor in request.boost_keywords.items():
                keyword_lower = keyword.lower()
                boost_lookup[keyword_lower] = max(0.1, min(2.0, factor))  # Clamp [0.1, 2.0]

        decisions: list[dict[str, Any]] = []
        constraint_rejections: dict[str, int] = {}
        
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
            # Track constraint rejection reasons
            if reason.startswith("denied:"):
                constraint = reason.replace("denied: ", "").split(":")[0]
                constraint_rejections[constraint] = constraint_rejections.get(constraint, 0) + 1

        candidates: list[CreativeCandidate] = []
        warnings: list[str] = []
        
        # Check for context quality
        if len(text) < 20:
            warnings.append("context_text too short (< 20 chars); semantic matching may be unreliable")
        
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
                constraint_rejections["pacing"] = constraint_rejections.get("pacing", 0) + 1
                continue
            
            # Compute boost factor for this hit
            boost_factor = 1.0
            for keyword, factor in boost_lookup.items():
                # Check if keyword appears in title, body, or topics
                payload = hit.payload
                title_lower = (payload.get("title") or "").lower()
                body_lower = (payload.get("body") or "").lower()
                topics = [t.lower() for t in (payload.get("topics") or [])]
                
                if keyword in title_lower or keyword in body_lower or keyword in topics:
                    boost_factor = max(boost_factor, factor)
            
            candidate = self._hit_to_candidate(hit, request_id, pacing.weight, pacing.reason, boost_factor)
            candidates.append(candidate)
            for d in decisions:
                if d.get("creative_id") == hit.creative_id:
                    d["match_id"] = candidate.match_id
                    d["pacing_weight"] = candidate.pacing_weight
                    d["boost_applied"] = candidate.boost_applied
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
                    metadata={
                        "pacing_reason": candidate.pacing_reason,
                        "boost_applied": candidate.boost_applied,
                    },
                )

        # Add warning if all eligible candidates are paced
        paced_count = sum(1 for d in decisions if d.get("reason", "").startswith("pacing:"))
        if len(eligible) > 0 and paced_count == len(eligible):
            warnings.append("all eligible creatives are budget-paced; consider relaxing constraints or increasing budget")

        response = MatchResponse(
            candidates=candidates,
            request_id=request_id,
            placement=request.placement.placement,
            warnings=warnings,
            constraint_impact=constraint_rejections if constraint_rejections else None,
        )
        audit_trace: dict[str, Any] = {
            "request_id": request_id,
            "placement": request.placement.placement,
            "context_text": request.context_text[:500],
            "constraints": request.constraints.model_dump(),
            "boost_keywords": request.boost_keywords or {},
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
        boost_factor: float = 1.0,
    ) -> CreativeCandidate:
        score = max(0.0, min(1.0, hit.score * pacing_weight * boost_factor))
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
            boost_applied=boost_factor,
        )
    def match_sample(
        self, request: MatchRequest, sample_size: int = 5
    ) -> tuple[MatchResponse, dict[str, Any]]:
        """Return N random eligible creatives with their match scores (for debugging/testing).
        
        Args:
            request: Match request
            sample_size: Number of random creatives to sample (default 5)
            
        Returns:
            Tuple of MatchResponse and audit trace
        """
        import random
        
        request_id = self._req_id.new_request_id()
        text = _WHITESPACE_RE.sub(" ", request.context_text.strip())
        vector = self._embed.embed(text)
        vector_filter = self._targeting.build_filter(request.constraints, request.placement)
        
        # Get a larger set to sample from
        raw_hits = self._store.query(
            vector=vector,
            vector_filter=vector_filter,
            top_k=min(100, max(sample_size * 3, 50)),  # Get 3x sample_size or at least 50
        )
        
        eligible = self._policy.apply(
            raw_hits, request.constraints, request.placement, context_text=request.context_text
        )
        
        # Randomly sample from eligible
        sample = random.sample(eligible, min(sample_size, len(eligible)))
        candidates: list[CreativeCandidate] = []
        
        for hit in sample:
            pacing = self._pacing.evaluate(hit.payload)
            boost_factor = self._compute_boost_factor(hit, request.boost_keywords or {})
            candidate = self._hit_to_candidate(hit, request_id, pacing.weight, pacing.reason, boost_factor)
            candidates.append(candidate)
        
        response = MatchResponse(
            candidates=candidates,
            request_id=request_id,
            placement=request.placement.placement,
            warnings=[f"Sample of {len(candidates)} random eligible creatives (not ranked)"],
        )
        
        audit_trace = {
            "request_id": request_id,
            "method": "match_sample",
            "sample_size": sample_size,
            "context_text": request.context_text[:250],
        }
        
        return response, audit_trace

    def match_dry_run(
        self,
        request: MatchRequest,
        constraint_overrides: dict[str, Any] | None = None,
    ) -> tuple[MatchResponse, dict[str, Any]]:
        """Simulate a match with temporary constraint changes (for testing).
        
        Args:
            request: Original match request
            constraint_overrides: Constraints to override (e.g., {'age_restricted_ok': True})
            
        Returns:
            Tuple of MatchResponse and audit trace
        """
        # Clone constraints and apply overrides
        overrides = constraint_overrides or {}
        modified_constraints = request.constraints.model_copy(update=overrides)
        
        # Build modified request
        modified_request = request.model_copy(update={"constraints": modified_constraints})
        
        # Run match with modified constraints
        response, audit_trace = self.match(modified_request)
        
        audit_trace["method"] = "match_dry_run"
        audit_trace["constraint_overrides"] = overrides
        
        return response, audit_trace

    def match_batch(
        self, requests: list[MatchRequest], page_size: int = 10
    ) -> list[tuple[MatchResponse, dict[str, Any]]]:
        """Match multiple requests in batch, returning paginated results.
        
        Yields results page by page (not all at once) for better latency profile
        and to allow graceful handling of timeouts.
        
        Args:
            requests: List of match requests
            page_size: Results per page (default 10)
            
        Yields:
            Tuples of (MatchResponse, audit_trace) for each request
        """
        for request in requests:
            try:
                response, trace = self.match(request)
                trace["batch_index"] = requests.index(request)
                yield response, trace
            except Exception as e:
                # Gracefully handle errors in batch
                if self._logger:
                    self._logger.error(
                        "batch_match_error",
                        extra={"error": str(e), "context": request.context_text[:100]},
                    )
                # Yield error response
                yield MatchResponse(
                    candidates=[],
                    request_id="error",
                    placement=request.placement.placement,
                    warnings=[f"Error: {str(e)}"],
                ), {
                    "batch_index": requests.index(request),
                    "error": str(e),
                }

    def _compute_boost_factor(self, hit: VectorHit, boost_keywords: dict[str, float]) -> float:
        """Compute boost factor for a creative based on boost_keywords."""
        boost_factor = 1.0
        for keyword, factor in boost_keywords.items():
            keyword_lower = keyword.lower()
            payload = hit.payload
            title_lower = (payload.get("title") or "").lower()
            body_lower = (payload.get("body") or "").lower()
            topics = [t.lower() for t in (payload.get("topics") or [])]
            
            if keyword_lower in title_lower or keyword_lower in body_lower or keyword_lower in topics:
                boost_factor = max(boost_factor, max(0.1, min(2.0, factor)))
        
        return boost_factor

    def _compute_cache_key(self, request: MatchRequest) -> str:
        """Compute a stable cache key for a request (for caching identical requests)."""
        # Create a hashable representation of the request
        import json
        
        key_dict = {
            "context": request.context_text.strip(),
            "top_k": request.top_k,
            "placement": request.placement.placement,
            "surface": request.placement.surface,
            "constraints": request.constraints.model_dump(),
            "boost_keywords": request.boost_keywords or {},
        }
        
        # Hash the JSON representation
        key_json = json.dumps(key_dict, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()

    def match_cached(self, request: MatchRequest) -> tuple[MatchResponse, dict[str, Any]]:
        """Match with optional caching for identical requests.
        
        Uses simple in-memory LRU cache; respects cache_key and returns None if not found.
        
        Returns:
            Tuple of (MatchResponse, audit_trace) from cache or fresh match
        """
        global _MATCH_CACHE
        
        cache_key = self._compute_cache_key(request)
        
        if cache_key in _MATCH_CACHE:
            response, trace = _MATCH_CACHE[cache_key]
            # Mark as from cache
            trace["source"] = "cache"
            return response, trace
        
        # Execute match
        response, trace = self.match(request)
        trace["source"] = "fresh"
        
        # Store in cache (with simple eviction if full)
        if len(_MATCH_CACHE) >= _CACHE_MAX_SIZE:
            # Remove oldest entry (FIFO)
            _MATCH_CACHE.pop(next(iter(_MATCH_CACHE)))
        
        _MATCH_CACHE[cache_key] = (response, trace)
        
        return response, trace

    @staticmethod
    def clear_cache():
        """Clear the match cache (for testing or memory cleanup)."""
        global _MATCH_CACHE
        _MATCH_CACHE.clear()

    def _get_cached_embedding(self, text: str) -> list[float]:
        """Get embedding for text, using cache if available.
        
        Cache is keyed by SHA256 hash of text for O(1) lookup.
        Automatically evicts LRU when full.
        
        Args:
            text: Preprocessed context text
            
        Returns:
            Embedding vector
        """
        global _EMBEDDING_CACHE
        
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        
        # Return from cache if exists
        if text_hash in _EMBEDDING_CACHE:
            return _EMBEDDING_CACHE[text_hash]
        
        # Compute embedding
        embedding = self._embed.embed(text)
        
        # Store in cache (with simple FIFO eviction if full)
        if len(_EMBEDDING_CACHE) >= _EMBEDDING_CACHE_MAX_SIZE:
            # Remove oldest entry
            _EMBEDDING_CACHE.pop(next(iter(_EMBEDDING_CACHE)))
        
        _EMBEDDING_CACHE[text_hash] = embedding
        
        return embedding

    @staticmethod
    def clear_embedding_cache():
        """Clear the embedding cache (for testing or memory cleanup)."""
        global _EMBEDDING_CACHE
        _EMBEDDING_CACHE.clear()

    @staticmethod
    def get_cache_stats() -> dict[str, Any]:
        """Get current cache statistics for monitoring."""
        return {
            "match_cache_size": len(_MATCH_CACHE),
            "match_cache_max": _CACHE_MAX_SIZE,
            "embedding_cache_size": len(_EMBEDDING_CACHE),
            "embedding_cache_max": _EMBEDDING_CACHE_MAX_SIZE,
        }
