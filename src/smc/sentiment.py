"""Multi-CEX sentiment aggregation: OI-weighted funding + summed OI + divergence.

Uses the per-venue fetch_funding / fetch_open_interest of the selected adapters.
Funding is averaged WEIGHTED BY OPEN INTEREST (bigger venues move price more);
OI is SUMMED (total market leverage). Divergence across venues is surfaced — a
market-wide extreme is far stronger than a single-venue local squeeze.
"""

from __future__ import annotations

from typing import List

from .base import ExchangeAdapter

# Funding thresholds (per-interval fraction): contrarian at extremes.
FR_LONG_BIAS = -0.0005   # crowded shorts -> long
FR_SHORT_BIAS = 0.0005   # crowded longs -> short
DIVERGENCE = 0.0005      # max-min funding across venues that flags divergence

# Long/Short account ratio thresholds: contrarian at extremes.
LSR_LONG_BIAS = 0.5      # <=0.5 (crowded shorts) -> long (+1)
LSR_SHORT_BIAS = 2.0     # >=2.0 (crowded longs) -> short (-1)


def fr_score(funding_rate) -> int:
    if funding_rate is None:
        return 0
    if funding_rate <= FR_LONG_BIAS:
        return 1
    if funding_rate >= FR_SHORT_BIAS:
        return -1
    return 0


def lsr_score(ratio) -> int:
    """Contrarian: crowded longs (high ratio) -> bias short (-1); crowded shorts
    (low ratio) -> bias long (+1); else 0. Measures retail crowd positioning,
    distinct from OI (total leverage) and FR (cost of hold)."""
    if ratio is None:
        return 0
    if ratio <= LSR_LONG_BIAS:
        return 1
    if ratio >= LSR_SHORT_BIAS:
        return -1
    return 0


def cvd_score(taker_buy_ratio) -> int:
    """Proxy order-flow leg from taker-buy share of total volume.

    taker_buy_ratio = sum(taker_buy_volume) / sum(total_volume) over the window.
    >0.55 -> aggressive buying (+1); <0.45 -> aggressive selling (-1); else 0.
    A cheap CVD proxy (Binance kline exposes taker-buy; full CVD needs tick data)."""
    if taker_buy_ratio is None:
        return 0
    if taker_buy_ratio >= 0.55:
        return 1
    if taker_buy_ratio <= 0.45:
        return -1
    return 0


def compute_cvd(adapter, symbol, timeframe="1h", limit=100, market_type="perp"):
    """Fetch taker-buy + total volume from an adapter and return the CVD proxy.

    Returns {taker_buy_ratio, cvd_score} or {taker_buy_ratio: None, cvd_score: 0}
    if the venue does not expose taker-buy volume (Bybit/OKX)."""
    try:
        tb = adapter.fetch_taker_buy_volume(symbol, timeframe, limit, market_type)
        candles = adapter.fetch_ohlcv(symbol, timeframe, limit, market_type)
    except Exception:  # noqa: BLE001
        return {"taker_buy_ratio": None, "cvd_score": 0}
    if not tb or not candles:
        return {"taker_buy_ratio": None, "cvd_score": 0}
    total = [float(c[5]) for c in candles if len(c) > 5]
    n = min(len(tb), len(total))
    if n == 0:
        return {"taker_buy_ratio": None, "cvd_score": 0}
    ratio = sum(tb[:n]) / sum(total[:n]) if sum(total[:n]) else None
    return {"taker_buy_ratio": round(ratio, 4) if ratio else None,
            "cvd_score": cvd_score(ratio)}


def _local_extrema(vals, depth=2):
    """Pivot lokal (index, kind) pada deret: high = >= tetangga, low = <= tetangga."""
    out = []
    n = len(vals)
    for i in range(depth, n - depth):
        if all(vals[i] >= vals[j] for j in range(i - depth, i)) and \
           all(vals[i] >= vals[j] for j in range(i + 1, i + depth + 1)):
            out.append((i, "high"))
        if all(vals[i] <= vals[j] for j in range(i - depth, i)) and \
           all(vals[i] <= vals[j] for j in range(i + 1, i + depth + 1)):
            out.append((i, "low"))
    return out


