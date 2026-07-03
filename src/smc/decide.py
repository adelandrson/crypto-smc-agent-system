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
from src.smc.risk import (entry_plan, funding_gate, position_size, pump_guard, structure_sl,
                          structure_tp_prices, swing_tp_count, tp_targets)

# ── konfigurasi per-gaya (penyesuaian eksplisit user, lihat plan) ──
GROUPS = {
    "scalp": {
        "tf": "5m", "mtf_minutes": [15, 60], "mode": "scalp",
        "lev_min": 15, "lev_max": 30, "stop_ref": (0.003, 0.02),   # SL rapat->lev_max, lebar->lev_min
        # max_open 4->10 (khusus web). Risk/margin per-trade DIKECILKAN agar agregat tetap sehat:
        # 10 x 0.5% = 5% risiko simultan · 10 x 1.5% = 15% margin simultan.
        "risk_pct": 0.005, "margin_cap": 0.015, "max_open": 10,
        "funding_max_pay_8h": 0.001, "funding_max_profit_frac": 0.35, "pump_min_rr": 2.5,
        "pump_spike_min": 15.0, "pump_mcap_ceiling": 5e9,  # gate funding+crime-pump
        "fvg_config": {"threshold_mode": "atr", "min_atr_mult": 0.25},
        "candle_limit": 220, "pending_ttl_h": 6,     # limit order kadaluarsa 6 jam (main cepat)
    },
    "swing": {
        "tf": "4h", "mtf_minutes": [1440], "mode": "swing",
        "lev_min": 8, "lev_max": 15, "stop_ref": (0.01, 0.08),
        # max_open 4->10 (khusus web). 10 x 1% = 10% risiko simultan · 10 x 3.5% = 35% margin simultan.
        "risk_pct": 0.01, "margin_cap": 0.035, "max_open": 10,
        "funding_max_pay_8h": 0.001, "funding_max_profit_frac": 0.35, "pump_min_rr": 2.5,
        "pump_spike_min": 15.0, "pump_mcap_ceiling": 5e9,
        "fvg_config": {"threshold_mode": "atr", "min_atr_mult": 0.25},
        "candle_limit": 220, "pending_ttl_h": 48,     # limit order kadaluarsa 48 jam
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
           cfg: dict, lsr_score: int = 0, funding_rate: float = 0.0, pump=None) -> dict:
    """Pure decision (tanpa network/side-effect). Return action dict — 'open' atau 'skip'."""
    c = analyze_confluence(candles, fvg_config=cfg["fvg_config"], fib_config=fib_preset(cfg["tf"]),
                           fr_score=fr_score, oi_score=oi_score)
    # GERBANG: |full_score| >= min_abs_score (default 2 = metodologi sumber; agen bisa setel [1..4])
    min_score = cfg.get("min_abs_score", 2)
    if abs(c["full_score"]) < min_score:
        return {"action": "skip", "reason": f"|score| {abs(c['full_score'])} < gate {min_score}", "confluence": c}
    direction = 1 if c["full_score"] > 0 else -1
    # LAPIS ANTI CRIME-PUMP (koin tier A ke bawah): blokir LONG di puncak pump artifisial; SHORT hanya
    # bila DISTRIBUSI SELESAI (candle wick-reject bervolume manipulasi tertinggi + harga turun dari puncak)
    if pump and pump.get("is_pump"):
        if direction > 0 and pump.get("block_long"):
            return {"action": "skip", "reason": pump["reason"], "confluence": c}
        if direction < 0 and not pump.get("short_ok"):
            return {"action": "skip", "confluence": c,
                    "reason": "crime-pump tier rendah: SHORT belum terkonfirmasi (distribusi belum selesai)"}
    # filter SKIP (tiap toggle bisa dimatikan agen via config_store; default sesuai sumber)
    if cfg.get("skip_ranging", True) and c.get("ranging"):
        return {"action": "skip", "reason": "vol_state=ranging (no trend)", "confluence": c}
    if cfg.get("skip_volume_anomaly", True) and c.get("volume_ok") is False:
        return {"action": "skip", "reason": "volume anomaly (below average)", "confluence": c}
    if cfg.get("lsr_contrarian", True) and lsr_score != 0 and lsr_score != direction:
        return {"action": "skip", "reason": f"lsr_score {lsr_score} against direction {direction}", "confluence": c}
    # disiplin zona: long hanya discount, short hanya premium (bisa dimatikan agen: enforce_zone)
    if cfg.get("enforce_zone", True) and (
            (direction > 0 and c["zone"] != "discount") or (direction < 0 and c["zone"] != "premium")):
        return {"action": "skip", "reason": f"zone {c['zone']} blocks {direction}", "confluence": c}
    # ENTRY FLEKSIBEL: kalau harga kini SUDAH di zona entry (FVG/OB/OTE) -> MARKET (masuk skrg);
    # kalau belum -> LIMIT di retest zona (arena pasang pending, tunggu pullback).
    fvg = c["nearest_fvg"]
    price = c["price"]
    in_fvg = bool(fvg and fvg.get("bottom") is not None and fvg.get("top") is not None
                  and fvg["bottom"] <= price <= fvg["top"])
    in_zone = in_fvg or c.get("in_ote") or c.get("in_golden_pocket")
    entry, order_type = entry_plan(direction, price, fvg, in_zone,
                                   max_pullback=cfg.get("limit_max_pullback", 0.05),
                                   min_pullback=cfg.get("limit_min_pullback", 0.0015))
    sl = structure_sl(direction, entry, c["nearest_fvg"], c["structure"])
    # SHORT crime-pump: entry/order/SL dari pump_guard (distribusi multi-TF + RR 1:3, SL=local sideways
    # wick), override entry/SL struktur biasa. Entry = MARKET di area sideways bila RR>=1:3, else skip.
    pump_short = bool(pump and pump.get("short_ok") and direction < 0 and pump.get("short_entry"))
    if pump_short:
        entry, order_type, sl = pump["short_entry"], pump["order_type"], pump["short_sl"]
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
    mode = cfg.get("mode", "scalp")
    # JUMLAH TP: SWING 1..3 dari Volatility+ATR; SCALP single. PENEMPATAN level: dari STRUKTUR
    # (pool likuiditas / opposing OB / Fib extension), fallback R-multiple bila struktur kurang.
    levels = swing_tp_count(c.get("vol_state"), c.get("atr_percentile")) if mode == "swing" else 1
    n_tp = 1 if mode == "scalp" else levels
    tp_px = structure_tp_prices(direction, entry, sl, order_blocks=c.get("order_blocks"),
                                liquidity_pools=c.get("liquidity_pools"),
                                fib_extensions=c.get("fib_extensions"), n=n_tp)
    tps = tp_targets(direction, entry, sl, mode=mode, levels=levels, prices=tp_px)
    # SHORT crime-pump: TP TUNGGAL 100% di ~<=1% DI ATAS harga pra-pump (retrace penuh)
    if pump_short and pump.get("short_tp"):
        tps = [{"label": "TP1", "frac": 1.0, "price": pump["short_tp"], "sl_after": {}}]
    # FUNDING GATE: tolak bila funding yg DIBAYAR (adverse) menggerus PnL (hanya sisi yg membayar)
    tp1_px = tps[0].get("price") if tps else None
    ok, freason = funding_gate(
        direction, funding_rate, entry, tp1_px, mode=mode,
        max_pay_8h=cfg.get("funding_max_pay_8h", 0.001),
        max_profit_frac=cfg.get("funding_max_profit_frac", 0.35))
    if not ok:
        return {"action": "skip", "confluence": c, "reason": freason}
    return {"action": "open", "symbol": symbol, "direction": direction, "entry": entry, "sl": sl,
            "order_type": order_type,
            "qty": qty, "leverage": lev, "margin_usd": round(notional / lev, 2) if lev else round(notional, 2),
            "risk_usd": round(risk_usd, 4), "risk_frac": round(risk_usd / equity, 5) if equity else 0.0,
            "tps": tps,
            "full_score": c["full_score"], "zone": c["zone"], "high_confluence": c["high_confluence"],
            "fr_score": c["fr_score"], "oi_score": c["oi_score"], "lsr_score": lsr_score}
