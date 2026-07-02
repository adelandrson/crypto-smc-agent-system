from fvg import Config, Direction, detect_mtf, resample_bars, normalize_bars, analyze
import fixtures


def test_resample_aggregates_buckets():
    bars = normalize_bars(fixtures.MTF_BASE)
    htf = resample_bars(bars, htf_minutes=2)  # 120s buckets
    assert len(htf) == 3
    # bucket 0: open of first, high/low aggregated, close of last
    assert htf[0].open == 9 and htf[0].high == 10 and htf[0].low == 8
    assert htf[1].high == 16 and htf[1].low == 10
    assert htf[2].high == 17 and htf[2].low == 12


def test_mtf_detects_higher_tf_gap():
    bars = normalize_bars(fixtures.MTF_BASE)
    zones = detect_mtf(bars, Config(), htf_minutes=2)
    assert len(zones) == 1
    z = zones[0]
    assert z.direction is Direction.BULLISH
    assert z.bottom == 10 and z.top == 12
    assert z.source_tf_minutes == 2


def test_analyze_includes_mtf():
    res = analyze(fixtures.MTF_BASE, {"mtf_minutes": [2]})
    assert res["summary"]["mtf"] == 1
    assert res["mtf_fvgs"][0]["source_tf_minutes"] == 2
