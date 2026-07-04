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


def _bar(o, c, h, l):
    return {"time": 0.0, "open": o, "high": h, "low": l, "close": c, "volume": 1000.0}


def _rising_then_falling(n=21, peak=10):
    # naik landai lalu turun -> bikin turning point yg jelas di sekitar `peak`
    bars = []
    for i in range(n):
        base = 100 + i * 0.2 if i < peak else 100 + peak * 0.2 - (i - peak) * 0.5
        o = base
        c = base + 0.1
        bars.append(_bar(o, c, max(o, c) + 0.2, min(o, c) - 0.2))
    return bars


def test_equal_high_double_top_is_marked():
    # DUA wick sama-tinggi (double-top / EQH) di idx 8 & 10 (idx 9 lebih rendah).
    # Sebelum fix: strict '>' gagal utk keduanya -> swing high (wick) HILANG.
    from sfib import normalize_bars as nb, raw_pivots
    bars = _rising_then_falling()
    for idx in (8, 10):
        bars[idx]["high"] = 110.0
    piv = raw_pivots(nb(bars), depth=3)
    highs = [p for p in piv if p.kind == "high"]
    assert any(abs(p.price - 110.0) < 1e-9 for p in highs), "wick equal-high 110 harus tertandai"


def test_equal_low_double_bottom_is_marked():
    from sfib import normalize_bars as nb, raw_pivots
    # cermin: dua wick-low sama-rendah (EQL) — bikin lembah lalu suntik equal lows
    bars = []
    for i in range(21):
        base = 100 - i * 0.2 if i < 10 else 100 - 10 * 0.2 + (i - 10) * 0.5
        o = base
        c = base + 0.1
        bars.append(_bar(o, c, max(o, c) + 0.2, min(o, c) - 0.2))
    for idx in (8, 10):
        bars[idx]["low"] = 96.0
    piv = raw_pivots(nb(bars), depth=3)
    lows = [p for p in piv if p.kind == "low"]
    assert any(abs(p.price - 96.0) < 1e-9 for p in lows), "wick equal-low 96 harus tertandai"


def test_plateau_yields_exactly_one_pivot():
    # Plateau 3-bar sama tinggi -> TEPAT satu pivot (bar pertama), bukan penanda ganda.
    from sfib import normalize_bars as nb, raw_pivots
    bars = _rising_then_falling()
    for idx in (8, 9, 10):
        bars[idx]["high"] = 110.0
    piv = [p for p in raw_pivots(nb(bars), depth=3) if abs(p.price - 110.0) < 1e-9]
    assert len(piv) == 1 and piv[0].index == 8
