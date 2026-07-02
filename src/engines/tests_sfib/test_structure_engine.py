import pytest

from sfib import analyze, classify, normalize_bars, compute_atr, significant_swings
import sfib_fixtures as fixtures


def _swings():
    bars = normalize_bars(fixtures.BARS)
    atr = compute_atr(bars, 14)
    return significant_swings(bars, atr, depth=fixtures.DEPTH, atr_mult=0.5)


def test_trend_uptrend():
    st = classify(_swings(), last_close=122.0)
    assert st["trend"] == "uptrend"
    assert st["event"] is None  # 122 < last swing high


def test_bos_and_choch():
    sw = _swings()
    bos = classify(sw, last_close=130.0)        # close above last swing high
    assert bos["event"] == "BOS" and bos["event_direction"] == "bullish"
    choch = classify(sw, last_close=80.0)       # close below last swing low in uptrend
    assert choch["event"] == "CHoCH" and choch["event_direction"] == "bearish"


def test_engine_analyze():
    res = analyze(fixtures.BARS, {"depth": fixtures.DEPTH})
    assert res["ok"] is True
    leg = res["active_leg"]
    assert leg["origin_index"] == 18 and leg["extreme_index"] == 24
    assert res["active_leg"]["fib"]["direction"] == "up"
    assert res["structure"]["trend"] == "uptrend"
    assert res["fib_score"] in (-1, 0, 1)
    assert res["zone"] in ("premium", "discount", "equilibrium")


def test_engine_needs_enough_bars():
    res = analyze(fixtures.BARS[:5], {"depth": fixtures.DEPTH})
    assert res["ok"] is False
