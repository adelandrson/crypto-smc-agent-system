"""Offline calibration sanity on cached real data (reproducible).

Asserts the per-timeframe presets produce a usable swing frequency and that
detection is causal (a swing is known only after `depth` confirming bars).
"""

import csv
from pathlib import Path

import pytest

from sfib import normalize_bars, compute_atr, significant_swings, preset_for, raw_pivots

DATA = Path(__file__).resolve().parents[1] / "tests_fvg" / "data"   # path adapted to this repo's layout (src/engines/*)
CASES = [("BTCUSDT_5m.csv", "5m"), ("ETHUSDT_15m.csv", "15m"),
         ("BTCUSDT_1h.csv", "1h"), ("SOLUSDT_4h.csv", "4h")]


def _candles(name):
    rows = []
    with open(DATA / name) as fh:
        for r in csv.DictReader(fh):
            rows.append({"time": int(r["time"]), "open": float(r["open"]),
                         "high": float(r["high"]), "low": float(r["low"]),
                         "close": float(r["close"]), "volume": float(r["volume"])})
    return rows


def test_preset_values():
    assert preset_for("5m")["depth"] == 5
    assert preset_for("15m")["depth"] == 8
    assert preset_for("1h")["depth"] == 10
    assert preset_for("4h")["depth"] == 10
    assert preset_for("weird")["depth"] == 10  # fallback


@pytest.mark.parametrize("name,tf", CASES)
def test_preset_frequency_is_usable(name, tf):
    if not (DATA / name).exists():
        pytest.skip("no data snapshot")
    p = preset_for(tf)
    bars = normalize_bars(_candles(name))
    atr = compute_atr(bars, 14)
    z = significant_swings(bars, atr, p["depth"], p["atr_mult"])
    per_1000 = len(z) / len(bars) * 1000
    assert 15 <= per_1000 <= 130, f"{tf}: {per_1000:.1f} swings/1000 out of band"
    # strictly alternating high/low
    kinds = [s.kind for s in z]
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))


def test_detection_is_causal():
    """A confirmed pivot only depends on `depth` bars to its right."""
    if not (DATA / "BTCUSDT_1h.csv").exists():
        pytest.skip("no data snapshot")
    bars = normalize_bars(_candles("BTCUSDT_1h.csv"))
    depth = 10
    piv = raw_pivots(bars, depth)
    # every pivot index has at least `depth` bars after it (right-confirmed)
    for p in piv:
        assert p.index + depth < len(bars)
