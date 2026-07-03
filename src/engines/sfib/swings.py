"""Deterministic swing detection: fractal pivots + ATR-filtered ZigZag.

This is the part LLMs get wrong by eyeballing. Here it is rule-based and
reproducible: a pivot high is a bar whose high exceeds the highs of `depth`
bars on both sides (symmetric for lows); pivots are then collapsed into an
alternating high/low sequence and filtered by an ATR threshold so only
structurally significant swings survive.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Sequence

from .core import Bar


@dataclass
class Pivot:
    index: int
    time: float
    price: float
    kind: str  # "high" | "low"
    provisional: bool = False  # True = developing extreme of the current (unconfirmed) leg

    def to_dict(self) -> dict:
        return asdict(self)


def raw_pivots(bars: Sequence[Bar], depth: int = 10) -> List[Pivot]:
    """Fractal pivots confirmed by `depth` bars on each side.

    Confirmation lags by `depth` bars (we only know a pivot once `depth` bars
    have printed after it) — this is honest, not look-ahead.
    """
    n = len(bars)
    out: List[Pivot] = []
    for i in range(depth, n - depth):
        hi, lo = bars[i].high, bars[i].low
        is_high = all(hi > bars[j].high for j in range(i - depth, i)) and \
            all(hi > bars[j].high for j in range(i + 1, i + depth + 1))
        is_low = all(lo < bars[j].low for j in range(i - depth, i)) and \
            all(lo < bars[j].low for j in range(i + 1, i + depth + 1))
        if is_high:
            out.append(Pivot(i, bars[i].time, hi, "high"))
        if is_low:
            out.append(Pivot(i, bars[i].time, lo, "low"))
    out.sort(key=lambda p: p.index)
    return out


def zigzag(pivots: Sequence[Pivot], atr: Sequence[float], atr_mult: float = 0.5) -> List[Pivot]:
    """Collapse pivots into a clean alternating sequence of significant swings.

    Same-type consecutive pivots keep the more extreme one; an opposite pivot is
    only accepted when the move from the last confirmed pivot is at least
    `atr_mult × ATR` (noise filter, volatility-normalised).
    """
    z: List[Pivot] = []
    for p in pivots:
        if not z:
            z.append(p)
            continue
        last = z[-1]
        if p.kind == last.kind:
            if (p.kind == "high" and p.price > last.price) or \
               (p.kind == "low" and p.price < last.price):
                z[-1] = p
        else:
            a = atr[p.index] if 0 <= p.index < len(atr) else (atr[-1] if atr else 0.0)
            thr = atr_mult * a
            if abs(p.price - last.price) >= thr:
                z.append(p)
            # else: too small a move — skip; a later, more extreme opposite
            # pivot will be accepted instead.
    return z


def developing_pivot(bars: Sequence[Bar], swings: Sequence[Pivot], atr: Sequence[float],
                     atr_mult: float = 0.5) -> Pivot | None:
    """Provisional extreme of the CURRENT (still-unconfirmed) leg since the last confirmed pivot.

    Fractal pivots lag confirmation by `depth` bars, so the live leg's extreme (e.g. a fresh swing
    low made 2 bars ago) is never a confirmed pivot yet — leaving structure/Fib anchored to a STALE
    swing. This returns the running extreme of the leg after the last confirmed pivot (a running low
    when the last pivot was a high, else a running high), IF the move is structurally significant
    (>= atr_mult x ATR). Honest: uses only printed bars, no look-ahead. Marked `provisional=True`.
    """
    if not swings or not bars:
        return None
    last = swings[-1]
    n = len(bars)
    start = last.index + 1
    if start >= n:
        return None
    rng = range(start, n)
    if last.kind == "high":                       # current leg is DOWN -> track running low
        ext_i = min(rng, key=lambda i: bars[i].low)
        ext_p, kind, moved = bars[ext_i].low, "low", last.price - bars[ext_i].low
    else:                                          # current leg is UP -> track running high
        ext_i = max(rng, key=lambda i: bars[i].high)
        ext_p, kind, moved = bars[ext_i].high, "high", bars[ext_i].high - last.price
    a = atr[ext_i] if 0 <= ext_i < len(atr) else (atr[-1] if atr else 0.0)
    if moved < atr_mult * a:                       # leg not significant yet -> no provisional swing
        return None
    return Pivot(ext_i, bars[ext_i].time, ext_p, kind, provisional=True)


def significant_swings(bars, atr, depth=10, atr_mult=0.5) -> List[Pivot]:
    z = zigzag(raw_pivots(bars, depth), atr, atr_mult)
    dev = developing_pivot(bars, z, atr, atr_mult)
    if dev is not None:
        z.append(dev)                              # live leg extreme -> structure/Fib track it
    return z
