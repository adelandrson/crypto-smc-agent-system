"""Test MTF divergence: resample base->HTF + deteksi divergensi lintas-TF."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ind.mtf import resample_candles, mtf_divergence


def test_resample_aggregates_ohlc():
    # 4 candle base -> 1 candle HTF: open pertama, high max, low min, close terakhir, vol jumlah
    base = [[0, 10, 12, 9, 11, 5], [1, 11, 15, 10, 14, 5], [2, 14, 16, 13, 13, 5], [3, 13, 14, 8, 12, 5]]
    htf = resample_candles(base, 4)
    assert len(htf) == 1
    assert htf[0][1] == 10 and htf[0][2] == 16 and htf[0][3] == 8 and htf[0][4] == 12 and htf[0][5] == 20


def test_resample_factor_one_identity():
    base = [[0, 1, 2, 0, 1, 1]]
    assert resample_candles(base, 1) == base


def test_mtf_divergence_shape():
    # data cukup panjang: return struktur benar (skor -1/0/1)
    candles = [[i, 100 + i % 5, 101 + i % 5, 99 + i % 5, 100 + i % 5, 10] for i in range(120)]
    r = mtf_divergence(candles, factors=(4, 12), depth=5)
    assert set(r.keys()) == {"htf", "mtf_score", "aligned_count"}
    assert r["mtf_score"] in (-1, 0, 1)
