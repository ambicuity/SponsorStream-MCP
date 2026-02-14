"""Match semantics for campaign targeting and policy."""

# Rule names for reference in tests and audit
RULE_TOPICS_INTERSECT = "topics: creative.topics intersects request.topics (ANY)"
RULE_VERTICALS_INTERSECT = "verticals: creative.verticals intersects request.verticals (ANY)"
RULE_LOCALE_EXACT_OR_GLOBAL = "locale: exact match or empty/'' as global"
RULE_EXCLUSIONS_ALWAYS = "exclusions: exclude_creative_ids, exclude_campaign_ids, exclude_advertiser_ids always enforced"
RULE_PLACEMENT_ANNOTATE_ONLY = "placement: annotate only, no filter"
RULE_AUDIENCE_SEGMENTS_ANY = "audience_segments: creative.audience_segments intersects request.audience_segments (ANY)"
RULE_KEYWORDS_ANY = "keywords: creative.keywords intersects request.keywords (ANY)"
RULE_SCHEDULE_ACTIVE = "schedule: creative is active within start/end window"
