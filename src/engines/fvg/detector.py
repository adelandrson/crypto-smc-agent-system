"""3-candle Fair Value Gap detection."""

from __future__ import annotations

from typing import List, Sequence

from .types import Bar, Config, Direction, FVG
from .threshold import passes_threshold


def detect_fvgs(
    bars: Sequence[Bar],
    atr: Sequence[float],
    cfg: Config,
    start_id: int = 0,
    source_tf_minutes=None,
) -> List[FVG]:
    """Detect raw (unresolved) FVGs across `bars`.

    A bullish FVG at completion bar `i` requires `low[i] > high[i-2]`, leaving
    an untraded gap between `high[i-2]` (bottom) and `low[i]` (top). A bearish
    FVG requires `high[i] < low[i-2]`, with the gap between `high[i]` (bottom)
    and `low[i-2]` (top). The middle candle `i-1` is the displacement candle.
    """

    out: List[FVG] = []
    next_id = start_id
    n = len(bars)
    for i in range(2, n):
        c0 = bars[i - 2]  # first candle
        c2 = bars[i]      # completion candle
        price = c2.close
        a = atr[i] if i < len(atr) else 0.0

        direction = None
        top = bottom = 0.0
        if c2.low > c0.high:  # bullish imbalance
            direction = Direction.BULLISH
            bottom, top = c0.high, c2.low
        elif c2.high < c0.low:  # bearish imbalance
            direction = Direction.BEARISH
            bottom, top = c2.high, c0.low

        if direction is None:
            continue
        if not passes_threshold(top - bottom, price, a, cfg):
            continue
        if getattr(cfg, "require_displacement", False):
            mid = bars[i - 1]      # candle TENGAH = displacement; wajib impulsif & searah gap
            b1 = abs(c0.close - c0.open)
            bm = abs(mid.close - mid.open)
            b3 = abs(c2.close - c2.open)
            rng = mid.high - mid.low
            imp_min = getattr(cfg, "impulse_atr_min", 0.5)
            if a > 0 and bm < imp_min * a:             # tengah tak cukup impulsif (mutlak vs ATR)
                continue
            if bm < 1.2 * max(b1, b3):                 # tengah tak DOMINAN (c1 & c3 harus lebih pendek)
                continue
            if rng > 0 and bm < 0.5 * rng:             # mayoritas wick, bukan impuls bersih
                continue
            if (direction is Direction.BULLISH and mid.close < mid.open) or \
               (direction is Direction.BEARISH and mid.close > mid.open):   # arah displacement salah
                continue

        out.append(
            FVG(
                id=next_id,
                direction=direction,
                top=top,
                bottom=bottom,
                formed_index=i,
                formed_time=c2.time,
                atr_at_formation=a,
                price_at_formation=price,
                source_tf_minutes=source_tf_minutes,
            )
        )
        next_id += 1
    return out
