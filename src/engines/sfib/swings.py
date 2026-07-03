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


def developing_pivots(bars: Sequence[Bar], swings: Sequence[Pivot], atr: Sequence[float],
                      atr_mult: float = 0.5) -> List[Pivot]:
    """CHAIN of provisional alternating extremes for the tail (after the last confirmed pivot).

    Fractal pivots lag confirmation by `depth` bars, so the live leg(s) never confirm — leaving
    structure/Fib anchored to a STALE swing. This greedily walks the tail: from the current pivot take
    the running extreme of the OPPOSITE kind; if that move is structurally significant (>= atr_mult x
    ATR) add it as a provisional pivot and continue from there. Walking the chain (not a single step)
    captures multi-leg tails — e.g. high -> developing low -> developing high after a rally that broke
    back above the last swing high — so the active Fib leg matches where price ACTUALLY is, not a leg
    price has already left behind. Honest: uses only printed bars, no look-ahead. `provisional=True`.
    """
    out: List[Pivot] = []
    if not swings or not bars:
        return out
    current = swings[-1]
    n = len(bars)
    guard = 0
    while current.index + 1 < n and guard < 8:
        guard += 1
        rng = range(current.index + 1, n)
        if current.kind == "high":                 # look for the running LOW that follows a high
            ext_i = min(rng, key=lambda i: bars[i].low)
            ext_p, kind, moved = bars[ext_i].low, "low", current.price - bars[ext_i].low
        else:                                      # look for the running HIGH that follows a low
            ext_i = max(rng, key=lambda i: bars[i].high)
            ext_p, kind, moved = bars[ext_i].high, "high", bars[ext_i].high - current.price
        a = atr[ext_i] if 0 <= ext_i < len(atr) else (atr[-1] if atr else 0.0)
        if moved < atr_mult * a:                   # remaining tail move not significant -> stop
            break
        piv = Pivot(ext_i, bars[ext_i].time, ext_p, kind, provisional=True)
        out.append(piv)
        current = piv
    return out


def significant_swings(bars, atr, depth=10, atr_mult=0.5) -> List[Pivot]:
    z = zigzag(raw_pivots(bars, depth), atr, atr_mult)
    z.extend(developing_pivots(bars, z, atr, atr_mult))   # live leg(s) -> structure/Fib track them
    return z
