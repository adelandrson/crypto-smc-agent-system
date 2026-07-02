"""RSI divergence detection (regular & hidden).

Reuses a LOCAL fractal pivot on price highs/lows (smaller depth than the
swing-fib structural pivots) so this module is self-contained and does not
collide with the swing-fib engine's structural swing detection.

  Regular bull divergence : price lower-low  + RSI higher-low  -> reversal up   (+1)
  Regular bear divergence : price higher-high + RSI lower-high  -> reversal down (-1)
  Hidden  bull divergence : price higher-low  + RSI lower-low   -> continuation up  (+1)
  Hidden  bear divergence : price lower-high  + RSI higher-high -> continuation down (-1)
"""
from __future__ import annotations

from typing import List, Sequence


def _price_pivots(highs, lows, depth: int = 5) -> list:
    """Local fractal pivots: (index, price, kind). Smaller depth than structural
    swings so divergence catches momentum turns at a finer grain."""
    n = len(highs)
    out = []
    for i in range(depth, n - depth):
        is_high = all(highs[i] > highs[j] for j in range(i - depth, i)) and \
            all(highs[i] > highs[j] for j in range(i + 1, i + depth + 1))
        is_low = all(lows[i] < lows[j] for j in range(i - depth, i)) and \
            all(lows[i] < lows[j] for j in range(i + 1, i + depth + 1))
        if is_high:
            out.append((i, highs[i], "high"))
        if is_low:
            out.append((i, lows[i], "low"))
    out.sort(key=lambda p: p[0])
    # collapse same-kind consecutive -> keep most extreme
    collapsed = []
    for p in out:
        if collapsed and collapsed[-1][2] == p[2]:
            if (p[2] == "high" and p[1] > collapsed[-1][1]) or \
               (p[2] == "low" and p[1] < collapsed[-1][1]):
                collapsed[-1] = p
        else:
            collapsed.append(p)
    return collapsed


def detect(rsi_series: Sequence[float], highs, lows, depth: int = 5) -> dict:
    """Return the most recent divergence signal.

    {kind: "regular_bull"|"regular_bear"|"hidden_bull"|"hidden_bear"|None,
     momentum_score: +1|-1|0, pivot_indices: (i_prev, i_now)}"""
    pivots = _price_pivots(highs, lows, depth)
    highs_p = [p for p in pivots if p[2] == "high"]
    lows_p = [p for p in pivots if p[2] == "low"]

    best = None  # (score, kind, detail)
    # regular/hidden bear from two most-recent highs
    if len(highs_p) >= 2:
        (i0, p0, _), (i1, p1, _) = highs_p[-2], highs_p[-1]
        r0, r1 = rsi_series[i0], rsi_series[i1]
        if p1 > p0 and r1 < r0:                       # higher-high, lower RSI
            best = (-1, "regular_bear", (i0, i1))
        elif p1 < p0 and r1 > r0:                      # lower-high, higher RSI
            best = (-1, "hidden_bear", (i0, i1))
    # regular/hidden bull from two most-recent lows (overrides bear only if newer)
    if len(lows_p) >= 2:
        (i0, p0, _), (i1, p1, _) = lows_p[-2], lows_p[-1]
        r0, r1 = rsi_series[i0], rsi_series[i1]
        if p1 < p0 and r1 > r0:                        # lower-low, higher RSI
            cand = (1, "regular_bull", (i0, i1))
            if not best or i1 >= best[2][1]:
                best = cand
        elif p1 > p0 and r1 < r0:                       # higher-low, lower RSI
            cand = (1, "hidden_bull", (i0, i1))
            if not best or i1 >= best[2][1]:
                best = cand
    if not best:
        return {"kind": None, "momentum_score": 0, "pivot_indices": None}
    return {"kind": best[1], "momentum_score": best[0], "pivot_indices": best[2]}
