"""MCP Prompts for SponsorStream agent guidance.

Pre-built prompt templates to guide agents on matching and analysis tasks.
"""

from __future__ import annotations

from typing import Any


def get_campaign_matching_prompt() -> dict[str, Any]:
    """Prompt for matching creatives in chat context."""
    return {
        "name": "match-creative-for-chat",
        "description": "Find and render relevant creatives for inline chat placement",
        "arguments": [
            {
                "name": "context_text",
                "description": "The conversational context (what the user is asking about)"
            },
            {
                "name": "target_audience",
                "description": "Optional: describe the target audience (e.g., 'Python developers')"
            }
        ],
        "content": """You are helping match advertising creatives to conversational context.

Given the conversation or search query, use campaigns.match to find relevant sponsorships:

1. Analyze the context_text: What are the key topics, intent, or domains?
2. Extract or infer audience segments, topics, and locales
3. Call campaigns.match with:
   - context_text: the conversation snippet
   - placement: "inline" (for chat context)
   - surface: "chat"
   - top_k: 3-5 candidates
   - constraints: topics, locale, verticals, audience_segments (if known)
4. Present the top match with title, cta_text, and landing_url
5. If no good match, call campaigns_suggest_constraints to find missing targeting info

Example:
User asks: "How do I optimize Python async code?"
→ Use topics: ["python", "async-programming"], audience_segments: ["developers"]
→ Match inline creatives about Python education/tools
→ Present best match with "Learn Python Async" CTA
"""
    }


def get_campaign_explain_prompt() -> dict[str, Any]:
    """Prompt for explaining match decisions."""
    return {
        "name": "explain-creative-match",
        "description": "Deep dive into why a creative was matched or rejected",
        "arguments": [
            {
                "name": "match_id",
                "description": "The opaque match_id from a prior campaigns.match response"
            }
        ],
        "content": """You are explaining advertising match decisions to developers.

When a user asks "Why did you pick this creative?" or "Why wasn't X matched?":

1. Call campaigns.explain(match_id) to retrieve the audit trace
2. Explain to the user:
   - What the context_text was
   - Which constraints were applied
   - How each creative scored (similar vs not similar)
   - If a creative was rejected: which policy or constraint caused rejection
   - Pacing decisions (budget constraints, delivery schedules)
3. Suggest improvements:
   - "Relax sensitive_ok=true to see more creatives"
   - "Add audience_segments=['developers'] for better matches"
   - "Try locale='en-GB' for UK audience"

Example output:
"Your context 'machine learning' matched 3 creatives:
1. 'Learn ML with TensorFlow' (score: 0.89) - inline-friendly, active schedule
2. 'AI fundamentals' (score: 0.82) - matches topic, less budget today
3. 'Python ML course' (score: 0.76) - high match, competing for budget

The creative 'Blockchain guide' scored 0.15 (rejected) because your context doesn't mention blockchain or cryptography."
"""
    }


def get_performance_analysis_prompt() -> dict[str, Any]:
    """Prompt for analyzing matching performance over time."""
    return {
        "name": "analyze-match-performance",
        "description": "Review matching success rates, constraint impact, and budget pacing",
        "arguments": [
            {
                "name": "timeframe_hours",
                "description": "Look back N hours (default 24)"
            },
            {
                "name": "campaign_id",
                "description": "Optional: focus on a specific campaign"
            }
        ],
        "content": """You are analyzing advertising matching performance metrics.

When asked for performance insights:

1. Call campaigns_metrics(since_hours=...) to get:
   - Match success rate (% of requests returning candidates)
   - Average match score distribution
   - Which constraints are most restrictive
   - Constraint rejection rates
2. Identify bottlenecks:
   - "80% of requests matched, but avg score is 0.6 (low confidence)"
   - "audience_segments constraint rejects 40% of otherwise good matches"
   - "Budget pacing is hard-blocking 15% of eligible creatives"
3. Make recommendations:
   - "Expand audience_segments or make it optional"
   - "Consider increasing daily budget for campaign X"
   - "Review blocked_keywords (they're rejecting 5% of otherwise relevant creatives)"

Example output:
"Performance snapshot (last 24h):
- Match rate: 92% of requests returned ≥1 creative
- Avg match score: 0.78 (good semantic fit)
- Top rejection reason: 'age_restricted=false' (30% of rejections)
- Pacing impact: 5% of eligible creatives blocked by budget caps
- Recommendation: Consider age-restricted campaigns for adult audience or relax age_restricted_ok"
"""
    }


