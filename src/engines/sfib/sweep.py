"""Liquidity sweep / EQH-EQL (stop-hunt) — deterministik.

EQH/EQL = kumpulan swing high/low pada harga ~sama = POOL LIKUIDITAS (stop order menumpuk di
situ). SWEEP = harga menembus (wick) melewati pool lalu CLOSE balik = stop-hunt/trap → sinyal
REVERSAL berkualitas:
  - Sweep SELL-side (pool EQL / low): low tembus DI BAWAH pool lalu close DI ATAS → BULLISH (+1).
  - Sweep BUY-side  (pool EQH / high): high tembus DI ATAS pool lalu close DI BAWAH → BEARISH (-1).
Entry SMC bagus biasanya terjadi SETELAH liquidity sweep + BOS/CHoCH, bukan BOS polos — makanya
ini dikonsumsi confluence sebagai booster A+ (sejenis ob_retest yang sudah ada).
"""
from __future__ import annotations

from typing import List, Sequence

from .swings import Pivot


def find_liquidity_pools(swings: Sequence[Pivot], tol: float) -> dict:
    """Cluster swing high (EQH) & swing low (EQL) yang berjarak <= tol → level pool (rata cluster).
    Butuh >= 2 pivot 'equal' untuk dianggap pool likuiditas (definisi EQH/EQL)."""
    def cluster(vals: List[float]) -> List[float]:
        vals = sorted(vals)
        pools: List[float] = []
        i = 0
        while i < len(vals):
            grp = [vals[i]]
            j = i
            while j + 1 < len(vals) and vals[j + 1] - grp[0] <= tol:
                j += 1
                grp.append(vals[j])
            if len(grp) >= 2:                       # >=2 harga ~sama = pool
                pools.append(round(sum(grp) / len(grp), 10))
            i = j + 1
        return pools

    return {"eqh": cluster([p.price for p in swings if p.kind == "high"]),
            "eql": cluster([p.price for p in swings if p.kind == "low"])}


def liquidity_map(swings: Sequence[Pivot], atr, price: float, tol_mult: float = 0.35) -> dict:
    """Peta likuiditas: SETIAP swing high = Buy-Side Liquidity (BSL, stop di atas), setiap swing low =
    Sell-Side Liquidity (SSL, stop di bawah) — bukan hanya yg 'equal'. EQH/EQL (>=2 sejajar) = pool
    TERKUAT. Toleransi 'equal' = max(tol_mult x ATR, 0.1% harga) supaya 'hampir sejajar' tertangkap."""
    a = atr[-1] if atr else 0.0
    tol = max(tol_mult * a, 0.001 * price) if price else (tol_mult * a)
    pools = find_liquidity_pools(swings, tol)
    eqh, eql = pools["eqh"], pools["eql"]
    highs = sorted({round(p.price, 8) for p in swings if p.kind == "high"})
    lows = sorted({round(p.price, 8) for p in swings if p.kind == "low"})
    bsl = [{"level": h, "equal": any(abs(h - e) <= tol for e in eqh)} for h in highs]
    ssl = [{"level": l, "equal": any(abs(l - e) <= tol for e in eql)} for l in lows]
    return {"eqh": eqh, "eql": eql, "bsl": bsl, "ssl": ssl, "tol": tol}


def detect_sweep(bars, swings: Sequence[Pivot], atr, tol_mult: float = 0.35,
                 lookback: int = 3) -> dict:
    """Liquidity sweep di `lookback` bar terakhir terhadap likuiditas swing high/low (BUKAN hanya
    EQH/EQL — sweep terjadi di likuiditas mana pun). SWEEP = bar wick TEMBUS level lalu CLOSE BALIK
    ke dalam range (close di LUAR = breakout/BOS, bukan sweep). Return {swept, direction(+1/-1/0),
    level, type('EQL'|'SSL'|'EQH'|'BSL'), equal, wick_atr, age}."""
    none = {"swept": False, "direction": 0, "level": None, "type": None, "equal": False,
            "wick_atr": None, "age": None}
    n = len(bars)
    if n < 2 or not swings:
        return none
    a = atr[-1] if atr else 0.0
    ref = bars[-1].close or bars[-1].high or 1.0
    tol = max(tol_mult * a, 0.001 * ref) if a and a > 0 else 0.001 * ref
    pools = find_liquidity_pools(swings, tol)
    eqh, eql = pools["eqh"], pools["eql"]
    wick = 0.15 * a if a and a > 0 else 0.0         # tembusan minimal (bukan poke sepele)
    for k in range(1, min(lookback, n) + 1):
        idx = n - k
        b = bars[idx]
        for p in swings:                            # SELL-side sweep (bullish): tembus low, close di atas
            if p.kind == "low" and p.index < idx and b.low < p.price - wick and b.close > p.price:
                is_eq = any(abs(p.price - e) <= tol for e in eql)
                return {"swept": True, "direction": 1, "level": round(p.price, 8),
                        "type": "EQL" if is_eq else "SSL", "equal": is_eq,
                        "wick_atr": round((p.price - b.low) / a, 2) if a else None, "age": k - 1}
        for p in swings:                            # BUY-side sweep (bearish): tembus high, close di bawah
            if p.kind == "high" and p.index < idx and b.high > p.price + wick and b.close < p.price:
                is_eq = any(abs(p.price - e) <= tol for e in eqh)
                return {"swept": True, "direction": -1, "level": round(p.price, 8),
                        "type": "EQH" if is_eq else "BSL", "equal": is_eq,
                        "wick_atr": round((b.high - p.price) / a, 2) if a else None, "age": k - 1}
    return none
