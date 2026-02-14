"""Control Plane entrypoint.

Starts the MCP Control Plane server (admin-only: provisioning, ingestion).
Use for CI/CD, backoffice, or trusted operators.

Usage:
    python -m sponsorstream_mcp.main_control
    # or:
    sponsorstream-mcp-control
"""

from __future__ import annotations

from .mcp.auth import check_scope
from .mcp.server import create_server
from .config import get_settings


def main() -> None:
    settings = get_settings()
    check_scope("admin")
    server = create_server(mode="admin")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
