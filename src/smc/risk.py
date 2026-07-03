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


FUNDING_INTERVAL_H = 8.0   # perp: funding di-settle tiap 8 jam (00/08/16 UTC)


def funding_fee(notional: float, funding_rate, direction: int, hours: float) -> float:
    """Biaya funding perp (aproksimasi dry-run, akrual proporsional per periode 8 jam) — cermin
    paper/risk.py sumber. LONG bayar saat rate>0 (SHORT terima). Return PnL funding (neg=biaya)."""
    if not funding_rate or hours <= 0 or not notional:
        return 0.0
    return -direction * abs(notional) * funding_rate * (hours / FUNDING_INTERVAL_H)


_EST_FUNDING_PERIODS = {"scalp": 1, "swing": 6}   # estimasi periode 8j yg dilewati selama hold


def funding_gate(direction: int, funding_rate, entry: float, tp_price, mode: str = "swing",
                 max_pay_8h: float = 0.001, max_profit_frac: float = 0.35, max_abs_8h: float = 0.003):
    """Gerbang funding — cermin paper/risk.py sumber. Return (ok: bool, reason: str) — reason='' bila lolos.
    (0) EKSTREM dua-arah: |funding| > max_abs_8h (0.3%/8j) -> tolak koin ini SAMA SEKALI (pasar tak
    stabil/manipulatif, mis. LAB 0.76%). (1) bayar > max_pay_8h -> tolak. (2) bayar estimasi > 35%
    target profit -> tolak. Funding diterima & tak ekstrem tak pernah memblokir."""
    rate = funding_rate or 0.0
    if abs(rate) > max_abs_8h:
        return False, f"funding EKSTREM {abs(rate)*100:.2f}%/8j — pasar tak stabil, koin dihindari"
    pay_rate = max(0.0, direction * rate)
    if pay_rate <= 0:
        return True, ""
    if pay_rate > max_pay_8h:
        return False, f"funding bayar {pay_rate*100:.3f}%/8j di atas batas — menggerus PnL"
    if tp_price and entry:
        profit_frac = abs(tp_price - entry) / entry
        if profit_frac > 0:
            frac = (pay_rate * _EST_FUNDING_PERIODS.get(mode, 4)) / profit_frac
            if frac > max_profit_frac:
                return False, f"funding bayar {pay_rate*100:.3f}%/8j makan ~{frac*100:.0f}% target profit"
    return True, ""


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


def structure_tp_prices(direction: int, entry: float, sl: float, order_blocks=None,
                        liquidity_pools=None, fib_extensions=None, n: int = 1,
                        min_r: float = 1.0) -> list:
    """Penempatan LEVEL TP dari STRUKTUR (jumlah TP dipisah dari DI MANA). Kandidat sisi profit:
    pool likuiditas LAWAN (long→EQH / short→EQL), opposing OB (long→bearish / short→bullish),
    Fib extension. Filter >= min_r*R, urut mendekat→menjauh, dedupe ~0.1R. Kurang → fallback R-multiple."""
    R = abs(entry - sl) or (entry * 0.005)
    cands: list = []
    if liquidity_pools:
        cands += list(liquidity_pools.get("eqh" if direction > 0 else "eql", []) or [])
    for ob in (order_blocks or []):
        if direction > 0 and ob.get("type") == "bear" and ob.get("bottom") is not None:
            cands.append(ob["bottom"])
        elif direction < 0 and ob.get("type") == "bull" and ob.get("top") is not None:
            cands.append(ob["top"])
    if fib_extensions:
        cands += [x for x in fib_extensions if x is not None]
    floor = entry + direction * min_r * R
    valid = sorted({round(float(x), 10) for x in cands
                    if (direction > 0 and x >= floor) or (direction < 0 and x <= floor)},
                   reverse=(direction < 0))
    out: list = []
    for x in valid:
        if not out or abs(x - out[-1]) >= 0.1 * R:
            out.append(x)
        if len(out) >= n:
            break
    fb = [2.0, 3.5, 5.0, 7.0]
    while len(out) < n:
        m = fb[min(len(out), len(fb) - 1)]
        lvl = round(entry + direction * m * R, 10)
        if out and ((direction > 0 and lvl <= out[-1]) or (direction < 0 and lvl >= out[-1])):
            lvl = round(out[-1] + direction * R, 10)
        out.append(lvl)
    return out[:n]


def tp_targets(direction: int, entry: float, sl: float, mode: str = "scalp", levels: int = 2,
               prices: list | None = None):
    """Rencana take-profit. JUMLAH level (mode/levels) dipisah dari PENEMPATAN level (`prices`).

    mode='scalp' — MAIN CEPAT: SATU TP tutup 100%, tanpa SL-evolution.
    mode='swing' — TP BERKALA 1..3 level (fixed, sum=100%); SL evolution BE->lock-TP1.
    `prices` (opsional) = harga TP dari struktur (structure_tp_prices); None → R-multiple.
    """
    R = abs(entry - sl)
    if mode == "scalp":
        plan = [("TP1", 2.0, 1.00, {})]
    else:  # swing
        plan = _SWING_LADDERS[levels if levels in _SWING_LADDERS else 2]
    out = []
    for i, (lbl, mult, frac, sa) in enumerate(plan):
        px = prices[i] if (prices and i < len(prices) and prices[i] is not None) \
            else entry + direction * mult * R
        out.append({"label": lbl, "price": px, "frac": frac, "filled": False, "sl_after": sa})
    return out
