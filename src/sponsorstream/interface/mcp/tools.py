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
    "boost_applied",
})
ALLOWED_MATCH_RESPONSE_KEYS = frozenset({"candidates", "request_id", "placement", "warnings", "constraint_impact"})
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


def _generate_recommendations(trace: dict, constraint_rejections: dict, accepted_count: int) -> list[str]:
    """Generate actionable recommendations based on match results."""
    recommendations = []
    
    # If no candidates were accepted, suggest constraint relaxation
    if accepted_count == 0:
        recommendations.append("No candidates matched. Consider relaxing constraints: age_restricted_ok, sensitive_ok, or removing audience_segments filters")
    
    # Identify overly restrictive constraints
    for constraint, count in constraint_rejections.items():
        if count > 5:
            if constraint == "age_restricted":
                recommendations.append("age_restricted constraint is blocking many candidates. Try setting age_restricted_ok=true")
            elif constraint == "sensitive":
                recommendations.append("sensitive constraint is blocking many candidates. Try setting sensitive_ok=true")
            elif constraint in ["locale", "verticals", "audience_segments"]:
                recommendations.append(f"'{constraint}' is very restrictive (blocking {count}+ candidates). Consider broadening or removing this constraint")
            elif constraint == "pacing":
                recommendations.append("Budget pacing is blocking many eligible candidates. Consider increasing your campaign budget or relaxing schedule")
    
    # If very few constraints are being used, suggest adding more for better targeting
    active_constraints = sum(1 for k, v in trace.get("constraints", {}).items() if v)
    if active_constraints < 2:
        recommendations.append("Few constraints are active. Consider adding topics, audience_segments, or verticals for better targeting")
    
    # Suggest using boost_keywords if not already
    if not trace.get("boost_keywords"):
        recommendations.append("Tip: Use boost_keywords parameter to promote creatives with specific topics")
    
    return recommendations if recommendations else ["Match results look good. Consider A/B testing different constraint combinations."]


