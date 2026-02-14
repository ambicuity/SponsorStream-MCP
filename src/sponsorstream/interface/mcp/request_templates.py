"""Request templates for common matching scenarios.

Pre-built MatchRequest templates to help agents quickly construct
properly-formed requests for different use cases.
"""

from __future__ import annotations

from sponsorstream.models.mcp_requests import MatchRequest, MatchConstraints, PlacementContext


def template_inline_chat(
    context_text: str,
    locale: str = "en-US",
    topics: list[str] | None = None,
    audience_segments: list[str] | None = None,
    top_k: int = 3,
) -> MatchRequest:
    """Template for inline chat placement (conversational context).
    
    Optimized for matching creatives within chat messages.
    
    Args:
        context_text: The conversation snippet or question
        locale: Locale to target (default: en-US)
        topics: Optional topic restrictions
        audience_segments: Optional audience segments
        top_k: Number of candidates (default: 3)
        
    Returns:
        Configured MatchRequest for inline chat
    """
    return MatchRequest(
        context_text=context_text,
        top_k=top_k,
        placement=PlacementContext(placement="inline", surface="chat"),
        constraints=MatchConstraints(
            locale=locale,
            topics=topics,
            audience_segments=audience_segments,
            age_restricted_ok=False,
            sensitive_ok=False,
        ),
    )


def template_sidebar_article(
    context_text: str,
    verticals: list[str] | None = None,
    audience_segments: list[str] | None = None,
    topics: list[str] | None = None,
    top_k: int = 1,
) -> MatchRequest:
    """Template for sidebar placement in articles.
    
    Optimized for matching creatives alongside article content.
    
    Args:
        context_text: Article headline, summary, or category
        verticals: Industry verticals to target
        audience_segments: Optional audience segments
        topics: Optional topic restrictions
        top_k: Number of candidates (default: 1)
        
    Returns:
        Configured MatchRequest for sidebar
    """
    return MatchRequest(
        context_text=context_text,
        top_k=top_k,
        placement=PlacementContext(placement="sidebar", surface="feed"),
        constraints=MatchConstraints(
            verticals=verticals,
            audience_segments=audience_segments,
            topics=topics,
            locale="en-US",
            age_restricted_ok=False,
            sensitive_ok=False,
        ),
    )


def template_banner_homepage(
    context_text: str = "homepage",
    locale: str = "en-US",
    verticals: list[str] | None = None,
    top_k: int = 1,
) -> MatchRequest:
    """Template for banner placement on homepage (broad audience).
    
    Optimized for main page banners with minimal targeting.
    
    Args:
        context_text: Page context (default: "homepage")
        locale: Locale to target (default: en-US)
        verticals: Optional vertical targeting
        top_k: Number of candidates (default: 1)
        
    Returns:
        Configured MatchRequest for banner
    """
    return MatchRequest(
        context_text=context_text,
        top_k=top_k,
        placement=PlacementContext(placement="banner", surface="feed"),
        constraints=MatchConstraints(
            locale=locale,
            verticals=verticals,
            age_restricted_ok=False,
            sensitive_ok=False,
        ),
    )


def template_search_results(
    query: str,
    topics: list[str] | None = None,
    audience_segments: list[str] | None = None,
    locale: str = "en-US",
    top_k: int = 2,
) -> MatchRequest:
    """Template for search results page (query-based matching).
    
    Optimized for matching creatives alongside search query results.
    
    Args:
        query: User search query
        topics: Optional topic restrictions
        audience_segments: Optional audience segments
        locale: Locale to target (default: en-US)
        top_k: Number of candidates (default: 2)
        
    Returns:
        Configured MatchRequest for search
    """
    return MatchRequest(
        context_text=query,
        top_k=top_k,
        placement=PlacementContext(placement="inline", surface="search"),
        constraints=MatchConstraints(
            topics=topics,
            audience_segments=audience_segments,
            locale=locale,
            age_restricted_ok=False,
            sensitive_ok=False,
        ),
    )


def template_testing(
    context_text: str,
    sensitive_ok: bool = True,
    age_restricted_ok: bool = True,
) -> MatchRequest:
    """Template for testing (relaxed constraints).
    
    Useful for debugging and testing without restrictive filtering.
    
    Args:
        context_text: Test context
        sensitive_ok: Allow sensitive content (default: True)
        age_restricted_ok: Allow age-restricted content (default: True)
        
    Returns:
        Configured MatchRequest with relaxed constraints
    """
    return MatchRequest(
        context_text=context_text,
        top_k=10,
        placement=PlacementContext(placement="inline", surface="chat"),
        constraints=MatchConstraints(
            sensitive_ok=sensitive_ok,
            age_restricted_ok=age_restricted_ok,
        ),
    )


# Template registry for easy lookup
TEMPLATES = {
    "inline_chat": template_inline_chat,
    "sidebar_article": template_sidebar_article,
    "banner_homepage": template_banner_homepage,
    "search_results": template_search_results,
    "testing": template_testing,
}


def get_template(template_name: str) -> callable | None:
    """Get a template function by name.
    
    Args:
        template_name: Name of the template (e.g., 'inline_chat')
        
    Returns:
        Template function or None if not found
    """
    return TEMPLATES.get(template_name)


def list_templates() -> dict[str, str]:
    """Get list of all available templates with descriptions.
    
    Returns:
        Dict mapping template names to descriptions
    """
    descriptions = {
        "inline_chat": "For conversational context in chat (3 candidates)",
        "sidebar_article": "For sidebar placement in articles (1 candidate)",
        "banner_homepage": "For banner on homepage (1 candidate, broad audience)",
        "search_results": "For search results page (2 candidates)",
        "testing": "For testing with relaxed constraints (10 candidates)",
    }
    return descriptions
