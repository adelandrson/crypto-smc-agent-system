"""Bar normalisation + ATR for the swing/Fibonacci engine (pure stdlib)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

_REQ = ("open", "high", "low", "close")


@dataclass
class Bar:
    index: int
    time: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def normalize_bars(raw: Sequence) -> List[Bar]:
    bars: List[Bar] = []
    for i, row in enumerate(raw):
        if isinstance(row, Bar):
            bars.append(Bar(i, row.time, row.open, row.high, row.low, row.close, row.volume))
            continue
        if isinstance(row, dict):
            for k in _REQ:
                if k not in row:
                    raise ValueError(f"bar {i} missing '{k}'")
            b = Bar(i, float(row.get("time", i)), float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]), float(row.get("volume", 0.0) or 0.0))
        else:
            seq = list(row)
            if len(seq) < 5:
                raise ValueError(f"bar {i} needs [time,o,h,l,c]")
            b = Bar(i, float(seq[0]), float(seq[1]), float(seq[2]), float(seq[3]),
                    float(seq[4]), float(seq[5]) if len(seq) > 5 else 0.0)
        if b.high < b.low:
            raise ValueError(f"bar {i}: high<low")
        bars.append(b)
    return bars


def compute_atr(bars: Sequence[Bar], period: int = 14) -> List[float]:
    n = len(bars)
    if n == 0:
        return []
    period = max(1, int(period))
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b.high - b.low)
        else:
            pc = bars[i - 1].close
            tr.append(max(b.high - b.low, abs(b.high - pc), abs(b.low - pc)))
    atr, run = [], 0.0
    for i in range(n):
        run += tr[i]
        if i < period:
            atr.append(run / (i + 1))
        else:
            run -= tr[i - period]
            atr.append(run / period)
    return atr
