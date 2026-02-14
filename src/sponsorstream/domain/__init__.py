"""Domain layer for SponsorStream."""

from .filters import FieldFilter, FilterOp, VectorFilter
from .match_semantics import (
    RULE_AUDIENCE_SEGMENTS_ANY,
    RULE_EXCLUSIONS_ALWAYS,
    RULE_KEYWORDS_ANY,
    RULE_LOCALE_EXACT_OR_GLOBAL,
    RULE_PLACEMENT_ANNOTATE_ONLY,
    RULE_SCHEDULE_ACTIVE,
    RULE_TOPICS_INTERSECT,
    RULE_VERTICALS_INTERSECT,
)
from .policy_engine import PolicyEngine
from .sponsorship import (
    Campaign,
    CampaignBudget,
    CampaignPolicy,
    CampaignSchedule,
    CampaignTargeting,
    Creative,
    CreativeSpec,
)
from .targeting_engine import TargetingEngine

__all__ = [
    "Campaign",
    "CampaignBudget",
    "CampaignPolicy",
    "CampaignSchedule",
    "CampaignTargeting",
    "Creative",
    "CreativeSpec",
    "FieldFilter",
    "FilterOp",
    "PolicyEngine",
    "TargetingEngine",
    "VectorFilter",
    "RULE_AUDIENCE_SEGMENTS_ANY",
    "RULE_EXCLUSIONS_ALWAYS",
    "RULE_KEYWORDS_ANY",
    "RULE_LOCALE_EXACT_OR_GLOBAL",
    "RULE_PLACEMENT_ANNOTATE_ONLY",
    "RULE_SCHEDULE_ACTIVE",
    "RULE_TOPICS_INTERSECT",
    "RULE_VERTICALS_INTERSECT",
]
