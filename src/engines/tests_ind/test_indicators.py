"""Tests for the momentum/volatility/volume indicators engine (offline)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ind.core import rsi, adx, atr_percentile, bollinger_width, volume_zscore
from ind.divergence import detect
from ind.engine import analyze


def _candles(prices, start_ts=0, step=60):
    """Build [ts,o,h,l,c,v] from a close series; o=h=l=c, v=1 (flat bars)."""
    out = []
    for i, p in enumerate(prices):
        ts = (start_ts + i * step) * 1000
        out.append([ts, p, p, p, p, 1.0])
    return out


def _realistic(prices, start_ts=0, step=60):
    """Bars with proper o/h/l/c (high=max(o,c)+1, low=min(o,c)-1)."""
    out = []
    for i, p in enumerate(prices):
        ts = (start_ts + i * step) * 1000
        o = prices[i - 1] if i > 0 else p
        out.append([ts, o, max(o, p) + 1, min(o, p) - 1, p, 10.0 + i])
    return out


# ----------------------------- RSI -----------------------------------------
def test_rsi_rising_to_100():
    closes = [100 + i for i in range(30)]
    r = rsi(closes, 14)
    assert r[-1] > 90                       # strong uptrend -> RSI near 100


def test_rsi_falling_to_0():
    closes = [100 - i for i in range(30)]
    r = rsi(closes, 14)
    assert r[-1] < 10


def test_rsi_flat_near_50():
    closes = [100.0] * 30
    r = rsi(closes, 14)
    assert 45 <= r[-1] <= 55


# ----------------------------- ADX -----------------------------------------
def test_adx_trending_uptrend_high():
    prices = [100 + i * 2 for i in range(50)]   # strong linear uptrend
    bars = _realistic(prices)
    from ind.core import _to_arrays
    h, l, c, v = _to_arrays(bars)
    d = adx(h, l, c, 14)
    assert d["adx"][-1] > 20                    # ADX rises in a trend


def test_adx_flat_low():
    prices = [100.0] * 50
    bars = _realistic(prices)
    from ind.core import _to_arrays
    h, l, c, v = _to_arrays(bars)
    d = adx(h, l, c, 14)
    assert d["adx"][-1] < 25


# ---------------------- atr_percentile / bb / volume -----------------------
def test_atr_percentile_in_range():
    prices = [100 + (i % 5) for i in range(120)]
    bars = _realistic(prices)
    from ind.core import _to_arrays
    h, l, c, v = _to_arrays(bars)
    pct = atr_percentile(h, l, c, 14, 100)
    assert 0.0 <= pct <= 1.0


def test_bb_width_positive_and_mid():
    prices = [100 + i * 0.5 for i in range(30)]
    bb = bollinger_width(prices, 20, 2.0)
    assert bb["width_pct"] >= 0 and bb["mid"] is not None


def test_volume_zscore_high_on_spike():
    vols = [10.0] * 25 + [50.0]
    z = volume_zscore(vols, 20)
    assert z > 2.0                              # spike -> high z


def test_volume_zscore_zero_on_flat():
    vols = [10.0] * 25
    assert volume_zscore(vols, 20) == 0.0


# ----------------------------- divergence ----------------------------------
def test_divergence_no_signal_on_flat():
    closes = [100.0] * 60
    highs = lows = closes
    r = rsi(closes, 14)
    assert detect(r, highs, lows, depth=5)["kind"] is None
    assert detect(r, highs, lows)["momentum_score"] == 0


def test_divergence_returns_valid_score():
    # build a price series with swings; any divergence detected must score +/-1
    prices = []
    for i in range(80):
        prices.append(100 + 10 * (1 if (i // 10) % 2 == 0 else -1) * (i % 10) / 10)
    bars = _realistic(prices)
    from ind.core import _to_arrays
    h, l, c, v = _to_arrays(bars)
    r = rsi(c, 14)
    d = detect(r, h, l, depth=5)
    assert d["momentum_score"] in (-1, 0, 1)


# ----------------------------- engine.analyze ------------------------------
def test_engine_analyze_schema():
    prices = [100 + i * 0.5 for i in range(60)]
    bars = _realistic(prices)
    res = analyze(bars)
    assert res["ok"] is True
    for k in ("rsi", "adx", "vol_state", "ranging", "volume_z", "volume_ok",
              "rsi_divergence", "momentum_score", "atr_percentile", "bb_width_pct"):
        assert k in res
    assert res["vol_state"] in ("trending", "breakout", "ranging", "mixed")
    assert isinstance(res["ranging"], bool)
    assert isinstance(res["volume_ok"], bool)
    assert res["momentum_score"] in (-1, 0, 1)


def test_engine_ranging_on_flat_squeeze():
    prices = [100.0 + (i % 3) * 0.01 for i in range(60)]   # near-flat
    bars = _realistic(prices)
    res = analyze(bars, {"adx_ranging": 25.0})
    assert res["vol_state"] in ("ranging", "mixed")


def test_engine_trending_on_strong_trend():
    prices = [100 + i * 2 for i in range(60)]
    bars = _realistic(prices)
    res = analyze(bars)
    assert res["vol_state"] == "trending"


def test_engine_insufficient_candles():
    res = analyze([[0, 1, 2, 1, 1, 1], [60, 1, 2, 1, 1, 1]])
    assert res["ok"] is False


def test_ind_analyze_tool():
    import tools as t
    prices = [100 + i * 0.5 for i in range(60)]
    bars = _realistic(prices)
    out = json.loads(t.ind_analyze({"bars": bars}))
    assert out["ok"] is True and "rsi" in out
