"""Fibonacci levels, zones (golden pocket / OTE / equilibrium), extensions.

Convention: a leg goes from ORIGIN `O` (start of impulse) to EXTREME `E`
(latest pivot). level(r) = E - r*(E - O); r=0 → E (100% of the move), r=1 → O
(0%). Retracement levels sit between O and E regardless of direction. Extensions
project beyond E in the impulse direction (take-profit targets).
"""

from __future__ import annotations

from typing import List, Optional

# Retracement ratios (incl. golden pocket 0.618-0.65 and ICT OTE 0.62/0.705/0.79)
RETRACEMENTS = [0.236, 0.382, 0.5, 0.618, 0.62, 0.65, 0.705, 0.786, 0.79]
EXTENSIONS = [1.272, 1.414, 1.618, 2.0, 2.618]
GOLDEN_POCKET = (0.618, 0.65)
OTE = (0.62, 0.79)          # ICT optimal trade entry zone
OTE_SWEET = 0.705
GOLDEN_ZONE = (0.5, 0.786)  # high-probability retracement window


def level(O: float, E: float, r: float) -> float:
    return E - r * (E - O)


def fib_for_leg(O: float, E: float, price: float) -> dict:
    span = E - O
    direction = "up" if span > 0 else "down"
    levels = {f"{r:.3f}": round(level(O, E, r), 8) for r in RETRACEMENTS}
    equilibrium = round(level(O, E, 0.5), 8)
    extensions = {f"{x:.3f}": round(E + (x - 1.0) * span, 8) for x in EXTENSIONS}

    # current retracement ratio of price within the leg
    r_price = (E - price) / span if span != 0 else 0.0
    in_golden_pocket = GOLDEN_POCKET[0] <= r_price <= GOLDEN_POCKET[1]
    in_ote = OTE[0] <= r_price <= OTE[1]
    in_golden_zone = GOLDEN_ZONE[0] <= r_price <= GOLDEN_ZONE[1]

    # premium/discount relative to the leg's equilibrium (ICT dealing range)
    lo, hi = (O, E) if E > O else (E, O)
    if price < equilibrium:
        zone = "discount"
    elif price > equilibrium:
        zone = "premium"
    else:
        zone = "equilibrium"

    # nearest retracement level to price
    nearest_r = min(RETRACEMENTS, key=lambda r: abs(level(O, E, r) - price))
    nearest = {
        "ratio": nearest_r,
        "price": round(level(O, E, nearest_r), 8),
        "dist_pct": round(abs(level(O, E, nearest_r) - price) / price * 100, 4) if price else None,
    }

    return {
        "direction": direction,
        "origin": round(O, 8),
        "extreme": round(E, 8),
        "range": round(abs(span), 8),
        "levels": levels,
        "equilibrium": equilibrium,
        "extensions": extensions,
        "golden_pocket": [round(level(O, E, GOLDEN_POCKET[0]), 8),
                          round(level(O, E, GOLDEN_POCKET[1]), 8)],
        "ote_zone": [round(level(O, E, OTE[0]), 8), round(level(O, E, OTE[1]), 8)],
        "ote_sweet": round(level(O, E, OTE_SWEET), 8),
        "retracement_ratio_now": round(r_price, 4),
        "in_golden_pocket": in_golden_pocket,
        "in_ote": in_ote,
        "in_golden_zone": in_golden_zone,
        "zone": zone,          # discount / premium / equilibrium
        "nearest_level": nearest,
    }
