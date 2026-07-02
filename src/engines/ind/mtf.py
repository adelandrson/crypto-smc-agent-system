"""Multi-timeframe RSI divergence — konfirmasi lintas timeframe.

Mirror pola fvg/mtf.py: TIDAK fetch data baru — resample candle base ke TF lebih tinggi
(count-based: gabung tiap `factor` candle), lalu jalankan deteksi divergensi RSI di TF itu.
Divergensi yang muncul di base DAN dikonfirmasi HTF = sinyal jauh lebih kuat (spec: beberapa
script TradingView menonjolkan konfirmasi divergensi lintas-TF; di sini deterministik).
"""
from __future__ import annotations

from typing import Sequence

from .core import rsi
from .divergence import detect


def resample_candles(candles: Sequence, factor: int) -> list:
    """Gabung tiap `factor` candle base → 1 candle HTF: open pertama, high max, low min,
    close terakhir, volume jumlah. Bucket count-based (mis. 4×15m ≈ 1h)."""
    if factor <= 1:
        return list(candles)
    out = []
    for i in range(0, len(candles) - factor + 1, factor):
        grp = candles[i:i + factor]
        o = grp[0][1]
        h = max(g[2] for g in grp)
        low = min(g[3] for g in grp)
        c = grp[-1][4]
        v = sum((g[5] if len(g) > 5 else 0.0) for g in grp)
        out.append([grp[0][0], o, h, low, c, v])
    return out


def mtf_divergence(candles: Sequence, factors=(4,), depth: int = 5, rsi_period: int = 14) -> dict:
    """Divergensi RSI di TF lebih tinggi (resample base). Return:
    {htf: {factor: score}, mtf_score: +1/-1/0 (mayoritas HTF searah), aligned_count}."""
    htf_scores: dict[int, int] = {}
    for f in factors:
        htf = resample_candles(candles, f)
        if len(htf) < 2 * depth + 3:
            continue
        highs = [c[2] for c in htf]
        lows = [c[3] for c in htf]
        closes = [c[4] for c in htf]
        rsi_s = rsi(closes, rsi_period)
        htf_scores[f] = detect(rsi_s, highs, lows, depth)["momentum_score"]
    pos = sum(1 for s in htf_scores.values() if s > 0)
    neg = sum(1 for s in htf_scores.values() if s < 0)
    mtf_score = 1 if pos > neg else (-1 if neg > pos else 0)
    return {"htf": htf_scores, "mtf_score": mtf_score, "aligned_count": max(pos, neg)}
