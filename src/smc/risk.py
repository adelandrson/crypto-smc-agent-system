"""Risk: structure-based SL, position sizing from risk%, staged TP (R-based).

SL is anchored to structure (swing / FVG zone), never a fixed tick. Size is
derived from risk% and SL distance — leverage never inflates risk per trade.
"""

from __future__ import annotations

import math
from typing import Optional


def fmt_price(p: Optional[float]) -> str:
    """Harga dalam ANGKA UTAMA (significant figures): >=$1000 -> 5 sig-fig, <$1000 -> 4 sig-fig.
    Contoh: 60130, 1630.5, 77.67, 3.055, 0.7239."""
    if p is None:
        return "-"
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "-"
    if math.isnan(p) or p == 0:
        return "0" if p == 0 else "-"
    a = abs(p)
    sig = 5 if a >= 1000 else 4
    d = sig - 1 - math.floor(math.log10(a))
    if d <= 0:
        return str(int(round(p, d)))
    return f"{round(p, d):.{d}f}"


def fmt_num(p):
    """Versi NUMERIK fmt_price: bulatkan ke 5/4 angka utama, return float (bukan string) supaya
    output skill yang dibaca agent LLM ringkas — agent tak lagi menulis 0.33136625999999997."""
    if p is None:
        return None
    try:
        p = float(p)
    except (TypeError, ValueError):
        return p
    if math.isnan(p) or p == 0:
        return p
    a = abs(p)
    sig = 5 if a >= 1000 else 4
    d = sig - 1 - math.floor(math.log10(a))
    return round(p, d)


def limit_entry(direction: int, price: float, nearest_fvg: Optional[dict],
                max_pullback: float = 0.05, min_pullback: float = 0.0015) -> float:
    """Harga LIMIT ORDER (retest zona imbalance) — bukan market di harga kini. SMC entry presisi:
    Long = retest TOP FVG bullish di BAWAH harga; Short = retest BOTTOM FVG bearish di ATAS harga.
    Fallback (tak ada FVG searah): pullback kecil `min_pullback` dari harga kini. Di-clamp
    `max_pullback` supaya limit tak terlalu jauh (realistis terisi, bukan menggantung selamanya)."""
    if price <= 0:
        return price
    if direction > 0:
        zone = nearest_fvg.get("top") if nearest_fvg else None
        cand = zone if (zone and 0 < zone < price) else price * (1 - min_pullback)
        return max(cand, price * (1 - max_pullback))       # tak lebih jauh dari max_pullback
    zone = nearest_fvg.get("bottom") if nearest_fvg else None
    cand = zone if (zone and zone > price) else price * (1 + min_pullback)
    return min(cand, price * (1 + max_pullback))


def position_size(equity: float, risk_pct: float, entry: float, sl: float) -> float:
    """Base-asset qty so that hitting SL loses exactly risk% of equity."""
    if entry <= 0 or sl <= 0:
        return 0.0
    sl_dist = abs(entry - sl) / entry
    if sl_dist <= 0:
        return 0.0
    pos_usd = (equity * risk_pct) / sl_dist
    return pos_usd / entry


def structure_sl(direction: int, entry: float, nearest_fvg: Optional[dict],
                 structure: Optional[dict], buffer: float = 0.002,
                 fallback_pct: float = 0.01) -> float:
    """SL beyond the protecting structure + buffer.

    Long: below the nearest support (FVG bottom / last swing low). Short: above
    the nearest resistance (FVG top / last swing high). Falls back to a fixed %
    if no structure is available.
    """
    cands = []
    if direction > 0:
        if nearest_fvg and nearest_fvg.get("bottom") and nearest_fvg["bottom"] < entry:
            cands.append(nearest_fvg["bottom"])
        if structure and structure.get("last_swing_low") and structure["last_swing_low"] < entry:
            cands.append(structure["last_swing_low"])
        ref = min(cands) if cands else entry * (1 - fallback_pct)
        return ref * (1 - buffer)
    else:
        if nearest_fvg and nearest_fvg.get("top") and nearest_fvg["top"] > entry:
            cands.append(nearest_fvg["top"])
        if structure and structure.get("last_swing_high") and structure["last_swing_high"] > entry:
            cands.append(structure["last_swing_high"])
        ref = max(cands) if cands else entry * (1 + fallback_pct)
        return ref * (1 + buffer)


# Ladder TP berkala SWING per JUMLAH level (1..3, max 3 per spec final user), fraksi total=100%.
# R-multiple = penempatan SEMENTARA; JUMLAH level dipisah dari PENEMPATAN level (spec).
_SWING_LADDERS = {
    1: [("TP1", 3.0, 1.00, {})],
    2: [("TP1", 2.0, 0.50, {"mode": "be"}),
        ("TP2", 4.0, 0.50, {})],
    3: [("TP1", 2.0, 0.40, {"mode": "be"}),
        ("TP2", 3.5, 0.35, {"mode": "lock", "lock_label": "TP1"}),
        ("TP3", 5.0, 0.25, {})],
}


def swing_tp_count(vol_state, atr_percentile=None) -> int:
    """Jumlah TP berkala SWING (1..3) dari VOLATILITY STATE + ATR — deterministik & backtest-able
    (spec final user), BUKAN confluence score (score = kualitas entry, bukan jumlah TP).
    trending/breakout -> harga bisa lari jauh -> 3 level; ranging -> cepat ambil untung -> 1;
    mixed -> 2. ATR sangat rendah (<0.3) turunkan 1 (range sempit, target jauh tak realistis)."""
    if vol_state in ("trending", "breakout"):
        n = 3
    elif vol_state == "ranging":
        n = 1
    else:
        n = 2
    if atr_percentile is not None and atr_percentile < 0.3 and n > 1:
        n -= 1
    return max(1, min(3, n))


def entry_plan(direction: int, price: float, nearest_fvg, in_zone: bool,
               max_pullback: float = 0.05, min_pullback: float = 0.0015):
    """Entry FLEKSIBEL (bukan limit-only/market-only). Harga kini SUDAH di zona entry (FVG/OB/OTE)
    -> MARKET (masuk sekarang, area valid). Belum -> LIMIT di retest zona. Return (entry, order_type)."""
    if in_zone:
        return price, "market"
    return limit_entry(direction, price, nearest_fvg, max_pullback, min_pullback), "limit"


def tp_targets(direction: int, entry: float, sl: float, mode: str = "scalp", levels: int = 2):
    """Rencana take-profit.

    mode='scalp' — MAIN CEPAT: SATU TP tutup 100% di 2R, tanpa TP berkala/SL-evolution.
    mode='swing' — TP BERKALA 1..3 level (fixed, sum=100%) sesuai `levels` (dari swing_tp_count:
        Volatility+ATR); SL evolution BE->lock-TP1 di level antara.
    """
    R = abs(entry - sl)
    if mode == "scalp":
        plan = [("TP1", 2.0, 1.00, {})]                      # 100% sekaligus (main cepat)
    else:  # swing
        plan = _SWING_LADDERS[levels if levels in _SWING_LADDERS else 2]
    return [{"label": lbl, "price": entry + direction * mult * R,
             "frac": frac, "filled": False, "sl_after": sa}
            for lbl, mult, frac, sa in plan]
