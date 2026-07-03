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
