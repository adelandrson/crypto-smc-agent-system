"""Cross-pair SMT divergence / breadth filter (swing mode).

ICT SMT: two correlated assets diverging at swing highs/lows reveals breadth.
When the reference (e.g. BTC) makes a higher-high but a correlated pair (ETH)
makes a lower-high, the rally is narrow -> caution on alt longs. Pure logic over
swing pivots already computed by the swing-fib engine; no new data source.

  narrow_bull : ref HH + sym LH  -> breadth weak, skip/caveat alt longs
  narrow_bear : ref LL + sym HL  -> breadth weak, skip/caveat alt shorts
  confirming  : both same direction -> healthy trend, no veto
  None        : insufficient pivots
"""
from __future__ import annotations

from typing import Optional, Sequence


def _last_two_highs(swings):
    hs = [p for p in swings if getattr(p, "kind", None) == "high"]
    return (hs[-2], hs[-1]) if len(hs) >= 2 else (None, None)


def _last_two_lows(swings):
    ls = [p for p in swings if getattr(p, "kind", None) == "low"]
    return (ls[-2], ls[-1]) if len(ls) >= 2 else (None, None)


def smt_breadth(swings_ref: Sequence, swings_sym: Sequence) -> dict:
    """Compare the reference pair's last two same-type pivots vs the symbol's.

    `swings_*` are lists of swing-fib Pivot objects (or dicts with price/kind).
    Returns {signal, note}."""
    # try highs first
    r0, r1 = _last_two_highs(swings_ref)
    s0, s1 = _last_two_highs(swings_sym)
    if r0 and r1 and s0 and s1:
        ref_hh = r1.price > r0.price
        sym_lh = s1.price < s0.price
        sym_hh = s1.price > s0.price
        if ref_hh and sym_lh:
            return {"signal": "narrow_bull", "note": "ref HH but sym LH - breadth weak, caveat longs"}
        if (not ref_hh) and (not sym_hh) and r1.price < r0.price and s1.price > s0.price:
            return {"signal": "narrow_bear", "note": "ref LL but sym HL - breadth weak, caveat shorts"}
        return {"signal": "confirming", "note": "highs agree - healthy breadth"}
    return {"signal": None, "note": "insufficient pivots"}


def compute_smt(adapters, ref_symbol: str, symbol: str, timeframe: str = "4h",
                limit: int = 220, fib_config: Optional[dict] = None) -> dict:
    """Fetch both symbols' swings via the swing-fib engine and compare.

    Convenience for the swing scanner: pass the exchange adapters + a reference
    (BTC/USDT) + the symbol under analysis. Returns the SMT breadth signal.
    Degrades gracefully on fetch failure (None)."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from shared.confluence import sfib  # single swing-fib authority

    def _swings(sym):
        try:
            candles = adapters[0].fetch_ohlcv(sym, timeframe, limit)
            bars = sfib.normalize_bars(candles)
            atr = sfib.compute_atr(bars, 14)
            return sfib.significant_swings(bars, atr, (fib_config or {}).get("depth", 10),
                                            (fib_config or {}).get("atr_mult", 0.5))
        except Exception:  # noqa: BLE001
            return []

    return smt_breadth(_swings(ref_symbol), _swings(symbol))


def smt_veto(smt_signal: Optional[str], direction: int) -> bool:
    """Should the SMT signal veto a trade in `direction`?

    narrow_bull (breadth weak on highs) vetoes longs.
    narrow_bear vetoes shorts."""
    if smt_signal == "narrow_bull" and direction > 0:
        return True
    if smt_signal == "narrow_bear" and direction < 0:
        return True
    return False
