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
    else:
        register_studio_tools(server)

    return server


if __name__ == "__main__":
    server = create_server("engine")
    server.run(transport="stdio")