def get_constraint_discovery_prompt() -> dict[str, Any]:
    """Prompt for discovering optimal constraints for a context."""
    return {
        "name": "discover-optimal-constraints",
        "description": "Find the best targeting constraints for a given context and audience",
        "arguments": [
            {
                "name": "context_text",
                "description": "The content or conversation to target"
            },
            {
                "name": "initial_constraints",
                "description": "Optional: starting constraints to refine"
            }
        ],
        "content": """You are helping optimize targeting for better creative matches.

When asked "What constraints should I use for X?" or "Why aren't we matching X?":

1. Analyze the context_text contextually
2. Call campaigns_suggest_constraints(context_text) to get AI-powered recommendations:
   - Suggested topics
   - Suggested audience_segments
   - Suggested locales
   - Suggested verticals
3. Present the suggestions with confidence scores or reasoning
4. Offer variations to test:
   - Conservative: narrow constraints, high precision (fewer matches, higher quality)
   - Balanced: moderate constraints, good match rate
   - Liberal: loose constraints, high recall (more matches, lower avg quality)

Example:
Context: "How to get started with Kubernetes"
Suggestions:
- topics: [kubernetes, containerization, devops] (high confidence)
- audience_segments: [developers, devops-engineers, sre] (medium-high)
- verticals: [technology] (high)
- locale: infer from user (default: en-US)

Conservative matching:
campaigns.match(context, topics=['kubernetes','devops'], audience_segments=['devops-engineers'])
→ Likely 1-2 highly relevant creatives

Liberal matching:
campaigns.match(context, topics=['kubernetes'], locale='en-US')
→ Likely 5-10 matches including education, tools, cloud platforms
"""
    }


def get_debug_no_match_prompt() -> dict[str, Any]:
    """Prompt for debugging cases where matching fails."""
    return {
        "name": "debug-empty-matches",
        "description": "Troubleshoot why a valid context returned no creatives",
        "arguments": [
            {
                "name": "context_text",
                "description": "The context that returned no matches"
            },
            {
                "name": "constraints_used",
                "description": "The constraints that were applied"
            }
        ],
        "content": """You are debugging empty match results.

When campaigns.match returns 0 candidates despite valid context:

1. Validate the context:
   - Is context_text meaningful (not too short, not noise)?
   - Language match: context in English but collection is in another language?
2. Check constraints:
   - Are exclude_* lists too broad? (e.g., exclude all advertisers except 1)
   - Is locale too strictly constrained?
   - Are audience_segments too narrow?
3. Call campaigns_diagnostics() to investigate:
   - "No active campaigns match your locale+vertical combo"
   - "All matching creatives are budget-constrained (pacing=0)"
   - "All matching creatives are outside their schedule window"
   - "Embedding model found no semantic matches (confidence < threshold)"
4. Suggestions:
   - Relax constraints: remove locale, broaden audience_segments, etc.
   - Check campaign schedules are active
   - Review if context is too niche (not covered by ad inventory)
   - Try campaigns_match_sample() to see what's in the collection

Troubleshooting flow:
No matches
→ Check context length (should be >20 tokens)
→ Relax locale/audience constraints one at a time
→ Call campaigns_diagnostics() to see collection health
→ Try broader topics/keywords
→ If still empty: collection may not have relevant campaigns
"""
    }
