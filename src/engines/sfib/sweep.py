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


def detect_sweep(bars, swings: Sequence[Pivot], atr, tol_mult: float = 0.15,
                 lookback: int = 3) -> dict:
    """Deteksi liquidity sweep di `lookback` bar terakhir terhadap pool EQH/EQL.

    Return {swept, direction(+1 bullish/-1 bearish/0), level, type('EQL'|'EQH'|None), age(bar ke-belakang)}.
    `age`=0 = bar terakhir. Toleransi 'equal' = tol_mult * ATR (fallback fraksi harga)."""
    none = {"swept": False, "direction": 0, "level": None, "type": None, "age": None}
    n = len(bars)
    if n < 2 or not swings:
        return none
    a = atr[-1] if atr else 0.0
    ref = bars[-1].close or bars[-1].high or 1.0
    tol = tol_mult * a if a and a > 0 else 0.001 * ref
    pools = find_liquidity_pools(swings, tol)
    if not pools["eqh"] and not pools["eql"]:
        return none
    for k in range(1, min(lookback, n) + 1):
        b = bars[n - k]
        for lvl in pools["eql"]:                    # sell-side sweep -> bullish
            if b.low < lvl - 1e-12 and b.close > lvl:
                return {"swept": True, "direction": 1, "level": lvl, "type": "EQL", "age": k - 1}
        for lvl in pools["eqh"]:                    # buy-side sweep -> bearish
            if b.high > lvl + 1e-12 and b.close < lvl:
                return {"swept": True, "direction": -1, "level": lvl, "type": "EQH", "age": k - 1}
    return none
