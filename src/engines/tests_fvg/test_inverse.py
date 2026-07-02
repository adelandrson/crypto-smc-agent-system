from fvg import Config, Direction, compute
import fixtures


def test_inverse_created_on_invalidation():
    _, base, _, _ = compute(fixtures.LIFECYCLE, Config())
    inverses = [f for f in base if f.is_inverse]
    assert len(inverses) == 1
    inv = inverses[0]
    # Original gap was bullish -> inverse is bearish, same price boundaries.
    assert inv.direction is Direction.BEARISH
    assert inv.bottom == 10 and inv.top == 12
    assert inv.formed_index == 6  # forms at the invalidation bar


def test_inverse_carries_zone():
    _, base, _, _ = compute(fixtures.LIFECYCLE, Config())
    bull = next(f for f in base if not f.is_inverse)
    inv = next(f for f in base if f.is_inverse)
    assert (inv.top, inv.bottom) == (bull.top, bull.bottom)
