from fvg import Config, compute
import fixtures


def _count(bars, cfg):
    _, base, _, _ = compute(bars, cfg)
    return len([f for f in base if not f.is_inverse])


def test_none_keeps_gap():
    assert _count(fixtures.BULLISH_3, Config(threshold_mode="none")) == 1


def test_atr_filters_small_gap():
    # An absurd ATR multiple rejects the 2-point gap.
    assert _count(fixtures.BULLISH_3, Config(threshold_mode="atr", min_atr_mult=100)) == 0
    # A tiny multiple keeps it.
    assert _count(fixtures.BULLISH_3, Config(threshold_mode="atr", min_atr_mult=0.01)) == 1


def test_percent_filters_small_gap():
    # Gap is ~12.5% of price; a 50% requirement rejects it, 1% keeps it.
    assert _count(fixtures.BULLISH_3, Config(threshold_mode="percent", min_pct=50)) == 0
    assert _count(fixtures.BULLISH_3, Config(threshold_mode="percent", min_pct=1)) == 1
