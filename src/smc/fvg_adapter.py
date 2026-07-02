"""FVG adapter — the SINGLE bridge between the fvg-nephew-sam engine and the
crypto-trader-signals confluence model.

Why this exists: the bundle must have exactly ONE FVG implementation. The
`fvg-nephew-sam` plugin engine is that single source of truth. Everything that
needs FVGs (the cron data script, the skill's confluence leg) goes through this
adapter, which:
  * loads the engine in-process (no second FVG code path), and
  * translates the engine's rich output into the schema the existing
    crypto-trader-signals skill already expects (type/top/bottom/mid/gap_pct/
    status/dist_pct), enriched with state/atr_multiple/source_tf/is_inverse.

Status vocabulary mapping (engine state -> skill status):
    unmitigated  -> fresh
    mitigated    -> tested
    filled       -> partially_mitigated
    invalidated  -> mitigated
Only `fresh`/`tested` gaps are "active" (tradeable), matching engine.is_active.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ---- load the engine exactly once (single FVG authority) ------------------
# path adapted to this repo's layout: src/smc/ (this file) -> src/engines/fvg (was plugins/fvg-nephew-sam/fvg)
_ENGINE_PKG = Path(__file__).resolve().parents[1] / "engines" / "fvg"


def _load_engine():
    if "fvg" in sys.modules:
        return sys.modules["fvg"]
    spec = importlib.util.spec_from_file_location(
        "fvg", _ENGINE_PKG / "__init__.py",
        submodule_search_locations=[str(_ENGINE_PKG)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fvg"] = mod
    spec.loader.exec_module(mod)
    return mod


fvg = _load_engine()

#: marker the integration tests assert on to prove a single FVG path
FVG_ENGINE_VERSION = getattr(fvg, "__version__", "unknown")

STATUS_MAP = {
    "unmitigated": "fresh",
    "mitigated": "tested",
    "filled": "partially_mitigated",
    "invalidated": "mitigated",
}


def candles_to_bars(candles):
    """Convert ccxt-style OHLCV rows into engine bar dicts.

    candles: [[timestamp, open, high, low, close, volume], ...]
    Timestamps in milliseconds (ccxt default) are auto-detected and converted
    to seconds so multi-timeframe bucketing works correctly.
    """
    bars = []
    for c in candles:
        ts = float(c[0])
        if ts > 1e12:  # milliseconds -> seconds
            ts /= 1000.0
        bars.append({
            "time": ts,
            "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]),
            "volume": float(c[5]) if len(c) > 5 else 0.0,
        })
    return bars


def _map_fvg(f: dict, price: float) -> dict:
    """Engine FVG dict -> confluence-ready dict (skill's schema + extras)."""
    mid = f["midpoint"]
    return {
        "type": "bull" if f["direction"] == "bullish" else "bear",
        "top": round(f["top"], 8),
        "bottom": round(f["bottom"], 8),
        "mid": round(mid, 8),
        "gap_pct": round(f["size_pct"], 4),
        "status": STATUS_MAP.get(f["state"], f["state"]),
        "dist_pct": round(abs(price - mid) / price * 100, 3) if price else None,
        # enriched fields the original detector never had:
        "state": f["state"],
        "atr_multiple": f["atr_multiple"],
        "source_tf_minutes": f["source_tf_minutes"],
        "is_inverse": f["is_inverse"],
    }


def analyze_for_confluence(candles_or_bars, config=None, near_pct: float = 3.0) -> dict:
    """Run the engine and return a confluence-ready FVG view.

    Returns a dict with: price, bias, fvg_score (-1/0/+1 for the confluence
    model's FVG leg), nearest_fvg (nearest ACTIVE gap within `near_pct`, or
    None), active_fvg_count, and the full mapped `fvgs` list.
    """
    bars = candles_or_bars
    if bars and isinstance(bars[0], (list, tuple)):
        bars = candles_to_bars(candles_or_bars)
    res = fvg.analyze(bars, config or {})

    price = res["last_price"]
    all_fvgs = list(res["fvgs"]) + list(res["mtf_fvgs"])
    mapped = [_map_fvg(f, price) for f in all_fvgs]
    active = [m for m in mapped if m["status"] in ("fresh", "tested")]

    nearest = None
    if active and price:
        cand = min(active, key=lambda m: m["dist_pct"])
        if cand["dist_pct"] <= near_pct:
            nearest = cand

    bias = res["zones"]["bias"]
    fvg_score = {"bullish": 1, "bearish": -1, "neutral": 0}.get(bias, 0)

    return {
        "price": price,
        "bias": bias,
        "bias_reason": res["zones"]["bias_reason"],
        "fvg_score": fvg_score,
        "nearest_fvg": nearest,
        "active_fvg_count": len(active),
        "base_timeframe_minutes": res["base_timeframe_minutes"],
        "fvgs": mapped,
        "engine_version": FVG_ENGINE_VERSION,
    }
