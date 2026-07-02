"""Decision engine — port dari paper/engine.py `decide()` (sumber metodologi), TAK diubah:
gerbang confluence (|full_score|>=2), disiplin zona (long=discount/short=premium), semua SKIP
filter (ranging/volume anomaly/LSR kontrarian), structure-SL, TP bertahap. SATU-SATUNYA
"penyesuaian" (sesuai instruksi user): leverage kini dipilih dalam RANGE per-gaya BARU
(scalp 15-30x, swing 8-15x, beda dari default folder sumber) + margin-cap ditambahkan,
mengikuti pola money-management crypto-trader-agent-system. Risk% & formula sizing/SL/TP
tak tersentuh.
"""
from __future__ import annotations

from src.smc.confluence import analyze_confluence, fib_preset
from src.smc.risk import position_size, structure_sl, tp_targets

# ── konfigurasi per-gaya (penyesuaian eksplisit user, lihat plan) ──
GROUPS = {
    "scalp": {
        "tf": "5m", "mtf_minutes": [15, 60], "mode": "scalp",
        "lev_min": 15, "lev_max": 30, "stop_ref": (0.003, 0.02),   # SL rapat->lev_max, lebar->lev_min
        "risk_pct": 0.01, "margin_cap": 0.03, "max_open": 4,
        "fvg_config": {"threshold_mode": "atr", "min_atr_mult": 0.25},
        "candle_limit": 220,
    },
    "swing": {
        "tf": "4h", "mtf_minutes": [1440], "mode": "swing",
        "lev_min": 8, "lev_max": 15, "stop_ref": (0.01, 0.08),
        "risk_pct": 0.02, "margin_cap": 0.07, "max_open": 4,
        "fvg_config": {"threshold_mode": "atr", "min_atr_mult": 0.25},
        "candle_limit": 220,
    },
}


def _choose_leverage(cfg: dict, stop_dist_frac: float) -> int:
    """Leverage dalam range gaya (BARU: scalp 15-30x / swing 8-15x) — makin rapat SL, makin
    dekat ke lev_max (margin makin efisien utk risiko unit yg sama). Ini TIDAK menaikkan
    risiko per-trade (risk% x equity tetap penentu qty) — leverage cuma menentukan margin
    yg dikomit. Diklem ke [lev_min, lev_max]."""
    lo, hi = cfg["lev_min"], cfg["lev_max"]
    if stop_dist_frac <= 0:
        return lo
    ref_tight, ref_wide = cfg.get("stop_ref", (0.003, 0.03))
    frac = max(0.0, min(1.0, (ref_wide - stop_dist_frac) / max(1e-9, ref_wide - ref_tight)))
    return round(lo + frac * (hi - lo))


def decide(symbol: str, candles: list, fr_score: int, oi_score: int, equity: float,
           cfg: dict, lsr_score: int = 0) -> dict:
    """Pure decision (tanpa network/side-effect). Return action dict — 'open' atau 'skip'."""
    c = analyze_confluence(candles, fvg_config=cfg["fvg_config"], fib_config=fib_preset(cfg["tf"]),
                           fr_score=fr_score, oi_score=oi_score)
    if not c["full_strong"]:
        return {"action": "skip", "reason": "no full_strong signal", "confluence": c}
    direction = 1 if c["full_score"] > 0 else -1
    # momentum/volatilitas/volume filter (SKIP kode-enforce, TAK diubah dari sumber)
    if c.get("ranging"):
        return {"action": "skip", "reason": "vol_state=ranging (no trend)", "confluence": c}
    if c.get("volume_ok") is False:
        return {"action": "skip", "reason": "volume anomaly (below average)", "confluence": c}
    if lsr_score != 0 and lsr_score != direction:
        return {"action": "skip", "reason": f"lsr_score {lsr_score} against direction {direction}", "confluence": c}
    # disiplin zona: long hanya discount, short hanya premium (TAK diubah)
    if (direction > 0 and c["zone"] != "discount") or (direction < 0 and c["zone"] != "premium"):
        return {"action": "skip", "reason": f"zone {c['zone']} blocks {direction}", "confluence": c}
    entry = c["price"]
    sl = structure_sl(direction, entry, c["nearest_fvg"], c["structure"])
    if (direction > 0 and sl >= entry) or (direction < 0 and sl <= entry):
        return {"action": "skip", "reason": "invalid SL vs entry", "confluence": c}
    stop_dist = abs(entry - sl) / entry
    lev = _choose_leverage(cfg, stop_dist)
    qty = position_size(equity, cfg["risk_pct"], entry, sl)   # sizing dari risk% (TAK diubah)
    notional = qty * entry
    max_margin = cfg["margin_cap"] * equity
    margin = notional / lev if lev else notional
    if margin > max_margin:
        # margin-cap menang: notional (& risk_usd) menyusut di bawah target risk% -- lebih
        # KETAT, bukan longgar (mirip MARGIN_CAP crypto-trader-agent-system)
        notional = max_margin * lev
        qty = notional / entry if entry else 0
    if qty <= 0:
        return {"action": "skip", "reason": "qty<=0", "confluence": c}
    risk_usd = qty * abs(entry - sl)
    return {"action": "open", "symbol": symbol, "direction": direction, "entry": entry, "sl": sl,
            "qty": qty, "leverage": lev, "margin_usd": round(notional / lev, 2) if lev else round(notional, 2),
            "risk_usd": round(risk_usd, 4), "risk_frac": round(risk_usd / equity, 5) if equity else 0.0,
            "tps": tp_targets(direction, entry, sl, mode=cfg.get("mode", "scalp")),
            "full_score": c["full_score"], "zone": c["zone"], "high_confluence": c["high_confluence"],
            "fr_score": c["fr_score"], "oi_score": c["oi_score"], "lsr_score": lsr_score}
