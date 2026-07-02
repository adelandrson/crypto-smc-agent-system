from fvg import Config, Direction, compute
import fixtures


def base_only(bars, cfg=None):
    _, base, _, _ = compute(bars, cfg or Config())
    return base


def test_bullish_detection():
    base = base_only(fixtures.BULLISH_3)
    assert len(base) == 1
    f = base[0]
    assert f.direction is Direction.BULLISH
    assert f.bottom == 10 and f.top == 12
    assert f.formed_index == 2
    assert f.size == 2


def test_bearish_detection():
    base = base_only(fixtures.BEARISH_3)
    assert len(base) == 1
    f = base[0]
    assert f.direction is Direction.BEARISH
    assert f.bottom == 6 and f.top == 14
    assert f.formed_index == 2


def test_no_gap():
    assert base_only(fixtures.NO_GAP) == []


def test_top_always_above_bottom():
    for fx in (fixtures.BULLISH_3, fixtures.BEARISH_3):
        for f in base_only(fx):
            assert f.top > f.bottom
