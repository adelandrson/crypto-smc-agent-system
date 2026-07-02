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


def significant_swings(bars, atr, depth=10, atr_mult=0.5) -> List[Pivot]:
    return zigzag(raw_pivots(bars, depth), atr, atr_mult)
