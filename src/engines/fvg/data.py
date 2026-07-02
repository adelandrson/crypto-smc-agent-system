"""OHLC normalisation, ATR computation and (optional) CSV loading."""

from __future__ import annotations

import csv
from typing import List, Sequence

from .types import Bar

_REQUIRED = ("open", "high", "low", "close")


def normalize_bars(raw: Sequence) -> List[Bar]:
    """Coerce a sequence of OHLC rows into `Bar` objects.

    Accepts dicts with keys open/high/low/close (+ optional time/volume) or
    sequences laid out as [time, open, high, low, close, volume]. `time` is
    optional and defaults to the row index.
    """

    bars: List[Bar] = []
    for i, row in enumerate(raw):
        if isinstance(row, Bar):
            bar = Bar(i, row.time, row.open, row.high, row.low, row.close, row.volume)
        elif isinstance(row, dict):
            for key in _REQUIRED:
                if key not in row:
                    raise ValueError(f"bar {i} missing required field '{key}'")
            bar = Bar(
                index=i,
                time=float(row.get("time", i)),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
            )
        else:  # assume an ordered sequence
            seq = list(row)
            if len(seq) < 5:
                raise ValueError(
                    f"bar {i} sequence needs [time, open, high, low, close], got {seq!r}"
                )
            bar = Bar(
                index=i,
                time=float(seq[0]),
                open=float(seq[1]),
                high=float(seq[2]),
                low=float(seq[3]),
                close=float(seq[4]),
                volume=float(seq[5]) if len(seq) > 5 else 0.0,
            )
        _validate(bar)
        bars.append(bar)
    return bars


def _validate(bar: Bar) -> None:
    if not (bar.high >= bar.low):
        raise ValueError(f"bar {bar.index}: high {bar.high} < low {bar.low}")
    if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
        # Tolerate tiny floating point excursions but reject genuine garbage.
        span = bar.high - bar.low
        eps = max(abs(bar.high), abs(bar.low), 1.0) * 1e-9 + span * 1e-9
        if not (
            bar.low - eps <= bar.open <= bar.high + eps
            and bar.low - eps <= bar.close <= bar.high + eps
        ):
            raise ValueError(
                f"bar {bar.index}: open/close outside high/low range"
            )


def compute_atr(bars: Sequence[Bar], period: int = 14) -> List[float]:
    """Average True Range aligned to `bars`.

    Uses a simple rolling mean of True Range. For the first `period` bars the
    ATR is the running mean of the available True Ranges (so early gaps still
    receive a sensible, non-zero reference).
    """

    n = len(bars)
    if n == 0:
        return []
    period = max(1, int(period))
    tr: List[float] = []
    for i, bar in enumerate(bars):
        if i == 0:
            tr.append(bar.high - bar.low)
        else:
            prev_close = bars[i - 1].close
            tr.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - prev_close),
                    abs(bar.low - prev_close),
                )
            )
    atr: List[float] = []
    running = 0.0
    for i in range(n):
        running += tr[i]
        if i < period:
            atr.append(running / (i + 1))
        else:
            running -= tr[i - period]
            atr.append(running / period)
    return atr


def load_csv(path: str) -> List[Bar]:
    """Load OHLC bars from a CSV with a header row.

    Recognised columns (case-insensitive): time/timestamp/date, open, high,
    low, close, volume. Used by the `fvg_*` tools when given a file path.
    """

    rows: List[dict] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty or header-less CSV")
        lookup = {name.strip().lower(): name for name in reader.fieldnames}

        def col(*candidates):
            for cand in candidates:
                if cand in lookup:
                    return lookup[cand]
            return None

        t = col("time", "timestamp", "date", "datetime")
        o = col("open", "o")
        h = col("high", "h")
        low_c = col("low", "l")
        c = col("close", "c")
        v = col("volume", "vol", "v")
        if not all([o, h, low_c, c]):
            raise ValueError(f"{path}: CSV missing open/high/low/close columns")
        for i, line in enumerate(reader):
            rows.append(
                {
                    "time": _parse_time(line[t]) if t else i,
                    "open": line[o],
                    "high": line[h],
                    "low": line[low_c],
                    "close": line[c],
                    "volume": line[v] if v else 0.0,
                }
            )
    return normalize_bars(rows)


def _parse_time(value: str):
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        # Best-effort ISO-8601 parsing without pulling in dependencies.
        from datetime import datetime

        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).timestamp()
            except ValueError:
                continue
        return 0.0
