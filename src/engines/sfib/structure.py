"""Market structure from the significant-swing sequence: trend + BOS/CHoCH.

This also fills two gaps the SMC knowledge docs previously left uncomputed:
trend classification and Break of Structure / Change of Character.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .swings import Pivot


def classify(swings: Sequence[Pivot], last_close: float) -> dict:
    highs = [p for p in swings if p.kind == "high"]
    lows = [p for p in swings if p.kind == "low"]
    trend = "range"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        if hh and hl:
            trend = "uptrend"
        elif lh and ll:
            trend = "downtrend"

    last_high = highs[-1].price if highs else None
    last_low = lows[-1].price if lows else None

    event = None          # "BOS" | "CHoCH"
    event_dir = None      # "bullish" | "bearish"
    if last_high is not None and last_close > last_high:
        event_dir = "bullish"
        event = "BOS" if trend == "uptrend" else "CHoCH"
    elif last_low is not None and last_close < last_low:
        event_dir = "bearish"
        event = "BOS" if trend == "downtrend" else "CHoCH"

    return {
        "trend": trend,
        "last_swing_high": last_high,
        "last_swing_low": last_low,
        "event": event,             # most recent break, if any
        "event_direction": event_dir,
        "swing_count": len(swings),
    }
