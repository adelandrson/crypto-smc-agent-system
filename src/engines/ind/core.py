"""Momentum / volatility / volume indicators (pure stdlib).

RSI (Wilder), ADX/DI, ATR percentile, Bollinger Band width, volume z-score.
Operates on plain arrays extracted from candles so this plugin is self-contained
(no sfib dependency). The divergence module reuses a local fractal pivot so it
does not collide with the swing-fib engine's structural pivots.
"""
from __future__ import annotations

from typing import List, Sequence


def _to_arrays(candles: Sequence) -> tuple:
    """Split [ts,o,h,l,c,v] rows into (highs, lows, closes, volumes) arrays."""
    highs, lows, closes, volumes = [], [], [], []
    for c in candles:
        seq = list(c)
        highs.append(float(seq[2])); lows.append(float(seq[3]))
        closes.append(float(seq[4]))
        volumes.append(float(seq[5]) if len(seq) > 5 else 0.0)
    return highs, lows, closes, volumes


def rsi(closes: Sequence[float], period: int = 14) -> List[float]:
    """Wilder's RSI. Returns a list aligned with closes (early values are
    the seed SMA-then-smoothed form)."""
    n = len(closes)
    if n < period + 1:
        return [50.0] * n
    out = [50.0] * n
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0); losses += max(-ch, 0.0)
    avg_g = gains / period
    avg_l = losses / period
    if avg_g == 0 and avg_l == 0:
        out[period] = 50.0        # flat: no movement -> neutral
    else:
        out[period] = 100.0 - (100.0 / (1.0 + (avg_g / avg_l if avg_l else 999.0)))
    for i in range(period + 1, n):
        ch = closes[i] - closes[i - 1]
        g = max(ch, 0.0); l = max(-ch, 0.0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        if avg_g == 0 and avg_l == 0:
            out[i] = 50.0
        else:
            rs = avg_g / avg_l if avg_l else 999.0
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def true_range(highs, lows, closes) -> List[float]:
    tr = [highs[0] - lows[0]] if highs else []
    for i in range(1, len(highs)):
        pc = closes[i - 1]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return tr


def atr(highs, lows, closes, period: int = 14) -> List[float]:
    """Wilder ATR (same smoothing as RSI)."""
    tr = true_range(highs, lows, closes)
    n = len(tr)
    if n == 0:
        return []
    out = [0.0] * n
    run = 0.0
    for i in range(n):
        run += tr[i]
        if i < period:
            out[i] = run / (i + 1)
        else:
            run -= tr[i - period]
            out[i] = run / period
    return out


def adx(highs, lows, closes, period: int = 14) -> dict:
    """ADX + DI+ / DI-. Returns dict of lists aligned with input."""
    n = len(highs)
    if n < 2 * period:
        return {"adx": [0.0] * n, "plus_di": [0.0] * n, "minus_di": [0.0] * n}
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = true_range(highs, lows, closes)
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
    # Wilder smoothing of tr, +DM, -DM
    atr_s = [0.0] * n; pdm_s = [0.0] * n; mdm_s = [0.0] * n
    atr_s[period - 1] = sum(tr[:period]); pdm_s[period - 1] = sum(plus_dm[:period])
    mdm_s[period - 1] = sum(minus_dm[:period])
    for i in range(period, n):
        atr_s[i] = atr_s[i - 1] - atr_s[i - 1] / period + tr[i]
        pdm_s[i] = pdm_s[i - 1] - pdm_s[i - 1] / period + plus_dm[i]
        mdm_s[i] = mdm_s[i - 1] - mdm_s[i - 1] / period + minus_dm[i]
    pdi = [(pdm_s[i] / atr_s[i] * 100.0) if atr_s[i] else 0.0 for i in range(n)]
    mdi = [(mdm_s[i] / atr_s[i] * 100.0) if atr_s[i] else 0.0 for i in range(n)]
    dx = [abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) * 100.0 if (pdi[i] + mdi[i]) else 0.0
          for i in range(n)]
    adx_list = [0.0] * n
    start = 2 * period - 1
    if start < n:
        adx_list[start] = sum(dx[period:start + 1]) / period
        for i in range(start + 1, n):
            adx_list[i] = (adx_list[i - 1] * (period - 1) + dx[i]) / period
    return {"adx": adx_list, "plus_di": pdi, "minus_di": mdi}


def atr_percentile(highs, lows, closes, period: int = 14, lookback: int = 100) -> float:
    """Current ATR rank (0..1) vs the last `lookback` ATR values. High = volatile."""
    a = atr(highs, lows, closes, period)
    if not a:
        return 0.5
    window = a[-lookback:] if len(a) >= lookback else a
    cur = a[-1]
    rank = sum(1 for v in window if v <= cur) / len(window)
    return round(rank, 3)


def bollinger_width(closes, period: int = 20, num_std: float = 2.0) -> dict:
    """Bollinger Band width (% of mid) + bands. Width low = squeeze (ranging)."""
    n = len(closes)
    if n < period:
        return {"width_pct": 0.0, "upper": None, "lower": None, "mid": None}
    s = closes[-period:]
    mid = sum(s) / period
    var = sum((x - mid) ** 2 for x in s) / period
    sd = var ** 0.5
    upper = mid + num_std * sd
    lower = mid - num_std * sd
    width_pct = ((upper - lower) / mid * 100.0) if mid else 0.0
    return {"width_pct": round(width_pct, 4), "upper": upper, "lower": lower, "mid": mid}


def volume_zscore(volumes, period: int = 20) -> float:
    """Z-score of the latest volume vs the mean/std of the last `period`."""
    if len(volumes) < period:
        return 0.0
    s = volumes[-period:]
    mean = sum(s) / period
    var = sum((x - mean) ** 2 for x in s) / period
    sd = var ** 0.5
    if sd == 0:
        return 0.0
    return round((volumes[-1] - mean) / sd, 3)
