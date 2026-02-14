"""Tool registry for MCP servers.

Strict JSON schemas via Pydantic; request shaping (limits, timeouts);
response allowlists (field-level).
"""

from __future__ import annotations

import json
import time
from typing import Any

from .observability import log_tool_invocation

from sponsorstream.config.runtime import get_settings
from sponsorstream.domain.sponsorship import Campaign, Creative
from sponsorstream.models.mcp_requests import MatchConstraints, MatchRequest, PlacementContext
from sponsorstream.modules.analytics.store import AnalyticsStore

# ---------------------------------------------------------------------------
# Response allowlists (field-level)
# ---------------------------------------------------------------------------
ALLOWED_MATCH_CANDIDATE_KEYS = frozenset({
    "creative_id",
    "campaign_id",
    "advertiser_id",
    "campaign_name",
    "title",
    "body",
    "cta_text",
    "landing_url",
    "score",
    "match_id",
    "pacing_weight",
    "pacing_reason",
})
ALLOWED_MATCH_RESPONSE_KEYS = frozenset({"candidates", "request_id", "placement"})
ALLOWED_COLLECTION_INFO_KEYS = frozenset({
    "name", "points_count", "indexed_vectors_count", "status",
    "dimension", "embedding_model_id", "schema_version",
})
ALLOWED_COLLECTION_ENSURE_KEYS = frozenset({"name", "created", "dimension", "embedding_model_id", "schema_version"})
ALLOWED_CREATIVES_GET_KEYS = frozenset({
    "creative_id",
    "campaign_id",
    "advertiser_id",
    "campaign_name",
    "title",
    "body",
    "cta_text",
    "landing_url",
    "topics",
    "locale",
    "verticals",
    "blocked_keywords",
    "audience_segments",
    "keywords",
    "sensitive",
    "age_restricted",
    "brand_safety_tier",
    "start_at",
    "end_at",
    "total_budget",
    "daily_budget",
    "currency",
    "pacing_mode",
    "cpm",
    "target_ctr",
    "enabled",
})

# In-memory trace store for campaigns.explain (match_id -> audit_trace), optional TTL
_trace_store: dict[str, dict[str, Any]] = {}
_TRACE_STORE_MAX = 10_000


def _shape_match_response(response: Any) -> dict:
    """Return only allowed fields for campaigns.match response."""
    d = response.model_dump() if hasattr(response, "model_dump") else response
    out: dict = {k: d[k] for k in ALLOWED_MATCH_RESPONSE_KEYS if k in d}
    if "candidates" in out:
        out["candidates"] = [
            {k: c.get(k) for k in ALLOWED_MATCH_CANDIDATE_KEYS if k in c}
            for c in out["candidates"]
        ]
    return out


def _shape_collection_info(d: dict) -> dict:
    return {k: d[k] for k in ALLOWED_COLLECTION_INFO_KEYS if k in d}


def _shape_collection_ensure(d: dict) -> dict:
    return {k: d[k] for k in ALLOWED_COLLECTION_ENSURE_KEYS if k in d}


