"""Test RSI divergence quality score 0-100."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ind.divergence import detect, _quality


def test_quality_range_and_monotonic():
    # simpangan RSI besar + ekstrem oversold -> quality tinggi; kecil -> rendah
    strong = _quality("regular_bull", 25.0, 45.0)     # gap 20, oversold
    weak = _quality("regular_bull", 48.0, 50.0)       # gap 2, tak oversold
    assert 0 <= weak < strong <= 100
    # hidden < regular utk kondisi sama
    assert _quality("hidden_bull", 25.0, 45.0) < _quality("regular_bull", 25.0, 45.0)


def test_detect_returns_quality():
    # regular bull: price lower-low (idx3=4 -> idx7=3) + RSI higher-low (30 -> 35). depth=2 -> pivot
    # harus di idx [2, n-3]. Highs dibuat rata (tak ada pivot high) supaya cek bull yang menang.
    # high pivot di idx5 memisahkan dua low pivot (idx3,idx7) supaya tak ter-collapse
    highs = [11, 11, 11, 11, 11, 15, 11, 11, 11, 11, 11, 11, 11]
    lows = [10, 9, 9, 4, 8, 9, 9, 3, 8, 9, 10, 11, 12]
    rsi = [50, 45, 45, 30, 45, 45, 45, 35, 45, 48, 50, 50, 50]
    d = detect(rsi, highs, lows, depth=2)
    assert d["momentum_score"] == 1 and d["kind"] == "regular_bull" and 0 < d["quality"] <= 100
