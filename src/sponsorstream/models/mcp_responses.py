"""MCP response DTOs for the Engine match tool."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreativeCandidate(BaseModel):
    """A single creative candidate returned by campaigns.match."""

    creative_id: str = Field(..., description="Unique creative identifier")
    campaign_id: str = Field(..., description="Campaign identifier")
    advertiser_id: str = Field(..., description="Advertiser identifier")
    campaign_name: str = Field(..., description="Campaign name")
    title: str = Field(..., description="Creative headline")
    body: str = Field(..., description="Creative body text")
    cta_text: str = Field(..., description="Call-to-action text")
    landing_url: str = Field(..., description="Click-through URL")
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score (0-1)")
    match_id: str = Field(..., description="Opaque ID for campaigns.explain lookups")
    pacing_weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Pacing weight applied")
    pacing_reason: str = Field(default="", description="Reason for pacing decision")


class MatchResponse(BaseModel):
    """Output DTO for the campaigns.match tool."""

    candidates: list[CreativeCandidate] = Field(
        default_factory=list,
        description="Ranked creative candidates",
    )
    request_id: str = Field(..., description="Trace ID for this request")
    placement: str = Field(..., description="Placement slot that was requested")
