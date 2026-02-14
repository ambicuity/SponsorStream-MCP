"""MCP server factory.

Creates either an Engine or Studio server depending on
the requested mode. Each surface registers only its own tool set.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import register_engine_tools, register_studio_tools


_SERVER_NAMES = {
    "engine": "sponsorstream-engine",
    "studio": "sponsorstream-studio",
}


def create_server(mode: str = "engine") -> FastMCP:
    """Build and return a configured FastMCP server.

    Args:
          mode: ``"engine"`` for the Engine (LLM-facing, read-only)
              or ``"studio"`` for the Studio.

    Returns:
        A FastMCP instance with the appropriate tools registered.
    """
    if mode not in _SERVER_NAMES:
        raise ValueError(f"Unknown MCP mode {mode!r}; expected 'engine' or 'studio'")

    server = FastMCP(_SERVER_NAMES[mode])

    if mode == "engine":
        register_engine_tools(server)
        _register_engine_resources(server)
        _register_engine_prompts(server)
    else:
        register_studio_tools(server)

    return server


def _register_engine_resources(server: FastMCP) -> None:
    """Register Engine resources (campaign catalog, schema, templates)."""
    from .resources import (
        get_campaign_catalog_resource,
        get_targeting_schema_resource,
        get_placement_templates_resource,
    )

    @server.resource_list()
    def list_resources() -> list[dict]:
        """List available resources."""
        return [
            {
                "uri": "sponsorstream://catalog/campaigns",
                "name": "Campaign Catalog",
                "description": "Active campaigns and creatives in the collection"
            },
            {
                "uri": "sponsorstream://schema/targeting",
                "name": "Targeting Schema",
                "description": "Valid constraint fields, types, and examples"
            },
            {
                "uri": "sponsorstream://templates/placements",
                "name": "Placement Templates",
                "description": "Example contexts and constraints for different placements"
            }
        ]

    @server.resource("sponsorstream://catalog/campaigns")
    def get_campaign_catalog():
        """Get the campaign catalog resource."""
        from mcp.types import TextResourceContents
        resource = get_campaign_catalog_resource()
        return TextResourceContents(
            uri=resource["uri"],
            mimeType="application/json",
            text=resource["contents"]
        )

    @server.resource("sponsorstream://schema/targeting")
    def get_targeting_schema():
        """Get the targeting schema resource."""
        from mcp.types import TextResourceContents
        resource = get_targeting_schema_resource()
        return TextResourceContents(
            uri=resource["uri"],
            mimeType="application/json",
            text=resource["contents"]
        )

    @server.resource("sponsorstream://templates/placements")
    def get_placement_templates():
        """Get the placement templates resource."""
        from mcp.types import TextResourceContents
        resource = get_placement_templates_resource()
        return TextResourceContents(
            uri=resource["uri"],
            mimeType="application/json",
            text=resource["contents"]
        )


def _register_engine_prompts(server: FastMCP) -> None:
    """Register Engine prompts (agent guidance for matching, explain, analysis)."""
    from .prompts import (
        get_campaign_matching_prompt,
        get_campaign_explain_prompt,
        get_performance_analysis_prompt,
        get_constraint_discovery_prompt,
        get_debug_no_match_prompt,
    )

    @server.prompt_list()
    def list_prompts() -> list[dict]:
        """List available prompts."""
        return [
            {"name": "match-creative-for-chat", "description": "Find relevant creatives for chat placement"},
            {"name": "explain-creative-match", "description": "Explain why a creative was matched"},
            {"name": "analyze-match-performance", "description": "Review matching performance metrics"},
            {"name": "discover-optimal-constraints", "description": "Find best targeting constraints"},
            {"name": "debug-empty-matches", "description": "Troubleshoot why no creatives were returned"},
        ]

    @server.prompt("match-creative-for-chat")
    def get_chat_matching_prompt():
        """Get guidance for matching creatives in chat context."""
        from mcp.types import TextContent
        prompt = get_campaign_matching_prompt()
        return [TextContent(type="text", text=prompt["content"])]

    @server.prompt("explain-creative-match")
    def get_explain_prompt():
        """Get guidance for explaining match decisions."""
        from mcp.types import TextContent
        prompt = get_campaign_explain_prompt()
        return [TextContent(type="text", text=prompt["content"])]

    @server.prompt("analyze-match-performance")
    def get_performance_prompt():
        """Get guidance for performance analysis."""
        from mcp.types import TextContent
        prompt = get_performance_analysis_prompt()
        return [TextContent(type="text", text=prompt["content"])]

    @server.prompt("discover-optimal-constraints")
    def get_discovery_prompt():
        """Get guidance for constraint discovery."""
        from mcp.types import TextContent
        prompt = get_constraint_discovery_prompt()
        return [TextContent(type="text", text=prompt["content"])]

    @server.prompt("debug-empty-matches")
    def get_debug_prompt():
        """Get guidance for debugging empty results."""
        from mcp.types import TextContent
        prompt = get_debug_no_match_prompt()
        return [TextContent(type="text", text=prompt["content"])]


if __name__ == "__main__":
    server = create_server("engine")
    server.run(transport="stdio")

