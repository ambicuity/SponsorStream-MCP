"""Request validation and safety for MCP tools.

Provides comprehensive validation, soft limits, and helpful feedback for match requests.
"""

from __future__ import annotations

from typing import Any
from sponsorstream.models.mcp_requests import MatchRequest, MatchConstraints


class ValidationResult:
    """Result of request validation."""
    
    def __init__(self, is_valid: bool, errors: list[str] | None = None, warnings: list[str] | None = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON response."""
        return {
            "valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }
    
    def add_error(self, error: str) -> ValidationResult:
        """Add an error and return self for chaining."""
        self.errors.append(error)
        self.is_valid = False
        return self
    
    def add_warning(self, warning: str) -> ValidationResult:
        """Add a warning and return self for chaining."""
        self.warnings.append(warning)
        return self


def validate_match_request(request: MatchRequest) -> ValidationResult:
    """Validate a MatchRequest for safety and correctness.
    
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(is_valid=True)
    
    # Validate context_text
    if not request.context_text or not request.context_text.strip():
        result.add_error("context_text cannot be empty")
    elif len(request.context_text.strip()) < 5:
        result.add_warning("context_text very short (< 5 chars); semantic matching may be unreliable")
    elif len(request.context_text) > 10_000:
        result.add_error(f"context_text too long ({len(request.context_text)} chars; max 10000)")
    
    # Check for mostly whitespace or non-ASCII
    content = request.context_text.strip()
    if len(content) < 10:
        result.add_warning("context_text appears too short for semantic matching")
    
    # Validate numeric ranges
    if request.top_k < 1:
        result.add_error(f"top_k must be >= 1 (got {request.top_k})")
    elif request.top_k > 100:
        result.add_error(f"top_k must be <= 100 (got {request.top_k})")
    
    # Validate placement
    valid_placements = {"inline", "sidebar", "banner"}
    if request.placement.placement not in valid_placements:
        result.add_warning(f"placement '{request.placement.placement}' not standard; expected one of {valid_placements}")
    
    # Validate constraints
    _validate_constraints(request.constraints, result)
    
    # Validate boost_keywords
    if request.boost_keywords:
        for keyword, factor in request.boost_keywords.items():
            if not isinstance(keyword, str) or not keyword.strip():
                result.add_error(f"boost_keywords key must be non-empty string, got: {keyword!r}")
            if not isinstance(factor, (int, float)):
                result.add_error(f"boost_keywords['{keyword}'] must be numeric, got: {type(factor).__name__}")
            elif factor < 0.1 or factor > 2.0:
                result.add_warning(f"boost_keywords['{keyword}'] = {factor} will be clamped to [0.1, 2.0]")
    
    return result


def _validate_constraints(constraints: MatchConstraints, result: ValidationResult) -> None:
    """Validate constraint fields."""
    
    # Validate list constraints
    list_constraints = {
        "topics": constraints.topics,
        "verticals": constraints.verticals,
        "audience_segments": constraints.audience_segments,
        "keywords": constraints.keywords,
        "exclude_advertiser_ids": constraints.exclude_advertiser_ids,
        "exclude_campaign_ids": constraints.exclude_campaign_ids,
        "exclude_creative_ids": constraints.exclude_creative_ids,
    }
    
    for name, value in list_constraints.items():
        if value is not None:
            if not isinstance(value, list):
                result.add_error(f"constraints.{name} must be list, got {type(value).__name__}")
            elif len(value) > 100:
                result.add_warning(f"constraints.{name} has {len(value)} items; may be overly restrictive")
            elif len(value) == 0:
                result.add_warning(f"constraints.{name} is empty list; removing this constraint")
            else:
                # Check for empty strings
                for item in value:
                    if not isinstance(item, str) or not item.strip():
                        result.add_error(f"constraints.{name} contains empty string")
    
    # Validate locale format (simple check)
    if constraints.locale is not None:
        if not isinstance(constraints.locale, str):
            result.add_error(f"constraints.locale must be string, got {type(constraints.locale).__name__}")
        elif not constraints.locale.strip():
            result.add_error("constraints.locale cannot be empty string")
        elif len(constraints.locale) > 10:
            result.add_warning(f"constraints.locale value '{constraints.locale}' looks unusual (too long)")
    
    # Validate boolean constraints
    if not isinstance(constraints.age_restricted_ok, bool):
        result.add_error(f"constraints.age_restricted_ok must be bool, got {type(constraints.age_restricted_ok).__name__}")
    if not isinstance(constraints.sensitive_ok, bool):
        result.add_error(f"constraints.sensitive_ok must be bool, got {type(constraints.sensitive_ok).__name__}")
    
    # Warn if all exclusion filters are set
    has_exclusions = (
        constraints.exclude_advertiser_ids or
        constraints.exclude_campaign_ids or
        constraints.exclude_creative_ids
    )
    if has_exclusions and (
        constraints.topics is None and
        constraints.verticals is None and
        constraints.audience_segments is None
    ):
        result.add_warning("Using only exclusion filters without positive constraints; may result in no matches")


def estimate_match_difficulty(request: MatchRequest) -> dict[str, Any]:
    """Estimate how difficult a match request is (heuristic scoring).
    
    Returns:
        Dict with difficulty_score (0–10), factors, and recommendations
    """
    score = 0.0
    factors = []
    recommendations = []
    
    # Context quality (0–3 points)
    context_len = len(request.context_text.strip())
    if context_len < 20:
        score += 2.5
        factors.append("Short context (< 20 chars) reduces semantic confidence")
        recommendations.append("Provide more context (30+ chars) for better matches")
    elif context_len < 50:
        score += 1.5
        factors.append("Moderate context length")
    else:
        factors.append("Good context length")
    
    # Constraint specificity (0–4 points)
    constraint_count = sum(1 for v in [
        request.constraints.topics,
        request.constraints.verticals,
        request.constraints.audience_segments,
        request.constraints.locale,
    ] if v)
    
    if constraint_count == 0:
        score += 0.5
        factors.append("No constraints specified (very broad)")
        recommendations.append("Add topics/verticals/audience_segments for better precision")
    elif constraint_count == 1:
        score += 1.0
        factors.append("Single constraint (good balance)")
    elif constraint_count >= 3:
        score += 2.0
        factors.append("Multiple constraints (may reduce match rate)")
        recommendations.append("Consider relaxing 1–2 constraints if match rate is low")
    
    # Exclusions strict ness (0–2 points)
    exclusion_count = sum(1 for v in [
        request.constraints.exclude_advertiser_ids,
        request.constraints.exclude_campaign_ids,
        request.constraints.exclude_creative_ids,
    ] if v and len(v) > 0)
    
    if exclusion_count > 0:
        score += min(2.0, exclusion_count)
        factors.append(f"Excluding {exclusion_count} categories of creatives")
    
    # Policy restrictions (0–2 points)
    if not request.constraints.age_restricted_ok:
        score += 0.5
        factors.append("Age-restricted campaigns excluded")
    if not request.constraints.sensitive_ok:
        score += 0.5
        factors.append("Sensitive campaigns excluded")
    
    # Boost keywords specificity (0–1 point)
    if request.boost_keywords and len(request.boost_keywords) > 5:
        score += 0.5
        factors.append("Many boost keywords may reduce signal")
    
    # Top_k high (0–1 point)
    if request.top_k > 20:
        score += 0.5
        factors.append("High top_k may include low-confidence matches")
        recommendations.append("Consider reducing top_k for higher quality matches")
    
    difficulty = min(10.0, score)
    difficulty_label = "easy" if difficulty < 3 else "moderate" if difficulty < 6 else "hard"
    
    if not recommendations:
        recommendations.append("Request looks reasonable; no specific recommendations")
    
    return {
        "difficulty_score": round(difficulty, 1),
        "difficulty_label": difficulty_label,
        "factors": factors,
        "recommendations": recommendations,
    }


def validate_and_estimate(request: MatchRequest) -> dict[str, Any]:
    """Run validation and estimate difficulty in one call.
    
    Returns:
        Dict with validation result and difficulty estimate
    """
    validation = validate_match_request(request)
    difficulty = estimate_match_difficulty(request)
    
    return {
        "validation": validation.to_dict(),
        "difficulty": difficulty,
        "summary": {
            "valid": validation.is_valid,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
            "difficulty_score": difficulty["difficulty_score"],
        }
    }
