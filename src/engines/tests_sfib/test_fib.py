import pytest

from sfib import fib_for_leg
from sfib.fib import level, RETRACEMENTS, OTE


def test_level_math():
    # up leg origin=100, extreme=200: 0.5 -> 150, 0.618 -> 138.2
    assert level(100, 200, 0.5) == 150
    assert level(100, 200, 0.618) == pytest.approx(138.2)
    assert level(100, 200, 0.0) == 200   # 0% at the extreme
    assert level(100, 200, 1.0) == 100   # 100% at the origin


def test_fib_for_leg_zones():
    f = fib_for_leg(96.0, 128.0, price=112.0)
    assert f["direction"] == "up"
    assert f["equilibrium"] == pytest.approx(112.0)
    assert f["zone"] == "equilibrium"
    # golden pocket spans 0.618..0.65 -> between these prices
    gp = f["golden_pocket"]
    assert gp[0] > gp[1]  # 0.618 price higher than 0.65 price (up leg)
    # extension 1.618 projects above the extreme
    assert f["extensions"]["1.618"] == pytest.approx(128.0 + 0.618 * 32.0)


def test_ote_zone_detection():
    # price deep in the leg (≈0.705 retr) must flag OTE
    O, E = 100.0, 200.0
    price = level(O, E, 0.705)
    f = fib_for_leg(O, E, price)
    assert f["in_ote"] is True
    assert OTE[0] <= f["retracement_ratio_now"] <= OTE[1]


def test_premium_discount():
    O, E = 100.0, 200.0
    assert fib_for_leg(O, E, 120.0)["zone"] == "discount"   # below equilibrium 150
    assert fib_for_leg(O, E, 180.0)["zone"] == "premium"
