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
                 max_pay_8h: float = 0.001, max_profit_frac: float = 0.35):
    """Gerbang funding — cermin paper/risk.py sumber. Return (ok: bool, reason: str). HANYA blok sisi
    yg MEMBAYAR funding tinggi (long saat rate>0/short saat rate<0); yg MENERIMA selalu lolos.
    (1) bayar > max_pay_8h -> tolak. (2) bayar estimasi > 35% target -> tolak.
    (Penghindaran koin PUMP-manipulatif ditangani lapisan terpisah: pump_guard.)"""
    rate = funding_rate or 0.0
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


def _dist_short(dc, win, pre, tp, wick_min, sideways_band, local_mult, min_rr, _med):
    """Cek DISTRIBUSI FINAL + entry di satu TF `dc`. Return dict entry bila valid RR>=min_rr, else None.
    Distribusi final: (1) sideways di atas (high berkelompok) + >=2 wick-reject atas; (2) LOCAL-peak
    volume (lebih tinggi dari tetangga kiri-kanan, bukan global-max) pd candle wick-reject.
    SL=wick tertinggi SIDEWAYS (local). Entry: MARKET di harga kini bila RR>=min_rr; jika sudah di
    bawah floor RR-1:3 -> None (telat, skip TF ini)."""
    if not dc or len(dc) < max(10, win):
        return None
    o = [x[1] for x in dc]; h = [x[2] for x in dc]; l = [x[3] for x in dc]
    c = [x[4] for x in dc]; v = [x[5] for x in dc]
    wI = [i for i in range(len(dc) - win, len(dc)) if i >= 0]
    if len(wI) < 5:
        return None

    def uw(i):
        r = h[i] - l[i]
        return (h[i] - max(o[i], c[i])) / r if r > 0 else 0.0

    wh = [h[i] for i in wI]
    sideways = (max(wh) - min(wh)) / max(wh) < sideways_band if max(wh) > 0 else False
    rej = sum(1 for i in wI if uw(i) >= wick_min)
    vm = _med([v[i] for i in wI])
    local_peak = any(v[wI[j]] > v[wI[j - 1]] and v[wI[j]] > v[wI[j + 1]] and v[wI[j]] >= vm * local_mult
                     and uw(wI[j]) >= wick_min for j in range(1, len(wI) - 1))
    if not (sideways and rej >= 2 and local_peak):
        return None
    sl = max(wh)                                    # SL = wick TERTINGGI saat SIDEWAYS (local)
    cur = c[-1]
    if not (tp < cur < sl):                         # harga harus di antara TP & SL
        return None
    floor = (min_rr * sl + tp) / (min_rr + 1)       # entry TERENDAH utk RR>=min_rr (short)
    if cur < floor:                                 # sudah di bawah floor -> TELAT, skip TF ini
        return None
    rr = (cur - tp) / (sl - cur) if sl > cur else 0.0
    return {"sl": sl, "entry": cur, "order": "market", "rr": rr, "sideways_high": sl}


