"""Studio entrypoint.

Starts the MCP Studio server (admin-only: provisioning, ingestion).
Use for CI/CD, backoffice, or trusted operators.

Usage:
    python -m sponsorstream.interface.mcp_studio
    # or:
    sponsorstream-studio
"""

from __future__ import annotations

from .mcp.auth import check_scope
from .mcp.server import create_server
from .config import get_settings


def main() -> None:
    settings = get_settings()
    check_scope("studio")
    server = create_server(mode="studio")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
