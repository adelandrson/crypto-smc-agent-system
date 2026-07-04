"""Order Block detection — deterministic, derived from the swing sequence.

ICT Order Block = the last opposite-coloured candle before the impulse that drove
a structural break. Bullish OB: last bearish (down-close) candle before an up-leg
that broke structure. Bearish OB: last bullish candle before a down-leg.

This is structure -> lives in the swing-fib engine (single source of truth), next
to BOS/CHoCH and swings. The confluence layer treats an OB retest (price back at
a fresh, unmitigated OB aligned with direction) as an A+ booster, exactly like the
existing Fib-golden-pocket x FVG overlap.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from .core import Bar
from .swings import Pivot


def _is_bullish(b: Bar) -> bool:
    return b.close >= b.open


def _vol_confirmed(bars: Sequence[Bar], idx: int, lookback: int = 20, mult: float = 1.2) -> bool:
    """Apakah volume bar[idx] DI ATAS rata-rata volume LOKAL (`lookback` bar sebelumnya)? Konfirmasi
    permintaan/distribusi institusi — rule user: gerak keluar OB/base wajib bervolume tinggi."""
    if not (0 < idx < len(bars)):
        return False
    vols = [bars[k].volume for k in range(max(0, idx - lookback), idx) if bars[k].volume]
    if not vols:
        return False
    avg = sum(vols) / len(vols)
    return avg > 0 and (bars[idx].volume or 0.0) >= mult * avg


def _count_retests(bars: Sequence[Bar], top: float, bottom: float, start: int) -> int:
    """Berapa kali harga KEMBALI menyentuh zona [bottom,top] setelah `start` (tiap masuk = 1 retest).
    Zona yg sering di-retest & bertahan = OB kuat (rule user: 'sering di-retest dan memantul')."""
    retests = 0
    inside = False
    for i in range(start, len(bars)):
        touch = bars[i].low <= top and bars[i].high >= bottom
        if touch and not inside:
            retests += 1
            inside = True
        elif not touch:
            inside = False
    return retests


def _impulse_has_fvg(bars: Sequence[Bar], a_idx: int, b_idx: int, want_bull: bool) -> bool:
    """Apakah impuls [a_idx..b_idx] meninggalkan FVG (3-candle imbalance) searah? (rule validitas OB:
    OB sah butuh displacement yg meninggalkan FVG — tanpa FVG, OB lemah)."""
    for i in range(max(2, a_idx), min(len(bars), b_idx + 1)):
        if want_bull and bars[i].low > bars[i - 2].high:
            return True
        if (not want_bull) and bars[i].high < bars[i - 2].low:
            return True
    return False


def _leg_broke_structure(swings: Sequence[Pivot], k: int, extreme: Pivot) -> bool:
    """Apakah ekstrem leg MENEMBUS swing sejenis sebelumnya? (BOS — rule: tanpa BOS bukan OB)."""
    for j in range(k - 2, -1, -1):
        if swings[j].kind == extreme.kind:
            return (extreme.price > swings[j].price) if extreme.kind == "high" \
                else (extreme.price < swings[j].price)
    return True                                  # leg pertama -> tak ada acuan, izinkan


def detect_order_blocks(bars: Sequence[Bar], swings: Sequence[Pivot],
                        lookback: int = 10, max_blocks: int = 6,
                        atr: Optional[Sequence[float]] = None,
                        refine_mult: float = 1.5, require_bos: bool = True,
                        require_fvg: bool = True, require_volume: bool = False,
                        vol_mult: float = 1.2) -> List[dict]:
    """Find the most recent VALID OB zones from the swing sequence.

    For each confirmed swing leg (O->E), the OB is the last opposite-colour candle at or before the
    origin pivot, within `lookback` bars. A zone is [low, high] of that candle (full range) — REFINED
    to the candle BODY when the full range is oversized (> refine_mult x ATR).

    VALIDITY (SMC rules): (a) the impulse must BREAK STRUCTURE (BOS) — extreme exceeds the prior
    same-kind swing; without BOS it is just a candle, not an OB. (b) the impulse must leave a
    FAIR VALUE GAP (imbalance) — without displacement/FVG the OB is weak. Both required by default
    so we mark only high-quality institutional zones (not every pullback near price).

    Lifecycle: `fresh` (untouched) -> `mitigated` (price traded back INTO the zone) -> `broken`
    (a candle CLOSED beyond the far edge). Broken = INVALID; consumers drop it.
    """
    out: List[dict] = []
    if len(swings) < 2 or not bars:
        return out
    last_idx = len(bars) - 1
    # walk swing legs from most recent backward
    for k in range(len(swings) - 1, 0, -1):
        if len(out) >= max_blocks:
            break
        origin = swings[k - 1]
        extreme = swings[k]
        direction = "up" if extreme.price > origin.price else "down"
        want_bull = direction == "up"        # up-leg -> look for bearish OB candle
        # RULE BOS: impuls wajib menembus struktur sejenis sebelumnya
        if require_bos and not _leg_broke_structure(swings, k, extreme):
            continue
        # RULE FVG: impuls wajib meninggalkan imbalance
        has_fvg = _impulse_has_fvg(bars, origin.index, extreme.index, want_bull)
        if require_fvg and not has_fvg:
            continue
        # RULE VOLUME: gerak keluar OB (impuls) wajib bervolume DI ATAS rata-rata lokal (konfirmasi)
        vol_ok = any(_vol_confirmed(bars, i, mult=vol_mult)
                     for i in range(origin.index, min(extreme.index, last_idx) + 1))
        if require_volume and not vol_ok:
            continue
        start = max(0, origin.index - lookback)
        end = origin.index
        ob_bar = None
        for i in range(end, start - 1, -1):
            if i >= len(bars):
                continue
            b = bars[i]
            bull = _is_bullish(b)
            if (want_bull and not bull) or (not want_bull and bull):
                ob_bar = i
                break
        if ob_bar is None:
            continue
        b = bars[ob_bar]
        top, bottom = max(b.high, b.low), min(b.high, b.low)
        # REFINEMENT: giant candle -> zone = body only (keeps the zone actionable)
        a = atr[ob_bar] if atr is not None and 0 <= ob_bar < len(atr) else 0.0
        refined = False
        if a > 0 and (top - bottom) > refine_mult * a:
            body_top, body_bot = max(b.open, b.close), min(b.open, b.close)
            if body_top > body_bot:              # skip pure doji (no body to refine to)
                top, bottom, refined = body_top, body_bot, True
        # lifecycle: mitigated = traded back INTO zone; broken = CLOSED through far edge
        mitigated = False
        broken = False
        for i in range(ob_bar + 1, last_idx + 1):
            bi = bars[i]
            if not mitigated and bi.low <= top and bi.high >= bottom:
                mitigated = True
            if (want_bull and bi.close < bottom) or ((not want_bull) and bi.close > top):
                broken = True
                break
        out.append({
            "type": "bull" if want_bull else "bear",
            "top": round(top, 8),
            "bottom": round(bottom, 8),
            "mid": round((top + bottom) / 2, 8),
            "index": ob_bar,
            "leg_direction": direction,
            "refined": refined,
            "has_fvg": has_fvg,           # displacement/imbalance ada -> OB kuat
            "has_bos": True,              # lolos gerbang BOS (kalau tidak, sudah di-skip di atas)
            "vol_confirmed": vol_ok,      # gerak keluar bervolume tinggi (permintaan/distribusi nyata)
            "retests": _count_retests(bars, top, bottom, ob_bar + 1),   # sering di-retest = kuat
            "mitigated": mitigated,
            "broken": broken,
            "status": "broken" if broken else ("mitigated" if mitigated else "fresh"),
        })
    return out


def detect_bases(bars: Sequence[Bar], atr: Sequence[float], min_len: int = 3,
                 range_mult: float = 1.5, max_zones: int = 10,
                 require_volume: bool = False, vol_mult: float = 1.2) -> List[dict]:
    """Zona AKUMULASI/DISTRIBUSI (sideways base) — 'pijakan' di TENGAH tren, pelengkap OB klasik.

    OB klasik hanya menandai origin swing (ekstrem). Padahal di tengah tren ada cluster sideways
    (>= min_len bar dengan total range <= range_mult x ATR) tempat likuiditas dikumpulkan sebelum
    harga melanjut — area para pembeli/penjual memasang limit order. Deteksi: run sideways maksimal,
    lalu bar berikutnya BREAKOUT close di luar range -> zona jadi support (breakout naik, type bull /
    akumulasi) atau resistance (breakout turun, type bear / distribusi).
    Lifecycle sama dgn OB: fresh -> mitigated (di-retest) -> broken (close menembus sisi jauh).
    """
    out: List[dict] = []
    n = len(bars)
    i = 0
    while i < n - min_len:
        j = i
        hi, lo = bars[i].high, bars[i].low
        while j + 1 < n:
            a = atr[j + 1] if j + 1 < len(atr) else (atr[-1] if atr else 0.0)
            nb = bars[j + 1]
            nh, nl = max(hi, nb.high), min(lo, nb.low)
            # STOP absorbing when the next bar CLOSES outside the band (that's the breakout, not the
            # base) — otherwise a greedy range check swallows the breakout candle & hides the zone.
            closes_in = (lo - 0.15 * a) <= nb.close <= (hi + 0.15 * a)
            if a > 0 and (nh - nl) <= range_mult * a and closes_in:
                hi, lo = nh, nl
                j += 1
            else:
                break
        if (j - i + 1) >= min_len and j + 1 < n:
            b = bars[j + 1]                       # bar breakout
            kind = "bull" if b.close > hi else ("bear" if b.close < lo else None)
            # RULE VOLUME: breakout dari base wajib bervolume DI ATAS rata-rata lokal (konfirmasi)
            vol_ok = _vol_confirmed(bars, j + 1, mult=vol_mult)
            if kind is not None and (vol_ok or not require_volume):
                mitigated = False
                broken = False
                for t in range(j + 2, n):
                    bt = bars[t]
                    if not mitigated and bt.low <= hi and bt.high >= lo:
                        mitigated = True
                    if (kind == "bull" and bt.close < lo) or (kind == "bear" and bt.close > hi):
                        broken = True
                        break
                out.append({
                    "type": kind,                 # bull = akumulasi/support · bear = distribusi/resist
                    "top": round(hi, 8),
                    "bottom": round(lo, 8),
                    "mid": round((hi + lo) / 2, 8),
                    "index": i,                   # awal cluster (utk penggambaran box dari sini)
                    "end_index": j,
                    "bars": j - i + 1,
                    "kind": "base",
                    "vol_confirmed": vol_ok,      # breakout bervolume tinggi = permintaan/distribusi nyata
                    "retests": _count_retests(bars, hi, lo, j + 2),
                    "mitigated": mitigated,
                    "broken": broken,
                    "status": "broken" if broken else ("mitigated" if mitigated else "fresh"),
                })
            i = j + 1
        else:
            i += 1
    return out[-max_zones:]


def retest(price: float, direction: int, order_blocks: List[dict],
           near_pct: float = 0.5) -> Optional[dict]:
    """Is `price` retesting a fresh OB aligned with `direction`?

    direction +1 (long) -> a fresh bullish OB within near_pct% of price.
    direction -1 (short) -> a fresh bearish OB within near_pct% of price.
    Returns the matched OB or None. Only fresh (unmitigated) OBs qualify — a
    mitigated OB has already done its job and is lower quality.
    """
    if not price or not order_blocks:
        return None
    want = "bull" if direction > 0 else "bear"
    for ob in order_blocks:
        if ob["status"] != "fresh" or ob["type"] != want:
            continue
        dist_pct = abs(price - ob["mid"]) / price * 100.0
        if dist_pct <= near_pct:
            return ob
    return None
