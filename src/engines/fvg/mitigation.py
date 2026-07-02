"""Mitigation state machine and inverse-FVG (IFVG) generation.

For each gap we scan forward and record the first bar at which price:
  * mitigates  — wicks (or closes) back into the zone,
  * fills       — reaches the far edge of the zone,
  * invalidates — closes fully through the far edge (the gap then flips
                  into an inverse FVG acting as the opposite side S/R).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .types import Bar, Config, Direction, FVG


def _resolve(fvg: FVG, bars: Sequence[Bar], cfg: Config) -> None:
    """Populate the transition indices of a single gap in place."""

    wick = (cfg.mitigation_mode or "wick").lower() != "close"
    n = len(bars)
    for j in range(fvg.formed_index + 1, n):
        bar = bars[j]
        if fvg.direction is Direction.BULLISH:
            # price sits above a bullish gap and returns downward
            touched = (bar.low <= fvg.top) if wick else (bar.close <= fvg.top)
            reached_far = bar.low <= fvg.bottom
            closed_through = bar.close < fvg.bottom
        else:
            # price sits below a bearish gap and returns upward
            touched = (bar.high >= fvg.bottom) if wick else (bar.close >= fvg.bottom)
            reached_far = bar.high >= fvg.top
            closed_through = bar.close > fvg.top

        if touched and fvg.mitigated_index is None:
            fvg.mitigated_index = j
            fvg.mitigated_time = bar.time
        if reached_far and fvg.filled_index is None:
            fvg.filled_index = j
            fvg.filled_time = bar.time
        if closed_through:
            fvg.invalidated_index = j
            fvg.invalidated_time = bar.time
            return  # the zone is dead; it flips into an IFVG from here


def _make_inverse(fvg: FVG, next_id: int) -> FVG:
    """Flip an invalidated gap into an inverse FVG at the invalidation bar."""

    return FVG(
        id=next_id,
        direction=fvg.direction.opposite,
        top=fvg.top,
        bottom=fvg.bottom,
        formed_index=fvg.invalidated_index,
        formed_time=fvg.invalidated_time,
        atr_at_formation=fvg.atr_at_formation,
        price_at_formation=fvg.price_at_formation,
        is_inverse=True,
        source_tf_minutes=fvg.source_tf_minutes,
    )


def resolve_all(
    fvgs: List[FVG], bars: Sequence[Bar], cfg: Config, next_id: Optional[int] = None
) -> List[FVG]:
    """Resolve base gaps, then derive and resolve inverse gaps.

    Inverse gaps are derived from invalidated base gaps only (a single level of
    inversion — an IFVG does not itself spawn another IFVG).
    """

    if next_id is None:
        next_id = (max((f.id for f in fvgs), default=-1)) + 1

    for fvg in fvgs:
        _resolve(fvg, bars, cfg)

    result = list(fvgs)
    if cfg.enable_inverse:
        for fvg in fvgs:
            if fvg.invalidated_index is not None:
                inv = _make_inverse(fvg, next_id)
                next_id += 1
                _resolve(inv, bars, cfg)
                result.append(inv)
    return result
