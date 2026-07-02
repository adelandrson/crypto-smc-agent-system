from fvg import analyze
import fixtures


def test_analyze_full_shape():
    res = analyze(fixtures.LIFECYCLE, {})
    assert res["ok"] is True
    assert res["bar_count"] == 7
    assert res["last_price"] == 9
    assert "summary" in res and "zones" in res and "alerts" in res
    # one base bullish gap + its inverse
    assert res["summary"]["total"] == 2
    assert res["summary"]["inverse"] == 1


def test_alerts_cover_lifecycle():
    res = analyze(fixtures.LIFECYCLE, {})
    types = [a["type"] for a in res["alerts"]]
    for expected in ("new_fvg", "mitigated", "filled", "invalidated", "ifvg_formed"):
        assert expected in types, f"missing alert: {expected}"


def test_alerts_sorted_by_index():
    res = analyze(fixtures.LIFECYCLE, {})
    idxs = [a["index"] for a in res["alerts"]]
    assert idxs == sorted(idxs)


def test_zones_bias_present():
    res = analyze(fixtures.BULLISH_3, {})
    zones = res["zones"]
    assert zones["bias"] in ("bullish", "bearish", "neutral")
    assert "active_zones" in zones
