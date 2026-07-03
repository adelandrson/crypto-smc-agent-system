"""Order Block detection — deterministic, derived from the swing sequence.

ICT Order Block = the last opposite-coloured candle before the impulse that drove
a structural break. Bullish OB: last bearish (down-close) candle before an up-leg
that broke structure. Bearish OB: last bullish candle before a down-leg.

This is structure -> lives in the swing-fib engine (single source of truth), next
to BOS/CHoCH and swings. The confluence layer treats an OB retest (price back at
a fresh, unmitigated OB aligned with direction) as an A+ booster, exactly like the
existing Fib-golden-pocket x FVG overlap.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from .core import Bar
from .swings import Pivot


def _is_bullish(b: Bar) -> bool:
    return b.close >= b.open


def detect_order_blocks(bars: Sequence[Bar], swings: Sequence[Pivot],
                        lookback: int = 10, max_blocks: int = 4,
                        atr: Optional[Sequence[float]] = None,
                        refine_mult: float = 1.5) -> List[dict]:
    """Find the most recent OB zones from the swing sequence.

    For each confirmed swing leg (O->E), the OB is the last opposite-colour
    candle at or before the origin pivot, within `lookback` bars. A zone is
    [low, high] of that candle (full range) — REFINED to the candle BODY when the
    full range is oversized (> refine_mult x ATR; giant candles otherwise paint a
    zone so wide that later opposite OBs nest inside it, confusing the read).

    Lifecycle: `fresh` (untouched, highest quality) -> `mitigated` (price traded
    back INTO the zone) -> `broken` (a candle CLOSED beyond the far edge: below a
    bull OB / above a bear OB). A broken OB is INVALID as its original type — it
    no longer acts as demand/supply (at best it flips into a breaker for the
    other side), so consumers should drop it.
    """
    out: List[dict] = []
    if len(swings) < 2 or not bars:
        return out
    last_idx = len(bars) - 1
    # walk swing legs from most recent backward
    for k in range(len(swings) - 1, 0, -1):
        if len(out) >= max_blocks:
            break
        origin = swings[k - 1]
        extreme = swings[k]
        direction = "up" if extreme.price > origin.price else "down"
        want_bull = direction == "up"        # up-leg -> look for bearish OB candle
        start = max(0, origin.index - lookback)
        end = origin.index
        ob_bar = None
        for i in range(end, start - 1, -1):
            if i >= len(bars):
                continue
            b = bars[i]
            bull = _is_bullish(b)
            if (want_bull and not bull) or (not want_bull and bull):
                ob_bar = i
                break
        if ob_bar is None:
            continue
        b = bars[ob_bar]
        top, bottom = max(b.high, b.low), min(b.high, b.low)
        # REFINEMENT: giant candle -> zone = body only (keeps the zone actionable)
        a = atr[ob_bar] if atr is not None and 0 <= ob_bar < len(atr) else 0.0
        refined = False
        if a > 0 and (top - bottom) > refine_mult * a:
            body_top, body_bot = max(b.open, b.close), min(b.open, b.close)
            if body_top > body_bot:              # skip pure doji (no body to refine to)
                top, bottom, refined = body_top, body_bot, True
        # lifecycle: mitigated = traded back INTO zone; broken = CLOSED through far edge
        mitigated = False
        broken = False
        for i in range(ob_bar + 1, last_idx + 1):
            bi = bars[i]
            if not mitigated and bi.low <= top and bi.high >= bottom:
                mitigated = True
            if (want_bull and bi.close < bottom) or ((not want_bull) and bi.close > top):
                broken = True
                break
        out.append({
            "type": "bull" if want_bull else "bear",
            "top": round(top, 8),
            "bottom": round(bottom, 8),
            "mid": round((top + bottom) / 2, 8),
            "index": ob_bar,
            "leg_direction": direction,
            "refined": refined,
            "mitigated": mitigated,
            "broken": broken,
            "status": "broken" if broken else ("mitigated" if mitigated else "fresh"),
        })
    return out


def retest(price: float, direction: int, order_blocks: List[dict],
           near_pct: float = 0.5) -> Optional[dict]:
    """Is `price` retesting a fresh OB aligned with `direction`?

    direction +1 (long) -> a fresh bullish OB within near_pct% of price.
    direction -1 (short) -> a fresh bearish OB within near_pct% of price.
    Returns the matched OB or None. Only fresh (unmitigated) OBs qualify — a
    mitigated OB has already done its job and is lower quality.
    """
    if not price or not order_blocks:
        return None
    want = "bull" if direction > 0 else "bear"
    for ob in order_blocks:
        if ob["status"] != "fresh" or ob["type"] != want:
            continue
        dist_pct = abs(price - ob["mid"]) / price * 100.0
        if dist_pct <= near_pct:
            return ob
    return None
