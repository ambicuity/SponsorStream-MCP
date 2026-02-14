"""Campaign and creative domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CampaignSchedule(BaseModel):
    """Schedule window for a campaign."""

    start_at: datetime | None = Field(default=None, description="UTC start time for campaign")
    end_at: datetime | None = Field(default=None, description="UTC end time for campaign")

    @field_validator("start_at", "end_at")
    @classmethod
    def _ensure_tz(cls, value: datetime | None) -> datetime | None:
        return _normalize_dt(value)

    def is_active(self, now: datetime | None = None) -> bool:
        """Return True if the schedule is active for the given time."""
        now = _normalize_dt(now or datetime.now(timezone.utc))
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class CampaignBudget(BaseModel):
    """Budget and pacing configuration for a campaign."""

    total_budget: float | None = Field(default=None, ge=0, description="Total budget cap")
    daily_budget: float | None = Field(default=None, ge=0, description="Daily budget cap")
    currency: str = Field(default="USD", description="Budget currency")
    pacing_mode: Literal["even", "accelerated", "adaptive"] = Field(
        default="even", description="Pacing strategy"
    )
    cpm: float = Field(default=10.0, ge=0, description="Estimated cost per 1000 impressions")
    target_ctr: float | None = Field(
        default=None, ge=0, le=1, description="Optional target CTR for adaptive pacing"
    )


class CampaignTargeting(BaseModel):
    """Targeting configuration for a campaign."""

    topics: list[str] = Field(default_factory=list, description="Topics to target")
    locale: list[str] = Field(default_factory=list, description="Locale codes to target (e.g., 'en-US')")
    verticals: list[str] = Field(default_factory=list, description="Industry verticals to target")
    blocked_keywords: list[str] = Field(default_factory=list, description="Keywords to exclude from targeting")
    audience_segments: list[str] = Field(default_factory=list, description="Audience segments to target")
    keywords: list[str] = Field(default_factory=list, description="Context keywords to target")


class CampaignPolicy(BaseModel):
    """Policy flags for a campaign."""

    sensitive: bool = Field(default=False, description="Whether the campaign contains sensitive content")
    age_restricted: bool = Field(default=False, description="Whether the campaign is age-restricted")
    brand_safety_tier: Literal["low", "medium", "high"] = Field(
        default="medium", description="Brand safety tier"
    )


class CreativeSpec(BaseModel):
    """Creative unit within a campaign definition."""

    creative_id: str = Field(..., description="Unique creative identifier")
    title: str = Field(..., description="Creative headline")
    body: str = Field(..., description="Creative body text")
    cta_text: str = Field(..., description="Call-to-action text")
    landing_url: str = Field(..., description="Click-through URL")


class Creative(BaseModel):
    """Renderable creative with campaign metadata attached."""

    creative_id: str = Field(..., description="Unique creative identifier")
    campaign_id: str = Field(..., description="Campaign identifier")
    advertiser_id: str = Field(..., description="Advertiser identifier")
    campaign_name: str = Field(..., description="Campaign name")
    title: str = Field(..., description="Creative headline")
    body: str = Field(..., description="Creative body text")
    cta_text: str = Field(..., description="Call-to-action text")
    landing_url: str = Field(..., description="Click-through URL")
    targeting: CampaignTargeting = Field(default_factory=CampaignTargeting, description="Targeting configuration")
    policy: CampaignPolicy = Field(default_factory=CampaignPolicy, description="Policy configuration")
    schedule: CampaignSchedule = Field(default_factory=CampaignSchedule, description="Schedule window")
    budget: CampaignBudget = Field(default_factory=CampaignBudget, description="Budget and pacing")
    enabled: bool = Field(default=True, description="Whether creative is eligible for matching")

    @property
    def embedding_text(self) -> str:
        """Generate text for embeddings (title + body + topics + keywords)."""
        topics_text = " ".join(self.targeting.topics)
        keywords_text = " ".join(self.targeting.keywords)
        return f"{self.title} {self.body} {topics_text} {keywords_text}".strip()

    def to_vector_payload(self) -> dict:
        """Convert to flat payload for vector storage."""
        return {
            "creative_id": self.creative_id,
            "campaign_id": self.campaign_id,
            "advertiser_id": self.advertiser_id,
            "campaign_name": self.campaign_name,
            "title": self.title,
            "body": self.body,
            "cta_text": self.cta_text,
            "landing_url": self.landing_url,
            "topics": self.targeting.topics,
            "locale": self.targeting.locale,
            "verticals": self.targeting.verticals,
            "blocked_keywords": self.targeting.blocked_keywords,
            "audience_segments": self.targeting.audience_segments,
            "keywords": self.targeting.keywords,
            "sensitive": self.policy.sensitive,
            "age_restricted": self.policy.age_restricted,
            "brand_safety_tier": self.policy.brand_safety_tier,
            "start_at": self.schedule.start_at.isoformat() if self.schedule.start_at else None,
            "end_at": self.schedule.end_at.isoformat() if self.schedule.end_at else None,
            "total_budget": self.budget.total_budget,
            "daily_budget": self.budget.daily_budget,
            "currency": self.budget.currency,
            "pacing_mode": self.budget.pacing_mode,
            "cpm": self.budget.cpm,
            "target_ctr": self.budget.target_ctr,
            "enabled": self.enabled,
        }


class Campaign(BaseModel):
    """Campaign definition with creatives and shared metadata."""

    campaign_id: str = Field(..., description="Campaign identifier")
    advertiser_id: str = Field(..., description="Advertiser identifier")
    name: str = Field(..., description="Campaign name")
    creatives: list[CreativeSpec] = Field(default_factory=list, description="Creative list")
    targeting: CampaignTargeting = Field(default_factory=CampaignTargeting, description="Targeting configuration")
    policy: CampaignPolicy = Field(default_factory=CampaignPolicy, description="Policy configuration")
    schedule: CampaignSchedule = Field(default_factory=CampaignSchedule, description="Schedule window")
    budget: CampaignBudget = Field(default_factory=CampaignBudget, description="Budget and pacing")

    def to_creatives(self) -> list[Creative]:
        """Expand campaign into creative instances with inherited metadata."""
        creatives: list[Creative] = []
        for creative in self.creatives:
            creatives.append(
                Creative(
                    creative_id=creative.creative_id,
                    campaign_id=self.campaign_id,
                    advertiser_id=self.advertiser_id,
                    campaign_name=self.name,
                    title=creative.title,
                    body=creative.body,
                    cta_text=creative.cta_text,
                    landing_url=creative.landing_url,
                    targeting=self.targeting,
                    policy=self.policy,
                    schedule=self.schedule,
                    budget=self.budget,
                )
            )
        return creatives
