"""PolicyEngine: non-negotiable post-query filtering."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models.mcp_requests import MatchConstraints, PlacementContext
from ..ports.vector_store import VectorHit

_WHITESPACE_RE = re.compile(r"\s+")


def _tokenize_context(text: str) -> set[str]:
    """Deterministic tokenization: split on whitespace, lowercase."""
    return {t.lower() for t in _WHITESPACE_RE.split(text.strip()) if t}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _schedule_active(payload: dict, now: datetime) -> bool:
    start_at = _parse_iso(payload.get("start_at"))
    end_at = _parse_iso(payload.get("end_at"))
    if start_at and now < start_at:
        return False
    if end_at and now > end_at:
        return False
    return True


class PolicyEngine:
    """Filter vector hits by policy and schedule rules."""

    def apply(
        self,
        hits: list[VectorHit],
        constraints: MatchConstraints,
        placement: PlacementContext,
        context_text: str = "",
    ) -> list[VectorHit]:
        """Return only hits that pass all policy checks."""
        eligible: list[VectorHit] = []
        for hit in hits:
            if self._allowed(hit, constraints, context_text):
                eligible.append(hit)
        return eligible

    def reason(
        self,
        hit: VectorHit,
        constraints: MatchConstraints,
        placement: PlacementContext,
        context_text: str = "",
    ) -> str:
        """Return audit reason for this hit: 'allowed' or 'denied: <reason>'."""
        meta = hit.payload
        if not meta.get("enabled", True):
            return "denied: disabled"
        if meta.get("age_restricted", False) and not constraints.age_restricted_ok:
            return "denied: age_restricted"
        if meta.get("sensitive", False) and not constraints.sensitive_ok:
            return "denied: sensitive"
        if self._blocked_keywords_intersect(hit, context_text):
            return "denied: blocked_keywords"
        now = datetime.now(timezone.utc)
        if not _schedule_active(meta, now):
            return "denied: schedule_inactive"
        return "allowed"

    def _allowed(
        self,
        hit: VectorHit,
        constraints: MatchConstraints,
        context_text: str,
    ) -> bool:
        meta = hit.payload
        if not meta.get("enabled", True):
            return False
        if meta.get("age_restricted", False) and not constraints.age_restricted_ok:
            return False
        if meta.get("sensitive", False) and not constraints.sensitive_ok:
            return False
        if self._blocked_keywords_intersect(hit, context_text):
            return False
        now = datetime.now(timezone.utc)
        if not _schedule_active(meta, now):
            return False
        return True

    def _blocked_keywords_intersect(self, hit: VectorHit, context_text: str) -> bool:
        """True if creative.blocked_keywords intersects context_text tokens."""
        blocked = hit.payload.get("blocked_keywords") or []
        if not blocked:
            return False
        tokens = _tokenize_context(context_text)
        for kw in blocked:
            kw_lower = kw.lower()
            if kw_lower in tokens:
                return True
            if any(kw_lower in t for t in tokens):
                return True
        return False
