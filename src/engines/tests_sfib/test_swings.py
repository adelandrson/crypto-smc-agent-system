from sfib import normalize_bars, compute_atr, significant_swings
import sfib_fixtures as fixtures


def _swings():
    bars = normalize_bars(fixtures.BARS)
    atr = compute_atr(bars, 14)
    return significant_swings(bars, atr, depth=fixtures.DEPTH, atr_mult=0.5)


def test_detects_known_swings():
    sw = [p for p in _swings() if not p.provisional]     # confirmed pivots only
    assert [p.kind for p in sw] == ["low", "high", "low", "high"]
    assert [p.index for p in sw] == [5, 12, 18, 24]


def test_swing_prices_match_extremes():
    sw = [p for p in _swings() if not p.provisional]
    prices = [round(p.price, 1) for p in sw]
    assert prices == [89.9, 120.1, 95.9, 128.1]


def test_developing_pivot_tracks_current_leg():
    # After the last confirmed pivot (high@24), the live down-leg's running low is a
    # PROVISIONAL swing so structure/Fib track the developing extreme, not a stale pivot.
    dev = _swings()[-1]
    assert dev.provisional is True
    assert dev.kind == "low" and dev.index == 26 and round(dev.price, 1) == 121.9


def test_atr_filter_drops_noise():
    # A huge atr_mult should reject all small legs -> nothing significant.
    from sfib import normalize_bars as nb, compute_atr as ca, zigzag, raw_pivots
    bars = nb(fixtures.BARS)
    atr = ca(bars, 14)
    z = zigzag(raw_pivots(bars, fixtures.DEPTH), atr, atr_mult=1000)
    assert len(z) <= 1
