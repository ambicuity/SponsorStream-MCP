"""Domain and MCP request/response models."""

from ..domain.sponsorship import (
    Campaign,
    CampaignBudget,
    CampaignPolicy,
    CampaignSchedule,
    CampaignTargeting,
    Creative,
    CreativeSpec,
)
from .mcp_requests import MatchConstraints, MatchRequest, PlacementContext
from .mcp_responses import CreativeCandidate, MatchResponse

__all__ = [
    # Domain
    "Campaign",
    "CampaignBudget",
    "CampaignPolicy",
    "CampaignSchedule",
    "CampaignTargeting",
    "Creative",
    "CreativeSpec",
    # MCP requests
    "MatchRequest",
    "MatchConstraints",
    "PlacementContext",
    # MCP responses
    "MatchResponse",
    "CreativeCandidate",
]
