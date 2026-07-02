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
