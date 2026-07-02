"""Unified confluence: FVG (engine) × Fibonacci/structure (swing-fib engine).

Both FVG and Fib come from their single-authority engines (no eyeballing). This
layer computes their agreement and — the key signal — whether the Fibonacci
golden pocket / ICT OTE band OVERLAPS an active (fresh/tested) FVG zone, which
ICT theory flags as a high-probability entry.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .fvg_adapter import analyze_for_confluence  # single FVG authority

# path adapted to this repo's layout: src/smc/ (this file) -> src/engines/{sfib,ind}
_SFIB = Path(__file__).resolve().parents[1] / "engines" / "sfib"
_IND = Path(__file__).resolve().parents[1] / "engines" / "ind"


def _load_sfib():
    if "sfib" in sys.modules:
        return sys.modules["sfib"]
    spec = importlib.util.spec_from_file_location(
        "sfib", _SFIB / "__init__.py", submodule_search_locations=[str(_SFIB)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sfib"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_ind():
    if "ind" in sys.modules:
        return sys.modules["ind"]
    spec = importlib.util.spec_from_file_location(
        "ind", _IND / "__init__.py", submodule_search_locations=[str(_IND)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ind"] = mod
    spec.loader.exec_module(mod)
    return mod


sfib = _load_sfib()
ind = _load_ind()


def fib_preset(timeframe):
    """Calibrated {depth, atr_mult} for a timeframe (from the swing-fib engine)."""
    return sfib.preset_for(timeframe)


def _overlap(a_lo, a_hi, b_lo, b_hi) -> bool:
    return max(a_lo, b_lo) <= min(a_hi, b_hi)


def analyze_confluence(candles_or_bars, fvg_config=None, fib_config=None,
                       fr_score=0, oi_score=0, ind_config=None) -> dict:
    """Combine FVG + Fib/structure into one confluence view for a symbol's bars.

    `fr_score`/`oi_score` (each -1/0/+1) are the optional Open-Interest / Funding
    legs (computed live by exchanges.aggregate_sentiment + an OI-change tracker).
    With both 0 (default), `full_score` == `analysis_score` (FVG+Fib only).
    """
    fvg = analyze_for_confluence(candles_or_bars, config=fvg_config)
    fib = sfib.analyze(candles_or_bars, fib_config or {})

    price = fvg["price"]
    fvg_score = fvg["fvg_score"]
    fib_score = 0
    fib_dir = zone = structure = None
    in_ote = in_gp = False
    overlaps = []

    if fib.get("ok"):
        f = fib["active_leg"]["fib"]
        fib_score = fib["fib_score"]
        fib_dir = f["direction"]
        zone = f["zone"]
        in_ote = f["in_ote"]
        in_gp = f["in_golden_pocket"]
        structure = fib["structure"]
        gp = sorted(f["golden_pocket"])
        ote = sorted(f["ote_zone"])
        for z in fvg["fvgs"]:
            if z["status"] not in ("fresh", "tested"):
                continue
            for band_name, band in (("golden_pocket", gp), ("ote", ote)):
                if _overlap(z["bottom"], z["top"], band[0], band[1]):
                    overlaps.append({"band": band_name, "fvg_type": z["type"],
                                     "fvg_zone": [z["bottom"], z["top"]],
                                     "fvg_status": z["status"],
                                     "source_tf_minutes": z.get("source_tf_minutes")})

    # combined sub-score from the two price legs (FVG + Fib)
    analysis_score = max(-2, min(2, fvg_score + fib_score))
    # full confluence incl. Open-Interest + Funding legs (range -4..+4)
    full_score = max(-4, min(4, fvg_score + fib_score + (fr_score or 0) + (oi_score or 0)))
    # A+ flag: Fib zone overlaps an active FVG AND both price legs agree
    high_confluence = bool(overlaps) and fvg_score != 0 and fvg_score == fib_score

    # ---- momentum / volatility / volume layer (confirmation + filters) ----
    # momentum_score (RSI divergence, +/-1) confirms direction; vol_state/volume
    # are SKIP filters (ranging market / volume anomaly). OB retest is an A+
    # booster like the Fib x FVG overlap. These do NOT change full_score (the
    # backtested -4..+4 primary stays the actionable threshold).
    ob_retest = fib.get("ob_retest") if fib.get("ok") else None
    liquidity_sweep = fib.get("liquidity_sweep") if fib.get("ok") else None
    try:
        mom = ind.analyze(candles_or_bars, ind_config or {})
    except Exception:  # noqa: BLE001
        mom = {"ok": False}
    momentum_score = mom.get("momentum_score", 0) if mom.get("ok") else 0
    momentum_quality = mom.get("rsi_divergence_quality", 0) if mom.get("ok") else 0
    mtf_div = mom.get("mtf_divergence") if mom.get("ok") else None
    vol_state = mom.get("vol_state") if mom.get("ok") else None
    ranging = mom.get("ranging", False) if mom.get("ok") else False
    volume_ok = mom.get("volume_ok", True) if mom.get("ok") else True
    # A+ extended: overlap Fib×FVG OR OB retest OR liquidity sweep OR MTF divergence (selaras arah)
    ob_boost = ob_retest is not None and fvg_score != 0 and fvg_score == fib_score
    sweep_boost = bool(liquidity_sweep and liquidity_sweep.get("swept") and fvg_score != 0
                       and liquidity_sweep.get("direction") == (1 if fvg_score > 0 else -1))
    mtf_boost = bool(mtf_div and mtf_div.get("mtf_score") and fvg_score != 0
                     and mtf_div.get("mtf_score") == (1 if fvg_score > 0 else -1))
    high_confluence = high_confluence or ob_boost or sweep_boost or mtf_boost
    # confirmed = full_strong AND momentum aligns AND not ranging AND volume ok
    confirmed = (abs(full_score) >= 2 and momentum_score != 0
                 and momentum_score == (1 if full_score > 0 else -1)
                 and not ranging and volume_ok)

    return {
        "price": price,
        "fvg_score": fvg_score,
        "fvg_bias": fvg["bias"],
        "fib_score": fib_score,
        "fib_direction": fib_dir,
        "fr_score": fr_score or 0,
        "oi_score": oi_score or 0,
        "zone": zone,                  # premium / discount / equilibrium
        "in_ote": in_ote,
        "in_golden_pocket": in_gp,
        "structure": structure,        # trend + BOS/CHoCH
        "order_blocks": fib.get("order_blocks") if fib.get("ok") else [],
        "ob_retest": ob_retest,
        "liquidity_sweep": liquidity_sweep,   # EQH/EQL stop-hunt (booster A+ bila selaras)
        "liquidity_pools": fib.get("liquidity_pools") if fib.get("ok") else None,  # target TP struktur
        "fib_extensions": fib.get("fib_extensions") if fib.get("ok") else None,    # target TP struktur
        "analysis_score": analysis_score,     # FVG + Fib (range -2..+2)
        "full_score": full_score,             # + OI + FR (range -4..+4)
        "full_strong": abs(full_score) >= 2,  # multi-leg agreement (actionable)
        "fib_fvg_overlaps": overlaps,         # golden-pocket/OTE × active FVG
        "high_confluence": high_confluence,   # A+ setup flag (now incl. OB retest)
        "momentum_score": momentum_score,     # RSI divergence leg (confirmation)
        "momentum_quality": momentum_quality,  # 0-100 kualitas divergensi RSI
        "mtf_divergence": mtf_div,             # konfirmasi divergensi RSI lintas timeframe
        "vol_state": vol_state,               # trending/breakout/ranging/mixed
        "atr_percentile": mom.get("atr_percentile") if mom.get("ok") else None,  # 0..1 (jumlah TP swing)
        "ranging": ranging,                   # SKIP filter (scalp)
        "volume_ok": volume_ok,               # SKIP filter (volume anomaly)
        "volume_z": mom.get("volume_z") if mom.get("ok") else None,
        "rsi": mom.get("rsi") if mom.get("ok") else None,
        "adx": mom.get("adx") if mom.get("ok") else None,
        "confirmed": confirmed,               # full_strong + momentum + filters pass
        "nearest_fvg": fvg["nearest_fvg"],
        "active_fvg_count": fvg["active_fvg_count"],
    }
