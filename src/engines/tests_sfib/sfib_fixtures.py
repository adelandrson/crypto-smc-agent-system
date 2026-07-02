"""Synthetic OHLC with KNOWN swing points → deterministic Fib/structure tests.

Piecewise-linear path through anchors (index, price); turning points become
clean fractal pivots at depth=2. Swing lows at idx 5 & 18, swing highs at idx
12 & 24; trailing bars confirm the last pivot.
"""

ANCHORS = [(0, 100.0), (5, 90.0), (12, 120.0), (18, 96.0), (24, 128.0),
           (25, 124.0), (26, 122.0)]
DEPTH = 2


def _interp(i):
    for (i0, p0), (i1, p1) in zip(ANCHORS, ANCHORS[1:]):
        if i0 <= i <= i1:
            if i1 == i0:
                return p0
            return p0 + (p1 - p0) * (i - i0) / (i1 - i0)
    return ANCHORS[-1][1]


def make_bars():
    last = ANCHORS[-1][0]
    bars = []
    prev = _interp(0)
    for i in range(last + 1):
        p = _interp(i)
        bars.append({"time": i * 60, "open": prev, "high": p + 0.1,
                     "low": p - 0.1, "close": p, "volume": 1.0})
        prev = p
    return bars


BARS = make_bars()
# Known active leg: origin = swing low @18 (≈96), extreme = swing high @24 (=128)
LEG_ORIGIN = 96.0
LEG_EXTREME = 128.0
