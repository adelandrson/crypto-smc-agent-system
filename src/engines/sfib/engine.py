"""Top-level swing/Fibonacci/structure analysis (public entry point)."""

from __future__ import annotations

from typing import List, Optional

from .core import normalize_bars, compute_atr
from .swings import significant_swings
from .fib import fib_for_leg, OTE
from .structure import classify
from .ob import detect_order_blocks

DEFAULTS = {"depth": 10, "atr_period": 14, "atr_mult": 0.5}

# Per-timeframe presets calibrated on real Binance data (BTC/ETH/SOL/BNB).
# Finding: `depth` is the dominant control (confirmation lag = depth bars);
# `atr_mult` is nearly inert once fractal depth is set (kept as a light guard).
# Chosen by responsiveness-vs-significance trade-off, not by chasing the
# noise-level golden-zone metric. See scripts/calibrate_fib.py & CALIBRATION.md.
PRESETS = {
    "5m": {"depth": 5, "atr_mult": 0.5},
    "15m": {"depth": 8, "atr_mult": 0.5},
    "1h": {"depth": 10, "atr_mult": 0.5},
    "4h": {"depth": 10, "atr_mult": 0.5},
    "1d": {"depth": 10, "atr_mult": 0.5},
}


def preset_for(timeframe: Optional[str]) -> dict:
    """Recommended {depth, atr_mult} for a timeframe (falls back to defaults)."""
    p = PRESETS.get((timeframe or "").lower())
    return dict(p) if p else {"depth": DEFAULTS["depth"], "atr_mult": DEFAULTS["atr_mult"]}


def _cfg(config: Optional[dict]) -> dict:
    c = dict(DEFAULTS)
    for k, v in (config or {}).items():
        if k in c and v is not None:
            c[k] = v
    return c


def _alt_legs(swings, atr, price, max_alts=2):
    """Previous alternating legs (older than the active one), ranked by recency."""
    out = []
    # active leg uses swings[-2..-1]; alternatives use earlier consecutive pairs
    for k in range(len(swings) - 2, 0, -1):
        O, E = swings[k - 1].price, swings[k].price
        a = atr[swings[k].index] if swings[k].index < len(atr) else (atr[-1] if atr else 0.0)
        size_atr = abs(E - O) / a if a else None
        out.append({
            "origin_index": swings[k - 1].index,
            "extreme_index": swings[k].index,
            "direction": "up" if E > O else "down",
            "range": round(abs(E - O), 8),
            "size_atr": round(size_atr, 3) if size_atr else None,
            "fib": fib_for_leg(O, E, price),
        })
        if len(out) >= max_alts:
            break
    return out


def analyze(bars_input, config: Optional[dict] = None) -> dict:
    cfg = _cfg(config)
    bars = normalize_bars(bars_input)
    if len(bars) < 2 * cfg["depth"] + 3:
        return {"ok": False, "error": "not enough bars for swing detection",
                "need": 2 * cfg["depth"] + 3, "got": len(bars)}
    atr = compute_atr(bars, cfg["atr_period"])
    swings = significant_swings(bars, atr, cfg["depth"], cfg["atr_mult"])
    price = bars[-1].close

    if len(swings) < 2:
        return {"ok": False, "error": "no significant swing leg found",
                "config": cfg, "swing_count": len(swings)}

    O, E = swings[-2].price, swings[-1].price
    fib = fib_for_leg(O, E, price)
    struct = classify(swings, price)
    order_blocks = detect_order_blocks(bars, swings)

    # Fib bias leg for confluence: price in OTE aligned with the active leg
    fib_score = 0
    if OTE[0] <= fib["retracement_ratio_now"] <= OTE[1]:
        fib_score = 1 if fib["direction"] == "up" else -1

    # OB retest: price back at a fresh OB aligned with the active leg (A+ booster)
    ob_retest = None
    if order_blocks:
        from .ob import retest as _retest
        direction = 1 if fib["direction"] == "up" else -1
        ob_retest = _retest(price, direction, order_blocks)

    # Liquidity sweep / EQH-EQL (stop-hunt) — booster A+ (entry SMC bagus terjadi SETELAH sweep)
    from .sweep import detect_sweep, find_liquidity_pools
    _tol = cfg.get("sweep_tol_mult", 0.15) * (atr[-1] if atr else 0.0)
    liquidity_sweep = detect_sweep(bars, swings, atr,
                                   tol_mult=cfg.get("sweep_tol_mult", 0.15),
                                   lookback=cfg.get("sweep_lookback", 3))
    liquidity_pools = find_liquidity_pools(swings, _tol if _tol > 0 else 0.001 * price)
    # Fib extension = target proyeksi di luar E (penempatan TP struktur-based)
    fib_extensions = sorted(fib.get("extensions", {}).values())

    return {
        "ok": True,
        "bar_count": len(bars),
        "last_price": price,
        "config": cfg,
        "structure": struct,
        "order_blocks": order_blocks,
        "ob_retest": ob_retest,
        "liquidity_sweep": liquidity_sweep,
        "liquidity_pools": liquidity_pools,   # {eqh:[...], eql:[...]} — target TP struktur
        "fib_extensions": fib_extensions,     # level proyeksi Fib (target TP)
        "active_leg": {
            "origin_index": swings[-2].index,
            "origin_time": swings[-2].time,
            "extreme_index": swings[-1].index,
            "extreme_time": swings[-1].time,
            "fib": fib,
        },
        "fib_score": fib_score,         # +1/-1/0 for the confluence model
        "in_ote": fib["in_ote"],
        "in_golden_pocket": fib["in_golden_pocket"],
        "zone": fib["zone"],            # premium / discount / equilibrium
        "swings": [p.to_dict() for p in swings[-8:]],
        "alt_legs": _alt_legs(swings, atr, price),
    }
