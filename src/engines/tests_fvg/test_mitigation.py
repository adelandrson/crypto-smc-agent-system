from fvg import Config, Direction, State, compute
import fixtures


def _base_gap(bars, cfg):
    _, base, _, _ = compute(bars, cfg)
    # the non-inverse gap
    return next(f for f in base if not f.is_inverse)


def test_full_lifecycle():
    cfg = Config()
    f = _base_gap(fixtures.LIFECYCLE, cfg)
    assert f.direction is Direction.BULLISH
    assert f.formed_index == 2
    assert f.mitigated_index == 4
    assert f.filled_index == 5
    assert f.invalidated_index == 6
    assert f.state is State.INVALIDATED
    assert f.is_active is False


def test_wick_vs_close_mitigation():
    # Bar 4 wicks (low) into the zone but its close (11.5) is below top (12),
    # so both wick and close modes mitigate at index 4 here. Verify wick mode
    # never mitigates later than close mode.
    wick = _base_gap(fixtures.LIFECYCLE, Config(mitigation_mode="wick"))
    close = _base_gap(fixtures.LIFECYCLE, Config(mitigation_mode="close"))
    assert wick.mitigated_index <= close.mitigated_index


def test_inverse_disabled():
    _, base, _, _ = compute(fixtures.LIFECYCLE, Config(enable_inverse=False))
    assert all(not f.is_inverse for f in base)
    assert len(base) == 1