def _shape_creatives_get(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    return {k: payload[k] for k in ALLOWED_CREATIVES_GET_KEYS if k in payload}


def _store_trace_for_explain(response: Any, audit_trace: dict[str, Any]) -> None:
    """Store audit trace keyed by each match_id for campaigns.explain."""
    global _trace_store
    candidates = getattr(response, "candidates", []) or []
    for c in candidates:
        match_id = getattr(c, "match_id", None) or (c.get("match_id") if isinstance(c, dict) else None)
        if match_id:
            _trace_store[match_id] = audit_trace
    while len(_trace_store) > _TRACE_STORE_MAX:
        # Drop oldest (arbitrary)
        _trace_store.pop(next(iter(_trace_store)))


def _get_match_service():
    from ..wiring import build_match_service
    return build_match_service()


def _get_index_service():
    from ..wiring import build_index_service
    return build_index_service()


# ---------------------------------------------------------------------------
# Engine tools
# ---------------------------------------------------------------------------
ENGINE_ALLOWED_TOOLS = frozenset({
    "campaigns_match",
    "campaigns_explain",
    "campaigns_health",
    "campaigns_capabilities",
})


def register_engine_tools(mcp):
    """Register Engine (runtime / LLM-facing) tools with request shaping and response allowlist."""

    @mcp.tool()
    def campaigns_match(
        context_text: str,
        top_k: int = 5,
        placement: str = "inline",
        surface: str = "chat",
        topics: list[str] | None = None,
        locale: str | None = None,
        verticals: list[str] | None = None,
        audience_segments: list[str] | None = None,
        keywords: list[str] | None = None,
        exclude_advertiser_ids: list[str] | None = None,
        exclude_campaign_ids: list[str] | None = None,
        exclude_creative_ids: list[str] | None = None,
        age_restricted_ok: bool = False,
        sensitive_ok: bool = False,
    ) -> str:
        """Match campaigns by semantic context (read-only). Returns ranked candidates and match_id for explain.

        Args:
            context_text: Conversational / page context to match against (max 10000 chars)
            top_k: Number of candidates (1-100, default 5)
            placement: Placement slot (e.g. 'inline', 'sidebar', 'banner')
            surface: Surface type (e.g. 'chat', 'search', 'feed')
            topics: Restrict to these topics
            locale: Required locale (e.g. 'en-US')
            verticals: Restrict to these verticals
            exclude_advertiser_ids: Advertiser IDs to exclude
            audience_segments: Restrict to these audience segments
            keywords: Restrict to these context keywords
            exclude_campaign_ids: Campaign IDs to exclude
            exclude_creative_ids: Creative IDs to exclude
            age_restricted_ok: Allow age-restricted campaigns
            sensitive_ok: Allow sensitive-content campaigns

        Returns:
            JSON with candidates (creative_id, title, cta_text, landing_url, score, match_id), request_id, placement
        """
        t0 = time.monotonic()
        request = MatchRequest(
            context_text=context_text[:10_000],
            top_k=max(1, min(100, top_k)),
            placement=PlacementContext(placement=placement, surface=surface),
            constraints=MatchConstraints(
                topics=topics,
                locale=locale,
                verticals=verticals,
                exclude_advertiser_ids=exclude_advertiser_ids,
                audience_segments=audience_segments,
                keywords=keywords,
                exclude_campaign_ids=exclude_campaign_ids,
                exclude_creative_ids=exclude_creative_ids,
                age_restricted_ok=age_restricted_ok,
                sensitive_ok=sensitive_ok,
            ),
        )
        service = _get_match_service()
        response, audit_trace = service.match(request)
        _store_trace_for_explain(response, audit_trace)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_match", response.request_id, latency_ms, extra={"candidates_count": len(response.candidates)})
        return json.dumps(_shape_match_response(response), indent=2)

    @mcp.tool()
    def campaigns_explain(match_id: str) -> str:
        """Return audit trace for a prior match (why eligible/ineligible, filters, scores).

        Args:
            match_id: Opaque ID returned with each candidate from campaigns_match

        Returns:
            JSON trace with request_id, placement, context_text, constraints, decisions (creative_id, score, reason)
        """
        trace = _trace_store.get(match_id)
        if trace is None:
            return json.dumps({"error": "match_id not found", "match_id": match_id})
        return json.dumps(trace, indent=2)

    @mcp.tool()
    def campaigns_health() -> str:
        """Liveness/readiness: Qdrant and embedding provider reachable."""
        try:
            from ..ops.smoke_check import run_smoke_check
            result = run_smoke_check()
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @mcp.tool()
    def campaigns_capabilities() -> str:
        """Supported placements, constraint keys, embedding model, schema version."""
        settings = get_settings()
        info = _get_index_service().collection_info()
        if isinstance(info, dict):
            embedding_model_id = info.get("embedding_model_id") or settings.embedding_model_id
            schema_version = info.get("schema_version") or "1"
        else:
            embedding_model_id = settings.embedding_model_id
            schema_version = "1"
        return json.dumps({
            "placements": ["inline", "sidebar", "banner"],
            "constraint_keys": [
                "topics",
                "locale",
                "verticals",
                "audience_segments",
                "keywords",
                "exclude_advertiser_ids",
                "exclude_campaign_ids",
                "exclude_creative_ids",
                "age_restricted_ok",
                "sensitive_ok",
            ],
            "embedding_model_id": embedding_model_id,
            "schema_version": schema_version,
        })


# ---------------------------------------------------------------------------
# Studio tools
# ---------------------------------------------------------------------------

def register_studio_tools(mcp):
    """Register Studio (admin) tools with response allowlists."""

    @mcp.tool()
    def collection_ensure(
        dimension: int = 384,
        embedding_model_id: str = "BAAI/bge-small-en-v1.5",
        schema_version: str = "1",
    ) -> str:
        """Ensure the campaigns collection exists with the given config.

        Args:
            dimension: Embedding vector dimension
            embedding_model_id: Model used for embeddings
            schema_version: Schema version tag

        Returns:
            JSON with name, created, dimension, embedding_model_id, schema_version
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        svc = _get_index_service()
        result = svc.ensure_collection(
            dimension=dimension,
            embedding_model_id=embedding_model_id,
            schema_version=schema_version,
        )
        return json.dumps(_shape_collection_ensure(result))

    @mcp.tool()
    def collection_info() -> str:
        """Return metadata about the current campaigns collection.

        Returns:
            JSON with name, points_count, status, dimension, embedding_model_id, schema_version
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        result = _get_index_service().collection_info()
        return json.dumps(_shape_collection_info(result))

    @mcp.tool()
    def collection_migrate(from_version: str, to_version: str) -> str:
        """Optional: run schema migrations / re-index between versions.

        Args:
            from_version: Current schema version
            to_version: Target schema version

        Returns:
            JSON status
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        return json.dumps({
            "status": "noop",
            "message": "collection_migrate not implemented",
            "from_version": from_version,
            "to_version": to_version,
        })

    @mcp.tool()
    def campaigns_upsert_batch(campaigns_json: str) -> str:
        """Upsert a batch of campaigns/creatives. Size limit from config.

        Args:
            campaigns_json: JSON array of campaign or creative objects

        Returns:
            JSON with upserted count
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        settings = get_settings()
        raw = json.loads(campaigns_json)
        if not isinstance(raw, list):
            return json.dumps({"error": "campaigns_json must be a JSON array"})
        items: list[Campaign | Creative] = []
        for i, item in enumerate(raw):
            try:
                items.append(Campaign.model_validate(item))
                continue
            except Exception:
                pass
            try:
                items.append(Creative.model_validate(item))
            except Exception as e:
                return json.dumps({"error": f"invalid campaign/creative at index {i}", "detail": str(e)})
        items = items[: settings.max_batch_size]
        svc = _get_index_service()
        count = svc.upsert_campaigns(items)
        return json.dumps({"upserted": count})

    @mcp.tool()
    def creatives_delete(creative_id: str) -> str:
        """Delete a single creative by ID.

        Args:
            creative_id: The creative identifier to delete

        Returns:
            JSON confirmation
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        _get_index_service().delete_creative(creative_id)
        return json.dumps({"deleted": creative_id})

    @mcp.tool()
    def campaigns_bulk_disable(filter_json: str) -> str:
        """Set enabled=false for all creatives matching the filter.

        Args:
            filter_json: JSON object e.g. {"advertiser_id": "x"} or {"creative_id": ["a","b"]}

        Returns:
            JSON with count of disabled creatives
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        try:
            filter_spec = json.loads(filter_json)
        except Exception as e:
            return json.dumps({"error": "invalid filter_json", "detail": str(e)})
        if not isinstance(filter_spec, dict):
            return json.dumps({"error": "filter_json must be a JSON object"})
        count = _get_index_service().bulk_disable(filter_spec)
        return json.dumps({"disabled": count})

    @mcp.tool()
    def creatives_get(creative_id: str) -> str:
        """Get a single creative by ID (debugging).

        Args:
            creative_id: The creative identifier

        Returns:
            JSON with creative payload (allowlisted fields)
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        payload = _get_index_service().get_creative(creative_id)
        if payload is None:
            return json.dumps({"error": "not found", "creative_id": creative_id})
        payload.setdefault("enabled", True)
        shaped = _shape_creatives_get(payload)
        return json.dumps(shaped or payload)

    @mcp.tool()
    def campaigns_report(campaign_id: str | None = None, since_hours: int = 24) -> str:
        """Return analytics summary or a single campaign report.

        Args:
            campaign_id: Optional campaign ID for detailed report
            since_hours: Window for summary aggregation

        Returns:
            JSON with analytics summary or campaign report
        """
        from ..mcp.auth import require_studio_scope
        require_studio_scope()
        settings = get_settings()
        store = AnalyticsStore(settings.analytics_db_path)
        if campaign_id:
            report = store.campaign_report(campaign_id)
            return json.dumps(report)
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(hours=max(1, since_hours))
        summary = store.summary(since=since)
        return json.dumps({"since_hours": since_hours, "campaigns": summary})
