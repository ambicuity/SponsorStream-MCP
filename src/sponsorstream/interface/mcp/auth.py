"""MCP auth: roles/scopes (studio vs engine). Gate and reject unauthorized."""

from __future__ import annotations

import os


def require_studio_scope() -> None:
    """Require studio scope for Studio. Raises PermissionError if not allowed."""
    from ..config.runtime import get_settings

    settings = get_settings()
    if not getattr(settings, "require_studio_key", False):
        return
    if not (os.environ.get("MCP_STUDIO_KEY") or os.environ.get("MCP_ADMIN_KEY")):
        raise PermissionError("Studio requires MCP_STUDIO_KEY to be set")


def require_engine_scope() -> None:
    """Require engine scope for Engine. Raises PermissionError if not allowed."""
    from ..config.runtime import get_settings

    settings = get_settings()
    if not getattr(settings, "require_engine_key", False):
        return
    if not (os.environ.get("MCP_ENGINE_KEY") or os.environ.get("MCP_DATA_KEY")):
        raise PermissionError("Engine requires MCP_ENGINE_KEY to be set")


def check_scope(mode: str) -> None:
    """Check scope for the given server mode. Call at server start or per-request."""
    if mode == "studio":
        require_studio_scope()
    elif mode == "engine":
        require_engine_scope()
    else:
        raise ValueError(f"Unknown mode: {mode!r}")
