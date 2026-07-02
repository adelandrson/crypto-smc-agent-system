"""Hand-crafted OHLC fixtures with known, deterministic FVG outcomes."""


def b(o, h, l, c, t=None, v=0.0):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def stamp(bars, step=60):
    """Assign ascending timestamps `step` seconds apart."""
    for i, bar in enumerate(bars):
        if bar["time"] is None:
            bar["time"] = i * step
    return bars


# A single bullish FVG: high[0]=10, low[2]=12 -> gap zone [10, 12].
BULLISH_3 = stamp([
    b(9, 10, 8, 9),
    b(10, 16, 10, 15),
    b(16, 17, 12, 16),
])

# A single bearish FVG: low[0]=14, high[2]=6 -> gap zone [6, 14].
BEARISH_3 = stamp([
    b(15, 16, 14, 15),
    b(10, 10, 4, 5),
    b(5, 6, 3, 4),
])

# Three overlapping candles -> no imbalance.
NO_GAP = stamp([
    b(10, 11, 9, 10),
    b(10, 12, 9, 11),
    b(11, 12, 10, 11),
])

# Full bullish lifecycle. Gap zone [10, 12] forms at index 2, then:
#   index 4: wick into the zone        -> mitigated
#   index 5: low reaches the far edge  -> filled
#   index 6: close below the far edge  -> invalidated (flips to inverse FVG)
# Subsequent bars are shaped so they do NOT spawn additional base gaps.
LIFECYCLE = stamp([
    b(9, 10, 8, 9),         # 0  high=10
    b(10, 16, 10, 15),      # 1  displacement up
    b(16, 17, 12, 16),      # 2  low=12 -> bullish FVG [10,12]
    b(16, 16.5, 13, 13.5),  # 3  stays above the gap
    b(13.5, 13.5, 11, 11.5),# 4  low=11 -> mitigated
    b(11.5, 13.5, 10, 10.5),# 5  low=10 -> filled
    b(10.5, 11.5, 8, 9),    # 6  close=9 -> invalidated
])

# Multi-timeframe: 1-minute base bars that aggregate (htf=2m, 120s buckets)
# into a 3-candle HTF bullish FVG with zone [10, 12].
MTF_BASE = stamp([
    b(9, 10, 8, 9),         # bucket 0
    b(9, 9.5, 8.5, 9),      # bucket 0
    b(10, 16, 10, 15),      # bucket 1
    b(15, 15.5, 12, 13),    # bucket 1
    b(13, 17, 12, 16),      # bucket 2
    b(16, 16.5, 13, 14),    # bucket 2
], step=60)
