"""Tests for Order Block detection (sfib/ob.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sfib.core import normalize_bars, compute_atr
from sfib.swings import significant_swings
from sfib.ob import detect_order_blocks, retest


def _bars(rows):
    """rows: list of [o, h, l, c] -> normalized bars (time=index)."""
    raw = [[i, r[0], r[1], r[2], r[3], 1.0] for i, r in enumerate(rows)]
    return normalize_bars(raw)


def test_ob_detects_bearish_candle_before_up_leg():
    # V then peak-then-down: 20 down, 25 up (peak @39), 6 down -> 2 confirmed pivots
    rows = []
    for i in range(20):                          # downtrend (bearish candles)
        c = 100 - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bottom = 100 - 19                            # = 81
    for i in range(1, 26):                       # uptrend (bullish candles)
        c = bottom + i * 2
        rows.append([c - 2, c + 1, c - 1, c])
    peak = bottom + 25 * 2                       # = 131
    for i in range(1, 7):                        # small decline so the peak is a confirmed high
        c = peak - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    swings = significant_swings(bars, atr, 5, 0.5)
    assert len(swings) >= 2                       # a low then a high
    obs = detect_order_blocks(bars, swings)
    assert obs                                    # at least one OB
    assert any(o["type"] == "bull" for o in obs)  # up-leg -> bullish OB


def test_ob_retest_finds_fresh_aligned_block():
    ob = [{"type": "bull", "top": 98, "bottom": 96, "mid": 97, "status": "fresh"}]
    assert retest(97.2, 1, ob, near_pct=1.0) is not None    # near fresh bull OB
    assert retest(97.2, -1, ob, near_pct=1.0) is None        # wrong direction
    assert retest(120, 1, ob, near_pct=1.0) is None          # too far


def test_ob_retest_ignores_mitigated():
    ob = [{"type": "bull", "top": 98, "bottom": 96, "mid": 97, "status": "mitigated"}]
    assert retest(97, 1, ob, near_pct=2.0) is None           # mitigated -> not fresh


def test_ob_broken_when_close_through_far_edge():
    # bull OB lalu harga CLOSE di bawah bottom zona -> status broken (OB mati, bukan demand lagi)
    rows = []
    for i in range(20):                          # turun
        c = 100 - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bottom = 81
    for i in range(1, 26):                       # naik (bentuk bull OB di dasar)
        c = bottom + i * 2
        rows.append([c - 2, c + 1, c - 1, c])
    peak = bottom + 50
    for i in range(1, 7):                        # koreksi kecil -> konfirmasi pivot high
        c = peak - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    for i in range(1, 60):                       # CRASH: close jauh di bawah dasar -> bull OB broken
        c = peak - 6 - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    swings = significant_swings(bars, atr, 5, 0.5)
    obs = detect_order_blocks(bars, swings, atr=atr)
    bulls = [o for o in obs if o["type"] == "bull" and o["index"] < 25]
    assert bulls and all(o["status"] == "broken" for o in bulls)


def test_ob_giant_candle_refined_to_body():
    # candle OB raksasa (range >> ATR) -> zona di-refine ke BODY (bukan body+wick penuh)
    rows = [[100, 100.6, 99.4, 100]] * 15
    rows.append([100, 130, 40, 60])              # candle bearish RAKSASA (range 90, ATR ~1)
    for i in range(1, 26):                       # up-leg kuat -> candle raksasa itu jadi bull OB
        c = 60 + i * 3
        rows.append([c - 3, c + 1, c - 1, c])
    peak = 60 + 75
    for i in range(1, 7):
        c = peak - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    swings = significant_swings(bars, atr, 5, 0.5)
    obs = detect_order_blocks(bars, swings, atr=atr)
    giant = [o for o in obs if o["index"] == 15]
    assert giant and giant[0]["refined"] is True
    assert giant[0]["top"] == 100 and giant[0]["bottom"] == 60   # body, bukan wick 130/40


def test_bases_detect_accumulation_before_breakout():
    # tren TURUN mulus -> base KETAT (akumulasi) -> breakout NAIK => zona support bull
    from sfib.ob import detect_bases
    rows = []
    for i in range(16):                          # turun mulus (tetapkan ATR, tak bikin base saingan)
        c = 120 - i * 1.2
        rows.append([c + 0.6, c + 0.9, c - 0.9, c - 0.6])
    for _ in range(6):                           # AKUMULASI: range ketat di ~100
        rows.append([100.0, 100.5, 99.5, 100.2])
    for i in range(1, 10):                        # breakout NAIK kuat
        c = 100.2 + i * 3
        rows.append([c - 3, c + 0.5, c - 3.2, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    zs = detect_bases(bars, atr)
    bulls = [z for z in zs if z["type"] == "bull" and z["kind"] == "base"]
    assert bulls, f"akumulasi tak terdeteksi: {zs}"
    z = bulls[-1]
    assert z["status"] in ("fresh", "mitigated")
    assert z["bottom"] <= 99.5 + 0.2 and z["top"] >= 100.5 - 0.2


def test_bases_broken_when_price_closes_back_through():
    from sfib.ob import detect_bases
    rows = []
    for i in range(16):                          # turun mulus
        c = 120 - i * 1.2
        rows.append([c + 0.6, c + 0.9, c - 0.9, c - 0.6])
    for _ in range(6):                           # base ketat
        rows.append([100.0, 100.5, 99.5, 100.2])
    for i in range(1, 6):                        # breakout naik
        c = 100.2 + i * 3
        rows.append([c - 3, c + 0.5, c - 3.2, c])
    for i in range(1, 22):                       # CRASH balik: close jauh di bawah base -> broken
        c = 115 - i * 2
        rows.append([c + 2, c + 2.2, c - 0.3, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    zs = detect_bases(bars, atr)
    bulls = [z for z in zs if z["type"] == "bull"]
    assert bulls and bulls[-1]["status"] == "broken"


def test_ob_requires_fvg():
    # up-leg GRADUAL (overlap, tanpa FVG) -> require_fvg gugurkan OB; mekanisme candle tetap jalan
    from sfib.ob import detect_order_blocks
    rows = []
    for i in range(20):
        c = 100 - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bottom = 81
    for i in range(1, 26):                        # naik gradual: low[i+2] == high[i] -> tanpa gap
        c = bottom + i
        rows.append([c - 0.5, c + 1, c - 1, c])
    peak = bottom + 25
    for i in range(1, 7):
        c = peak - i
        rows.append([c + 1, c + 1.5, c - 0.5, c])
    bars = _bars(rows)
    atr = compute_atr(bars, 14)
    swings = significant_swings(bars, atr, 5, 0.5)
    assert detect_order_blocks(bars, swings, require_fvg=True) == []
    assert detect_order_blocks(bars, swings, require_fvg=False)


def test_vol_confirmed_and_retests():
    from sfib.ob import _vol_confirmed, _count_retests
    from sfib.core import Bar
    def bar(i, o, h, l, c, v): return Bar(index=i, time=i, open=o, high=h, low=l, close=c, volume=v)
    bars = [bar(i, 100, 101, 99, 100, 10.0) for i in range(20)] + [bar(20, 100, 105, 100, 104, 20.0)]
    assert _vol_confirmed(bars, 20) is True           # 20 >= 1.2 x avg(10)
    assert _vol_confirmed(bars, 20, mult=3.0) is False # 20 < 3 x 10
    zb = [bar(0, 100, 100.5, 99.5, 100, 1), bar(1, 103, 104, 102, 103, 1),
          bar(2, 100, 100.5, 99.6, 100, 1), bar(3, 105, 106, 104, 105, 1),
          bar(4, 100, 100.4, 99.7, 100, 1)]
    assert _count_retests(zb, 101, 99, 0) == 3         # masuk zona 3x (bar0,2,4)