# ---------------------------------------------------------------------------
# Engine tools
# ---------------------------------------------------------------------------
ENGINE_ALLOWED_TOOLS = frozenset({
    "campaigns_match",
    "campaigns_match_template",
    "campaigns_match_sample",
    "campaigns_match_dry_run",
    "campaigns_explain",
    "campaigns_health",
    "campaigns_capabilities",
    "campaigns_diagnostics",
    "campaigns_metrics",
    "campaigns_suggest_constraints",
    "campaigns_validate",
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
        boost_keywords: dict[str, float] | None = None,
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
            boost_keywords: Optional boost factors for keywords (e.g. {'python': 1.5, 'ai': 1.2})

        Returns:
            JSON with candidates (creative_id, title, cta_text, landing_url, score, match_id, boost_applied), request_id, placement, warnings, constraint_impact
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
            boost_keywords=boost_keywords,
        )
        service = _get_match_service()
        response, audit_trace = service.match(request)
        _store_trace_for_explain(response, audit_trace)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_match", response.request_id, latency_ms, extra={"candidates_count": len(response.candidates)})
        return json.dumps(_shape_match_response(response), indent=2)


    @mcp.tool()
    def campaigns_explain(match_id: str) -> str:
        """Return detailed audit trace for a prior match (why eligible/ineligible, filters, scores).

        Args:
            match_id: Opaque ID returned with each candidate from campaigns_match

        Returns:
            JSON trace with request_id, placement, context_text, constraints, decisions, boost factors, and constraint impact analysis
        """
        trace = _trace_store.get(match_id)
        if trace is None:
            return json.dumps({"error": "match_id not found", "match_id": match_id})
        
        # Enhance trace with analysis and recommendations
        enhanced = trace.copy()
        
        # Add constraint impact analysis
        decisions = trace.get("decisions", [])
        constraint_rejections = {}
        rejected_by_policy = []
        rejected_by_pacing = []
        accepted = []
        
        for d in decisions:
            reason = d.get("reason", "")
            if reason == "allowed":
                accepted.append(d)
            elif reason.startswith("pacing:"):
                rejected_by_pacing.append((d, d["reason"]))
                constraint_rejections["pacing"] = constraint_rejections.get("pacing", 0) + 1
            elif reason.startswith("denied:"):
                constraint = reason.replace("denied: ", "").split(":")[0]
                rejected_by_policy.append((d, reason))
                constraint_rejections[constraint] = constraint_rejections.get(constraint, 0) + 1
        
        # Build analysis summary
        enhanced["analysis"] = {
            "total_candidates": len(decisions),
            "accepted": len(accepted),
            "rejected_by_policy": len(rejected_by_policy),
            "rejected_by_pacing": len(rejected_by_pacing),
            "constraint_impact": constraint_rejections,
            "recommendations": _generate_recommendations(trace, constraint_rejections, len(accepted)),
        }
        
        # Add boost factors if present
        if "boost_keywords" in trace and trace["boost_keywords"]:
            enhanced["boost_analysis"] = {
                "keywords": trace["boost_keywords"],
                "applied_to_candidates": sum(
                    1 for d in decisions if d.get("boost_applied", 1.0) > 1.0
                )
            }
        
        return json.dumps(enhanced, indent=2)


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
            "features": [
                "boost_keywords",
                "match_sample",
                "match_dry_run",
                "diagnostics",
                "metrics",
                "constraint_suggestions",
            ],
        })

    @mcp.tool()
    def campaigns_match_sample(
        context_text: str,
        sample_size: int = 5,
        placement: str = "inline",
        surface: str = "chat",
        topics: list[str] | None = None,
        locale: str | None = None,
        verticals: list[str] | None = None,
        audience_segments: list[str] | None = None,
        age_restricted_ok: bool = False,
        sensitive_ok: bool = False,
    ) -> str:
        """Return N random eligible creatives (for debugging and testing).

        Args:
            context_text: Context to match against
            sample_size: Number of random creatives to sample (1-100, default 5)
            placement: Placement slot
            surface: Surface type
            topics: Filter topics
            locale: Filter locale
            verticals: Filter verticals
            audience_segments: Filter audience segments
            age_restricted_ok: Allow age-restricted
            sensitive_ok: Allow sensitive

        Returns:
            JSON with random sample of candidates and audit info (not ranked by relevance)
        """
        t0 = time.monotonic()
        request = MatchRequest(
            context_text=context_text[:10_000],
            top_k=max(1, min(100, sample_size)),
            placement=PlacementContext(placement=placement, surface=surface),
            constraints=MatchConstraints(
                topics=topics,
                locale=locale,
                verticals=verticals,
                audience_segments=audience_segments,
                age_restricted_ok=age_restricted_ok,
                sensitive_ok=sensitive_ok,
            ),
        )
        service = _get_match_service()
        response, audit_trace = service.match_sample(request, sample_size=sample_size)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_match_sample", response.request_id, latency_ms)
        return json.dumps(_shape_match_response(response), indent=2)

    @mcp.tool()
    def campaigns_match_dry_run(
        context_text: str,
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
        age_restricted_ok: bool | None = None,
        sensitive_ok: bool | None = None,
    ) -> str:
        """Simulate matching with different constraints (for testing without pacing/analytics impact).

        Args:
            context_text: Context to match
            placement: Placement slot
            surface: Surface type
            topics: Override topics filter
            locale: Override locale filter
            verticals: Override verticals
            audience_segments: Override audience segments
            keywords: Override keywords
            exclude_advertiser_ids: Override advertiser exclusions
            exclude_campaign_ids: Override campaign exclusions
            exclude_creative_ids: Override creative exclusions
            age_restricted_ok: Override age restriction (None means keep original)
            sensitive_ok: Override sensitive content (None means keep original)

        Returns:
            JSON with match results for the modified constraints
        """
        t0 = time.monotonic()
        request = MatchRequest(
            context_text=context_text[:10_000],
            placement=PlacementContext(placement=placement, surface=surface),
            constraints=MatchConstraints(
                topics=topics,
                locale=locale,
                verticals=verticals,
                audience_segments=audience_segments,
                keywords=keywords,
                exclude_advertiser_ids=exclude_advertiser_ids,
                exclude_campaign_ids=exclude_campaign_ids,
                exclude_creative_ids=exclude_creative_ids,
                age_restricted_ok=False,
                sensitive_ok=False,
            ),
        )
        
        # Build overrides
        overrides = {}
        if age_restricted_ok is not None:
            overrides["age_restricted_ok"] = age_restricted_ok
        if sensitive_ok is not None:
            overrides["sensitive_ok"] = sensitive_ok
        
        service = _get_match_service()
        response, audit_trace = service.match_dry_run(request, overrides)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_match_dry_run", response.request_id, latency_ms)
        return json.dumps(_shape_match_response(response), indent=2)

    @mcp.tool()
    def campaigns_match_template(
        template_name: str,
        context_text: str,
        locale: str | None = None,
        topics: list[str] | None = None,
        verticals: list[str] | None = None,
        audience_segments: list[str] | None = None,
    ) -> str:
        """Match using a pre-built template (inline_chat, sidebar_article, banner_homepage, search_results, testing).

        Args:
            template_name: Name of template ("inline_chat", "sidebar_article", "banner_homepage", "search_results", or "testing")
            context_text: The content to match against
            locale: Override locale (optional)
            topics: Override topics filter (optional)
            verticals: Override verticals (optional)
            audience_segments: Override audience_segments (optional)

        Returns:
            JSON with matched creatives using template-optimized constraints
        """
        from .request_templates import get_template
        
        template_fn = get_template(template_name)
        if template_fn is None:
            return json.dumps({
                "error": f"Unknown template: {template_name}",
                "available_templates": ["inline_chat", "sidebar_article", "banner_homepage", "search_results", "testing"]
            })
        
        t0 = time.monotonic()
        
        # Build request with template
        try:
            # Special handling for each template type
            if template_name == "inline_chat":
                request = template_fn(
                    context_text=context_text,
                    locale=locale or "en-US",
                    topics=topics,
                    audience_segments=audience_segments,
                )
            elif template_name == "sidebar_article":
                request = template_fn(
                    context_text=context_text,
                    verticals=verticals,
                    audience_segments=audience_segments,
                    topics=topics,
                )
            elif template_name == "banner_homepage":
                request = template_fn(
                    context_text=context_text,
                    locale=locale or "en-US",
                    verticals=verticals,
                )
            elif template_name == "search_results":
                request = template_fn(
                    query=context_text,
                    topics=topics,
                    audience_segments=audience_segments,
                    locale=locale or "en-US",
                )
            else:  # testing
                request = template_fn(context_text=context_text)
        except Exception as e:
            return json.dumps({"error": f"Failed to build request from template: {str(e)}"})
        
        service = _get_match_service()
        response, audit_trace = service.match(request)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_match_template", response.request_id, latency_ms, extra={"template": template_name})
        return json.dumps(_shape_match_response(response), indent=2)

    @mcp.tool()
    def campaigns_diagnostics() -> str:
        """Diagnostic health check: collection status, budget constraints, schedule issues.

        Returns:
            JSON with collection health, active campaigns, and common blocking reasons
        """
        try:
            service = _get_index_service()
            info = service.collection_info()
            return json.dumps({
                "status": "ok",
                "collection": _shape_collection_info(info),
                "note": "Use campaigns_match with test context to identify specific matching issues"
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    @mcp.tool()
    def campaigns_metrics(since_hours: int = 24, campaign_id: str | None = None) -> str:
        """Get matching performance metrics: success rate, score distribution, constraint impact.

        Args:
            since_hours: Look back N hours (1-720, default 24)
            campaign_id: Optional: filter to specific campaign

        Returns:
            JSON with match success rate, score distribution, and constraint rejection rates
        """
        settings = get_settings()
        store = AnalyticsStore(settings.analytics_db_path)
        
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(720, since_hours)))
        summary = store.summary(since=since)
        
        if campaign_id:
            report = store.campaign_report(campaign_id, since=since)
            return json.dumps({
                "campaign_id": campaign_id,
                "since_hours": since_hours,
                "report": report
            })
        
        return json.dumps({
            "since_hours": since_hours,
            "summary": summary,
            "note": "Top-level metrics; use campaigns_report for detailed campaign analysis"
        })

    @mcp.tool()
    def campaigns_suggest_constraints(context_text: str) -> str:
        """Suggest optimal constraints for a given context (based on text analysis).

        Args:
            context_text: The content or conversation to analyze

        Returns:
            JSON with suggested topics, audience_segments, locale, verticals, and confidence scores
        """
        # Simple heuristic-based suggestion (can be enhanced with ML in production)
        text_lower = context_text.lower()
        
        suggestions = {
            "topics": [],
            "audience_segments": [  ],
            "locale": "en-US",  # Default
            "verticals": [],
            "confidence": {
                "topics": 0.7,
                "audience_segments": 0.6,
                "locale": 0.5,
                "verticals": 0.7,
            },
            "note": "These are heuristic suggestions; refine based on your domain knowledge"
        }
        
        # Simple keyword-based suggestions
        topic_keywords = {
            "python": ["python", "django", "fastapi"],
            "javascript": ["javascript", "nodejs", "react", "vue"],
            "kubernetes": ["kubernetes", "k8s", "docker", "container"],
            "machine-learning": ["machine learning", "ml", "ai", "tensorflow", "pytorch"],
            "devops": ["devops", "ci/cd", "jenkins", "terraform"],
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                suggestions["topics"].append(topic)
        
        # Audience suggestions based on role keywords
        if any(w in text_lower for w in ["code", "develop", "debug", "javascript", "python"]):
            suggestions["audience_segments"].append("developers")
        if any(w in text_lower for w in ["kubernetes", "devops", "deploy", "infrastructure"]):
            suggestions["audience_segments"].append("devops-engineers")
        if any(w in text_lower for w in ["data", "analytics", "machine learning", "model"]):
            suggestions["audience_segments"].append("data-scientists")
        
        # Vertical suggestions
        if any(w in text_lower for w in ["software", "code", "development", "api"]):
            suggestions["verticals"].append("technology")
        if any(w in text_lower for w in ["financial", "banking", "trading"]):
            suggestions["verticals"].append("finance")
        if any(w in text_lower for w in ["health", "medical", "patient"]):
            suggestions["verticals"].append("healthcare")
        
        return json.dumps(suggestions, indent=2)

    @mcp.tool()
    def campaigns_validate(
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
        boost_keywords: dict[str, float] | None = None,
    ) -> str:
        """Validate a match request and estimate difficulty without executing (read-only).

        Args:
            context_text: Conversational / page context (max 10000 chars)
            top_k: Number of candidates (1-100)
            placement: Placement slot (e.g. 'inline', 'sidebar', 'banner')
            surface: Surface type (e.g. 'chat', 'search', 'feed')
            topics: Restrict to these topics
            locale: Required locale (e.g. 'en-US')
            verticals: Restrict to these verticals
            audience_segments: Restrict to these audience segments
            keywords: Restrict to these context keywords
            exclude_advertiser_ids: Advertiser IDs to exclude
            exclude_campaign_ids: Campaign IDs to exclude
            exclude_creative_ids: Creative IDs to exclude
            age_restricted_ok: Allow age-restricted campaigns
            sensitive_ok: Allow sensitive-content campaigns
            boost_keywords: Optional boost factors for keywords

        Returns:
            JSON with validation result (errors, warnings, difficulty_score, recommendations)
        """
        from ..validation import validate_and_estimate
        
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
            boost_keywords=boost_keywords,
        )
        
        result = validate_and_estimate(request)
        latency_ms = (time.monotonic() - t0) * 1000
        log_tool_invocation("campaigns_validate", request.request_id, latency_ms)
        
        return json.dumps(result.to_dict(), indent=2)






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