def pump_guard(candles, tier, dist_candles=None, dist_win: int = 18, dist_tfs=None, min_rr: float = 2.5, spike_min: float = 15.0, mcap=None,
               mcap_ceiling: float = 5e9, pump_min: float = 0.30, wick_min: float = 0.45,
               base_quantile: float = 0.7, block_above: float = 0.15, sideways_win: int = 8,
               sideways_band: float = 0.12, local_mult: float = 1.15, tp_margin: float = 0.01) -> dict:
    """Deteksi 'crime pump/dump' koin TIER RENDAH (A/B/C) — deterministik, MULTI-TIMEFRAME.

    PUMP-MACRO (di `candles`, ~30 hari): baseline volume kecil-konsisten -> SPIKE volume angkat harga
    (artifisial) -> BLOKIR LONG selama harga masih di puncak.

    DISTRIBUSI FINAL + SHORT — dinilai lintas TF (`dist_tfs`, urut kasar->halus mis. 1D>4h>1h>15m)
    karena crime-pump ada yang lambat (LAB/Rave/OM) & sangat cepat (Manta): TF halus menangkap yang
    cepat lebih awal. Untuk tiap TF: (1) sideways-top + >=2 wick-reject; (2) LOCAL-peak volume (bukan
    global-max) wick-reject. SL = wick tertinggi SIDEWAYS (local). TP 100% = ~tp_margin di atas pra-pump.
    ENTRY: MARKET di harga kini bila RR>=`min_rr` (1:3); bila sudah di bawah floor RR-1:3 -> SKIP (telat).
    Ambil TF PERTAMA (dari daftar) yang memberi entry valid.

    Return: is_pump/block_long/short_ok/pre_pump_price/peak_price/short_sl/short_tp/short_entry/
    order_type/dist_tf/rr/pump_pct/reason."""
    out = {"is_pump": False, "block_long": False, "short_ok": False, "pre_pump_price": None,
           "peak_price": None, "short_sl": None, "short_tp": None, "short_entry": None,
           "order_type": None, "dist_tf": None, "rr": None, "pump_pct": None, "spike_ratio": None, "reason": ""}
    if tier not in ("A", "B", "C") or not candles or len(candles) < 30:
        return out

    def _med(xs):
        s = sorted(xs)
        return s[len(s) // 2] if s else 0.0

    h = [c[2] for c in candles]; cl = [c[4] for c in candles]; v = [c[5] for c in candles]
    dv = [cl[i] * v[i] for i in range(len(candles))]        # $ volume harian (close x base-vol)
    base = _med(sorted(dv)[:max(1, int(len(dv) * base_quantile))])   # baseline $vol tenang (kuantil bawah)
    if base <= 0:
        return out
    spike_ratio = max(dv) / base                            # rasio spike vs baseline 90 hari
    out["spike_ratio"] = round(spike_ratio, 1)
    # GATE VOLUME (riset 90d): rally organik/legit (Pyth/Near/Aave/HBAR) <=~10x; MANIPULASI
    # (Manta/LAB/Rave) >=~30x. spike_ratio < spike_min -> kenaikan WAJAR/organik, BUKAN crime-pump.
    if spike_ratio < spike_min:
        return out
    # GATE MCAP: koin sangat besar sulit dimanipulasi (safety large-cap false-positive)
    if mcap and mcap > mcap_ceiling:
        return out
    spikes = [i for i, x in enumerate(dv) if x > base * spike_min]
    if not spikes:
        return out
    s0 = spikes[0]
    pre = _med(cl[max(0, s0 - 5):s0] or [cl[0]])
    if pre <= 0:
        return out
    peak = max(h[s0:])
    pump_pct = (peak - pre) / pre
    if pump_pct < pump_min:
        return out
    out.update(is_pump=True, pre_pump_price=pre, peak_price=peak, pump_pct=pump_pct)
    tp = pre * (1 + tp_margin)
    out["short_tp"] = tp
    out["block_long"] = cl[-1] > pre * (1 + block_above)      # harga masih di puncak pump -> jangan LONG
    out["reason"] = (f"crime-pump tier {tier}: +{pump_pct * 100:.0f}% dari {pre:.6g} "
                     f"(spike vol {spike_ratio:.0f}x baseline 90h vs threshold {spike_min:.0f}x)")

    tfs = dist_tfs or ([("dist", dist_candles, dist_win)] if dist_candles else
                       [("macro", candles, sideways_win)])
    for name, dc, win in tfs:
        r = _dist_short(dc, win, pre, tp, wick_min, sideways_band, local_mult, min_rr, _med)
        if r:
            out.update(short_ok=True, short_sl=r["sl"], short_entry=r["entry"],
                       order_type=r["order"], dist_tf=name, rr=r["rr"])
            out["reason"] += (f"; DISTRIBUSI FINAL {name} → SHORT {r['order']} @ {r['entry']:.6g} "
                              f"SL {r['sl']:.6g} (local wick) TP {tp:.6g} RR {r['rr']:.1f}")
            break
    return out

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
