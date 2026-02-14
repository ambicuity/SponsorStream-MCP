"""Engine entrypoint.

Starts the MCP Engine server (LLM-facing, read-only).
This module deliberately avoids importing any CLI or studio modules
so it can be used as a minimal container entrypoint.

Usage:
    python -m sponsorstream.interface.mcp_engine
    # or via the script entrypoint:
    sponsorstream-engine
"""

from __future__ import annotations

from .mcp.server import create_server


def main() -> None:
    from .mcp.auth import check_scope
    check_scope("engine")
    server = create_server(mode="engine")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
