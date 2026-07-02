"""Multi-timeframe support: resample base bars to a higher timeframe and
detect gaps there, so HTF zones can be projected onto the base chart."""

from __future__ import annotations

from typing import List, Sequence

from .types import Bar, Config, FVG
from .data import compute_atr
from .detector import detect_fvgs
from .mitigation import resolve_all


def resample_bars(bars: Sequence[Bar], htf_minutes: int) -> List[Bar]:
    """Aggregate base bars into higher-timeframe candles by time bucket.

    Bars are assumed to be in ascending time order. Each output candle spans
    `htf_minutes` of wall-clock time; partial trailing buckets are kept so the
    most recent (forming) HTF candle is still represented.
    """

    if htf_minutes <= 0:
        raise ValueError("htf_minutes must be positive")
    bucket_seconds = htf_minutes * 60
    out: List[Bar] = []
    cur_key = None
    o = h = low_v = c = 0.0
    vol = 0.0
    start_time = 0.0
    idx = 0

    def flush():
        nonlocal idx
        out.append(
            Bar(
                index=idx,
                time=start_time,
                open=o,
                high=h,
                low=low_v,
                close=c,
                volume=vol,
            )
        )
        idx += 1

    for bar in bars:
        key = int(bar.time // bucket_seconds)
        if cur_key is None:
            cur_key = key
            o, h, low_v, c, vol, start_time = (
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.time,
            )
        elif key == cur_key:
            h = max(h, bar.high)
            low_v = min(low_v, bar.low)
            c = bar.close
            vol += bar.volume
        else:
            flush()
            cur_key = key
            o, h, low_v, c, vol, start_time = (
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.time,
            )
    if cur_key is not None:
        flush()
    return out


def detect_mtf(
    bars: Sequence[Bar], cfg: Config, htf_minutes: int, start_id: int = 0
) -> List[FVG]:
    """Detect and resolve gaps on a single higher timeframe.

    Returned FVGs carry `source_tf_minutes` and HTF-relative `formed_index`,
    but absolute `formed_time` so they map cleanly onto the base chart.
    """

    htf_bars = resample_bars(bars, htf_minutes)
    if len(htf_bars) < 3:
        return []
    atr = compute_atr(htf_bars, cfg.atr_period)
    raw = detect_fvgs(
        htf_bars, atr, cfg, start_id=start_id, source_tf_minutes=htf_minutes
    )
    return resolve_all(raw, htf_bars, cfg, next_id=start_id + len(raw))
