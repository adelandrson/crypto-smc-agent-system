"""Test liquidity sweep / EQH-EQL (stop-hunt) detector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sfib.core import Bar
from sfib.swings import Pivot
from sfib.sweep import find_liquidity_pools, detect_sweep


def _bar(t, o, h, l, c):
    return Bar(index=t, time=t, open=o, high=h, low=l, close=c, volume=1.0)


def test_find_pools_needs_two_equal():
    sw = [Pivot(0, 0, 100.0, "high"), Pivot(2, 2, 100.05, "high"),   # ~equal highs -> EQH pool
          Pivot(1, 1, 90.0, "low"), Pivot(3, 3, 95.0, "low")]        # lows too far apart -> no pool
    pools = find_liquidity_pools(sw, tol=0.2)
    assert len(pools["eqh"]) == 1 and abs(pools["eqh"][0] - 100.025) < 1e-6
    assert pools["eql"] == []                                        # 90 vs 95 > tol


def test_eql_sweep_is_bullish():
    """Low tembus di bawah pool EQL lalu close balik di atas -> sweep sell-side -> BULLISH (+1)."""
    swings = [Pivot(0, 0, 90.0, "low"), Pivot(2, 2, 90.05, "low"),   # EQL pool ~90
              Pivot(1, 1, 100.0, "high"), Pivot(3, 3, 105.0, "high")]
    atr = [1.0] * 10
    # bar terakhir: low 89 (tembus 90) tapi close 92 (balik di atas) = stop-hunt bullish
    bars = [_bar(0, 95, 96, 94, 95), _bar(1, 92, 93, 89.0, 92.0)]
    s = detect_sweep(bars, swings, atr)
    assert s["swept"] and s["direction"] == 1 and s["type"] == "EQL" and s["age"] == 0


def test_eqh_sweep_is_bearish():
    """High tembus di atas pool EQH lalu close balik di bawah -> sweep buy-side -> BEARISH (-1)."""
    swings = [Pivot(0, 0, 110.0, "high"), Pivot(2, 2, 110.1, "high"),   # EQH pool ~110
              Pivot(1, 1, 100.0, "low"), Pivot(3, 3, 95.0, "low")]
    atr = [1.0] * 10
    bars = [_bar(0, 105, 106, 104, 105), _bar(1, 108, 111.0, 107, 108.0)]  # high 111>110, close 108<110
    s = detect_sweep(bars, swings, atr)
    assert s["swept"] and s["direction"] == -1 and s["type"] == "EQH"


def test_no_sweep_when_close_stays_through():
    """Tembus DAN close di sisi yg sama (bukan balik) = break sungguhan, BUKAN sweep."""
    swings = [Pivot(0, 0, 90.0, "low"), Pivot(2, 2, 90.05, "low")]
    atr = [1.0] * 10
    bars = [_bar(0, 95, 96, 94, 95), _bar(1, 91, 92, 88.0, 88.5)]    # low 88 tembus, close 88.5 TETAP di bawah
    assert detect_sweep(bars, swings, atr)["swept"] is False


def test_no_pool_no_sweep():
    swings = [Pivot(0, 0, 90.0, "low"), Pivot(1, 1, 100.0, "high")]  # tak ada >=2 equal
    assert detect_sweep([_bar(0, 95, 96, 80, 95)], swings, [1.0])["swept"] is False
