"""Unified momentum/volatility/volume analysis (public entry point).

Returns one dict the confluence layer consumes:
  rsi, adx, vol_state (trending|breakout|ranging), vol_state_reason,
  atr_percentile, bb_width_pct, volume_z, volume_ok,
  rsi_divergence {kind, momentum_score}, momentum_score.

vol_state replaces the premium "LuxAlgo Volatility State" with a free
deterministic classifier:
  adx >= 25                       -> trending
  atr_percentile >= 0.8           -> breakout  (volatility expanding)
  adx < 20 and bb_width low       -> ranging   (SKIP scalp per SKILL A5)
  else                            -> mixed
"""
from __future__ import annotations

from typing import Optional

from .core import _to_arrays, rsi as _rsi, adx as _adx, atr_percentile as _atr_pct, \
    bollinger_width as _bb, volume_zscore as _vz
from .divergence import detect as _detect_div

DEFAULTS = {"rsi_period": 14, "adx_period": 14, "bb_period": 20, "bb_std": 2.0,
            "vol_period": 20, "atr_lookback": 100, "pivot_depth": 5,
            "adx_trending": 25.0, "adx_ranging": 20.0, "atr_breakout_pct": 0.8,
            "volume_ok_min_z": 0.0}


def _cfg(config: Optional[dict]) -> dict:
    c = dict(DEFAULTS)
    for k, v in (config or {}).items():
        if k in c and v is not None:
            c[k] = v
    return c


def analyze(candles, config: Optional[dict] = None) -> dict:
    cfg = _cfg(config)
    if len(candles) < max(cfg["rsi_period"], cfg["bb_period"], cfg["adx_period"]) * 2 + 5:
        return {"ok": False, "error": "not enough candles for momentum analysis",
                "got": len(candles)}
    highs, lows, closes, volumes = _to_arrays(candles)
    rsi_s = _rsi(closes, cfg["rsi_period"])
    adx_d = _adx(highs, lows, closes, cfg["adx_period"])
    atr_pct = _atr_pct(highs, lows, closes, cfg["adx_period"], cfg["atr_lookback"])
    bb = _bb(closes, cfg["bb_period"], cfg["bb_std"])
    vz = _vz(volumes, cfg["vol_period"])
    div = _detect_div(rsi_s, highs, lows, cfg["pivot_depth"])

    last_rsi = rsi_s[-1]
    last_adx = adx_d["adx"][-1]
    last_pdi = adx_d["plus_di"][-1]
    last_mdi = adx_d["minus_di"][-1]

    # volatility/trend-strength classifier
    if last_adx >= cfg["adx_trending"]:
        vol_state, reason = "trending", f"ADX {last_adx:.1f} >= {cfg['adx_trending']}"
    elif atr_pct >= cfg["atr_breakout_pct"]:
        vol_state, reason = "breakout", f"ATR pct {atr_pct:.2f} >= {cfg['atr_breakout_pct']}"
    elif last_adx < cfg["adx_ranging"] and bb["width_pct"] > 0:
        vol_state, reason = "ranging", f"ADX {last_adx:.1f} < {cfg['adx_ranging']} (squeeze)"
    else:
        vol_state, reason = "mixed", f"ADX {last_adx:.1f}, ATR pct {atr_pct:.2f}"

    volume_ok = vz >= cfg["volume_ok_min_z"]

    return {
        "ok": True,
        "rsi": round(last_rsi, 2),
        "adx": round(last_adx, 2),
        "plus_di": round(last_pdi, 2),
        "minus_di": round(last_mdi, 2),
        "atr_percentile": atr_pct,
        "bb_width_pct": bb["width_pct"],
        "vol_state": vol_state,
        "vol_state_reason": reason,
        "ranging": vol_state == "ranging",
        "volume_z": vz,
        "volume_ok": volume_ok,
        "rsi_divergence": div["kind"],
        "momentum_score": div["momentum_score"],
        "divergence_pivots": div["pivot_indices"],
    }
