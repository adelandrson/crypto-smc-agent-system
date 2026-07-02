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


def _quality(kind: str, r0: float, r1: float) -> int:
    """Skor KUALITAS divergensi 0-100: makin besar simpangan RSI + makin ekstrem (OB/OS) =
    makin tinggi. Hidden (continuation) sedikit di bawah regular (reversal). Untuk memperhalus
    bobot momentum TANPA mengubah skema skor -4..+4 (nice-to-have, spec final user)."""
    gap = min(1.0, abs(r1 - r0) / 20.0)               # simpangan RSI (cap 20 poin)
    if kind.endswith("bull"):
        extreme = min(1.0, max(0.0, (40.0 - min(r0, r1)) / 40.0))   # RSI rendah = oversold = bagus
    else:
        extreme = min(1.0, max(0.0, (max(r0, r1) - 60.0) / 40.0))   # RSI tinggi = overbought = bagus
    kind_w = 1.0 if kind.startswith("regular") else 0.8
    return round((0.6 * gap + 0.4 * extreme) * kind_w * 100)


def detect(rsi_series: Sequence[float], highs, lows, depth: int = 5) -> dict:
    """Return the most recent divergence signal.

    {kind: "regular_bull"|"regular_bear"|"hidden_bull"|"hidden_bear"|None,
     momentum_score: +1|-1|0, quality: 0-100, pivot_indices: (i_prev, i_now)}"""
    pivots = _price_pivots(highs, lows, depth)
    highs_p = [p for p in pivots if p[2] == "high"]
    lows_p = [p for p in pivots if p[2] == "low"]

    best = None  # (score, kind, (i0,i1), (r0,r1))
    # regular/hidden bear from two most-recent highs
    if len(highs_p) >= 2:
        (i0, p0, _), (i1, p1, _) = highs_p[-2], highs_p[-1]
        r0, r1 = rsi_series[i0], rsi_series[i1]
        if p1 > p0 and r1 < r0:                       # higher-high, lower RSI
            best = (-1, "regular_bear", (i0, i1), (r0, r1))
        elif p1 < p0 and r1 > r0:                      # lower-high, higher RSI
            best = (-1, "hidden_bear", (i0, i1), (r0, r1))
    # regular/hidden bull from two most-recent lows (overrides bear only if newer)
    if len(lows_p) >= 2:
        (i0, p0, _), (i1, p1, _) = lows_p[-2], lows_p[-1]
        r0, r1 = rsi_series[i0], rsi_series[i1]
        if p1 < p0 and r1 > r0:                        # lower-low, higher RSI
            cand = (1, "regular_bull", (i0, i1), (r0, r1))
            if not best or i1 >= best[2][1]:
                best = cand
        elif p1 > p0 and r1 < r0:                       # higher-low, lower RSI
            cand = (1, "hidden_bull", (i0, i1), (r0, r1))
            if not best or i1 >= best[2][1]:
                best = cand
    if not best:
        return {"kind": None, "momentum_score": 0, "quality": 0, "pivot_indices": None}
    return {"kind": best[1], "momentum_score": best[0],
            "quality": _quality(best[1], best[3][0], best[3][1]), "pivot_indices": best[2]}