def cvd_divergence(closes, taker_buy, total_vol, depth=2):
    """Divergensi CVD PER-CANDLE (bukan rasio agregat): delta = taker_buy - taker_sell tiap candle,
    CVD = kumulatif. Bearish: harga higher-high tapi CVD lower-high -> -1. Bullish: harga lower-low
    tapi CVD higher-low -> +1. Return {cvd_divergence: 'bull'|'bear'|None, cvd_div_score: +1|-1|0}."""
    none = {"cvd_divergence": None, "cvd_div_score": 0}
    n = min(len(closes), len(taker_buy), len(total_vol))
    if n < 2 * depth + 3:
        return none
    closes, taker_buy, total_vol = closes[:n], taker_buy[:n], total_vol[:n]
    delta = [2.0 * taker_buy[i] - total_vol[i] for i in range(n)]
    cvd, run = [], 0.0
    for d in delta:
        run += d
        cvd.append(run)
    piv = _local_extrema(closes, depth)
    highs = [i for i, k in piv if k == "high"]
    lows = [i for i, k in piv if k == "low"]
    if len(highs) >= 2:
        i0, i1 = highs[-2], highs[-1]
        if closes[i1] > closes[i0] and cvd[i1] < cvd[i0]:
            return {"cvd_divergence": "bear", "cvd_div_score": -1}
    if len(lows) >= 2:
        i0, i1 = lows[-2], lows[-1]
        if closes[i1] < closes[i0] and cvd[i1] > cvd[i0]:
            return {"cvd_divergence": "bull", "cvd_div_score": 1}
    return none


def compute_cvd_divergence(adapter, symbol, timeframe="1h", limit=100, market_type="perp", depth=2):
    """Ambil taker-buy + candle lalu hitung divergensi CVD per-candle (lihat cvd_divergence)."""
    try:
        tb = adapter.fetch_taker_buy_volume(symbol, timeframe, limit, market_type)
        candles = adapter.fetch_ohlcv(symbol, timeframe, limit, market_type)
    except Exception:  # noqa: BLE001
        return {"cvd_divergence": None, "cvd_div_score": 0}
    if not tb or not candles:
        return {"cvd_divergence": None, "cvd_div_score": 0}
    closes = [float(c[4]) for c in candles if len(c) > 5]
    total = [float(c[5]) for c in candles if len(c) > 5]
    return cvd_divergence(closes, tb, total, depth=depth)


def combine_sentiment(per_venue: list) -> dict:
    """Pure aggregation from per-venue {funding_rate, open_interest, long_short_ratio} entries.

    No network I/O — call this on already-fetched venue data so the live data
    path (router) doesn't double-fetch what `market_snapshot` already pulled.
    `aggregate_sentiment` (below) fetches then calls this.
    """
    frs = [(e["funding_rate"], e["open_interest"]) for e in per_venue
           if e.get("funding_rate") is not None]
    ois = [e["open_interest"] for e in per_venue if e.get("open_interest") is not None]
    lsrs = [e["long_short_ratio"] for e in per_venue
            if e.get("long_short_ratio") is not None]

    # OI-weighted funding (fallback to simple mean if OI missing)
    weighted_fr = None
    if frs:
        wsum = sum(oi for _, oi in frs if oi)
        if wsum > 0:
            weighted_fr = sum(fr * (oi or 0) for fr, oi in frs) / wsum
        else:
            weighted_fr = sum(fr for fr, _ in frs) / len(frs)

    fr_values = [fr for fr, _ in frs]
    dispersion = (max(fr_values) - min(fr_values)) if len(fr_values) >= 2 else 0.0
    # mean LSR across venues that report it (only Binance usually)
    mean_lsr = (sum(lsrs) / len(lsrs)) if lsrs else None

    return {
        "venues": len(per_venue),
        "responded": len(fr_values),
        "weighted_funding": weighted_fr,
        "total_open_interest": sum(ois) if ois else None,
        "funding_dispersion": dispersion,
        "divergence": dispersion >= DIVERGENCE,   # single-venue squeeze warning
        "fr_score": fr_score(weighted_fr),         # confluence FR leg (+1/0/-1)
        "consensus_extreme": (len(fr_values) >= 2 and dispersion < DIVERGENCE
                              and fr_score(weighted_fr) != 0),  # market-wide extreme
        "long_short_ratio": mean_lsr,
        "lsr_score": lsr_score(mean_lsr),           # contrarian crowd leg (+1/0/-1)
    }


def aggregate_sentiment(adapters: List[ExchangeAdapter], symbol: str,
                        market_type: str = "perp") -> dict:
    """Pull FR + OI + LSR from each venue and combine. Degrades gracefully if a
    venue fails or does not expose a field (uses whatever responded)."""
    per_venue = []
    for ad in adapters:
        entry = {"exchange": ad.name, "funding_rate": None,
                 "open_interest": None, "long_short_ratio": None}
        try:
            entry["funding_rate"] = ad.fetch_funding(symbol, market_type)
        except Exception as e:  # noqa: BLE001
            entry["funding_error"] = f"{type(e).__name__}: {e}"
        try:
            entry["open_interest"] = ad.fetch_open_interest(symbol, market_type)
        except Exception as e:  # noqa: BLE001
            entry["oi_error"] = f"{type(e).__name__}: {e}"
        try:
            entry["long_short_ratio"] = ad.fetch_long_short_ratio(symbol, market_type)
        except Exception as e:  # noqa: BLE001
            entry["lsr_error"] = f"{type(e).__name__}: {e}"
        per_venue.append(entry)

    out = combine_sentiment(per_venue)
    out["symbol"] = symbol
    out["per_venue"] = per_venue
    return out
