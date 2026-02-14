"""Tests that the Engine MCP server exposes only the allowed tool set.

No destructive or studio tools may be registered on the Engine.
"""

from sponsorstream.interface.mcp.server import create_server
from sponsorstream.interface.mcp.tools import ENGINE_ALLOWED_TOOLS

# Tools that must NEVER appear on the Data Plane
FORBIDDEN_TOOLS = {
    "collection_ensure",
    "collection_info",
    "collection_migrate",
    "collection_delete",
    "collection_create",
    "campaigns_upsert_batch",
    "creatives_delete",
    "campaigns_bulk_disable",
    "creatives_get",
    "campaigns_report",
    "delete_creative",
    "upsert_creative",
    "create_collection",
    "delete_collection",
}


def _get_tool_names(server) -> set[str]:
    """Extract registered tool names from a FastMCP server."""
    # FastMCP stores tools in _tool_manager._tools dict
    tools = server._tool_manager._tools
    return set(tools.keys())


def test_engine_exposes_only_allowed_tools():
    """Engine must expose exactly the tools in ENGINE_ALLOWED_TOOLS."""
    server = create_server("engine")
    tool_names = _get_tool_names(server)
    assert tool_names == ENGINE_ALLOWED_TOOLS, (
        f"Expected {ENGINE_ALLOWED_TOOLS}, got {tool_names}"
    )


def test_engine_has_no_forbidden_tools():
    """No destructive / studio tool may be registered on the Engine."""
    server = create_server("engine")
    tool_names = _get_tool_names(server)
    overlap = tool_names & FORBIDDEN_TOOLS
    assert not overlap, f"Forbidden tools found on Engine: {overlap}"


def test_studio_has_admin_tools():
    """Studio must have admin tools and NOT campaigns_match."""
    server = create_server("studio")
    tool_names = _get_tool_names(server)
    assert "collection_ensure" in tool_names
    assert "campaigns_upsert_batch" in tool_names
    assert "creatives_delete" in tool_names
    assert "campaigns_match" not in tool_names, "campaigns_match must not be on Studio"
