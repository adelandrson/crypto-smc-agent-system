"""Trading session filter (London/NY/Asia) — code-enforced SKILL A5 SKIP.

Replaces the manual "session aktif" narrative in lux-algo-guide.md / SKILL.md
with a deterministic UTC-hour check. Scalping (Mode A) should skip outside the
liquid London/NY overlap; swing (Mode B) is session-agnostic.

  London    : 07:00-12:00 UTC
  NY        : 13:00-17:00 UTC
  overlap   : 13:00-16:00 UTC  (best liquidity)
  Asia      : 00:00-07:00 UTC  (thinner; scalp caveat)
  off       : else
"""
from __future__ import annotations

from datetime import datetime, timezone


def session_at(dt: datetime) -> str:
    h = dt.astimezone(timezone.utc).hour
    if 7 <= h < 12:
        return "london"
    if 13 <= h < 17:
        return "ny"
    if 0 <= h < 7:
        return "asia"
    return "off"


def is_scalp_session(dt: datetime, allow_asia: bool = False) -> bool:
    s = session_at(dt)
    if s in ("london", "ny"):
        return True
    return allow_asia and s == "asia"


def session_ok(dt: datetime, mode: str = "swing", allow_asia: bool = False) -> bool:
    """Swing = always ok (multi-day). Scalp = only liquid sessions."""
    if mode == "scalp":
        return is_scalp_session(dt, allow_asia)
    return True
