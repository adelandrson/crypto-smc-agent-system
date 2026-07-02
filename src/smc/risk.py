"""Risk: structure-based SL, position sizing from risk%, staged TP (R-based).

SL is anchored to structure (swing / FVG zone), never a fixed tick. Size is
derived from risk% and SL distance — leverage never inflates risk per trade.
"""

from __future__ import annotations

from typing import Optional


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


def tp_targets(direction: int, entry: float, sl: float, mode: str = "scalp"):
    """Staged take-profits matching the skill's exit structure.

    mode='scalp' (Mode A4): 3 levels — 1.5R/2.5R/4R, sizes 50/30/20%, SL->BE after TP1.
    mode='swing' (Mode B3): 5 levels + moonbag — 1.5R/2.5R/4R/6R + moonbag(trailing),
        sizes 25/25/25/15/10%, SL evolution: BE -> TP1 -> trail 5% -> trail 8%.

    Each TP carries `sl_after` metadata the broker applies on fill so SL evolves
    exactly per the skill (B3 SL evolution) rather than only BE-after-TP1.
    """
    R = abs(entry - sl)
    if mode == "swing":
        plan = [
            ("TP1", 1.5, 0.25, {"mode": "be"}),
            ("TP2", 2.5, 0.25, {"mode": "lock", "lock_label": "TP1"}),
            ("TP3", 4.0, 0.25, {"mode": "trail", "value": 0.05}),
            ("TP4", 6.0, 0.15, {"mode": "trail", "value": 0.08}),
            ("TP5", None, 0.10, {"mode": "trail", "value": 0.08}),  # moonbag: no fixed price
        ]
    else:  # scalp (A4)
        plan = [
            ("TP1", 1.5, 0.50, {"mode": "be"}),
            ("TP2", 2.5, 0.30, {"mode": "trail", "value": 0.003}),
            ("TP3", 4.0, 0.20, {"mode": "trail", "value": 0.003}),
        ]
    return [{"label": lbl,
             "price": (None if mult is None else entry + direction * mult * R),
             "frac": frac, "filled": False, "sl_after": sa}
            for lbl, mult, frac, sa in plan]
