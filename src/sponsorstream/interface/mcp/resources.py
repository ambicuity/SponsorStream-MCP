"""MCP Resources for SponsorStream campaign discovery.

Exposes campaign catalog, creative templates, and targeting schema as discoverable resources.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.types import TextResourceContents, ResourceTemplate


def get_campaign_catalog_resource() -> dict[str, Any]:
    """Return the campaigns collection metadata and sample campaigns."""
    from ..wiring import build_index_service
    
    service = build_index_service()
    info = service.collection_info()
    
    return {
        "uri": "sponsorstream://catalog/campaigns",
        "name": "Campaign Catalog",
        "description": "Active campaigns and creatives in the collection",
        "mimeType": "application/json",
        "contents": json.dumps({
            "collection": info,
            "samples": _get_sample_campaigns(),
        }, indent=2)
    }


def get_targeting_schema_resource() -> dict[str, Any]:
    """Return targeting and constraint schema."""
    return {
        "uri": "sponsorstream://schema/targeting",
        "name": "Targeting Schema",
        "description": "Valid constraint fields, types, and examples for campaigns.match",
        "mimeType": "application/json",
        "contents": json.dumps({
            "constraint_keys": [
                {
                    "name": "topics",
                    "type": "list[str]",
                    "description": "Restrict to campaigns with these topics",
                    "example": ["python", "ai", "machine-learning"]
                },
                {
                    "name": "locale",
                    "type": "str",
                    "description": "Require exact locale match (e.g., 'en-US')",
                    "example": "en-US"
                },
                {
                    "name": "verticals",
                    "type": "list[str]",
                    "description": "Restrict to these industry verticals",
                    "example": ["technology", "finance"]
                },
                {
                    "name": "audience_segments",
                    "type": "list[str]",
                    "description": "Target specific audience segments",
                    "example": ["developers", "data-scientists"]
                },
                {
                    "name": "keywords",
                    "type": "list[str]",
                    "description": "Additional keyword targeting",
                    "example": ["kubernetes", "docker"]
                },
                {
                    "name": "exclude_advertiser_ids",
                    "type": "list[str]",
                    "description": "Exclude specific advertisers",
                    "example": ["adv-123", "adv-456"]
                },
                {
                    "name": "exclude_campaign_ids",
                    "type": "list[str]",
                    "description": "Exclude specific campaigns",
                    "example": ["camp-xyz"]
                },
                {
                    "name": "exclude_creative_ids",
                    "type": "list[str]",
                    "description": "Exclude specific creatives",
                    "example": ["cr-abc", "cr-def"]
                },
                {
                    "name": "age_restricted_ok",
                    "type": "bool",
                    "description": "Allow age-restricted campaigns (default false)",
                    "example": False
                },
                {
                    "name": "sensitive_ok",
                    "type": "bool",
                    "description": "Allow sensitive-content campaigns (default false)",
                    "example": False
                },
            ],
            "placements": ["inline", "sidebar", "banner"],
            "surfaces": ["chat", "search", "feed"],
        }, indent=2)
    }


def get_placement_templates_resource() -> dict[str, Any]:
    """Return placement-specific context templates for agents."""
    return {
        "uri": "sponsorstream://templates/placements",
        "name": "Placement Templates",
        "description": "Example contexts and constraints for different placements",
        "mimeType": "application/json",
        "contents": json.dumps({
            "inline": {
                "description": "Inline ad within conversational context",
                "example_context": "User is asking about Python async programming best practices...",
                "recommended_constraints": {
                    "topics": ["python", "programming"],
                    "locale": "en-US",
                    "audience_segments": ["developers"]
                },
                "typical_top_k": 3
            },
            "sidebar": {
                "description": "Sidebar placement in article or feed",
                "example_context": "Article on machine learning in finance...",
                "recommended_constraints": {
                    "verticals": ["finance", "technology"],
                    "audience_segments": ["data-scientists", "ml-engineers"]
                },
                "typical_top_k": 1
            },
            "banner": {
                "description": "Banner placement (hero, footer, etc)",
                "example_context": "General technology blog page",
                "recommended_constraints": {
                    "locale": "en-US",
                    "topics": ["technology"]
                },
                "typical_top_k": 1
            }
        }, indent=2)
    }


def _get_sample_campaigns() -> list[dict[str, Any]]:
    """Fetch a few sample campaigns from the vector store."""
    try:
        from ..wiring import build_index_service
        service = build_index_service()
        # Return a small representative sample
        info = service.collection_info()
        if info.get("points_count", 0) > 0:
            return [{
                "count": info.get("points_count"),
                "note": f"Total {info.get('points_count')} creatives in collection",
                "hint": "Use campaigns.match with context_text to find relevant creatives"
            }]
        return []
    except Exception:
        return []
