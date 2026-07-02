"""Top-level orchestration: detect -> resolve -> inverse -> MTF -> alerts,
plus a transparent zone/bias analysis. This is the public entry point used
by the Hermes plugin tools."""

from __future__ import annotations

import statistics
from typing import List, Optional, Sequence

from .types import Bar, Config, Direction, FVG, State
from .data import normalize_bars, compute_atr
from .detector import detect_fvgs
from .mitigation import resolve_all
from .mtf import detect_mtf
from .alerts import build_alerts


def infer_base_minutes(bars: Sequence[Bar]) -> Optional[float]:
    """Estimate the base timeframe (minutes) from bar timestamps."""

    if len(bars) < 3:
        return None
    deltas = [
        bars[i].time - bars[i - 1].time
        for i in range(1, len(bars))
        if bars[i].time > bars[i - 1].time
    ]
    if not deltas:
        return None
    return round(statistics.median(deltas) / 60.0, 6) or None


def compute(bars_input, cfg: Config):
    """Run the full pipeline. Returns (bars, base_fvgs, mtf_fvgs, alerts)."""

    bars = normalize_bars(bars_input)
    atr = compute_atr(bars, cfg.atr_period)
    raw = detect_fvgs(bars, atr, cfg)
    base = resolve_all(raw, bars, cfg, next_id=len(raw))

    next_id = (max((f.id for f in base), default=-1)) + 1
    mtf: List[FVG] = []
    for htf in cfg.mtf_minutes or []:
        htf = int(htf)
        zones = detect_mtf(bars, cfg, htf, start_id=next_id)
        next_id += len(zones) + 1
        mtf.extend(zones)

    alerts = build_alerts(list(base) + mtf, bars)
    return bars, base, mtf, alerts


def _weight(f: FVG) -> float:
    # Higher-timeframe imbalances carry more structural weight.
    return 2.0 if f.source_tf_minutes else 1.0


def analyze_zones(fvgs: Sequence[FVG], last_price: float) -> dict:
    """Identify active zones around price and derive a transparent bias."""

    active = [f for f in fvgs if f.is_active]
    inside = [f for f in active if f.contains(last_price)]
    below = sorted(
        (f for f in active if f.top <= last_price),
        key=lambda f: last_price - f.top,
    )
    above = sorted(
        (f for f in active if f.bottom >= last_price),
        key=lambda f: f.bottom - last_price,
    )

    bull_w = sum(_weight(f) for f in active if f.direction is Direction.BULLISH)
    bear_w = sum(_weight(f) for f in active if f.direction is Direction.BEARISH)
    net = bull_w - bear_w
    if inside:
        # Reacting at an imbalance: lean with the (weighted) dominant zone here.
        z = max(inside, key=_weight)
        bias = "bullish" if z.direction is Direction.BULLISH else "bearish"
        reason = (
            f"price is inside a {z.direction.value}"
            f"{' inverse' if z.is_inverse else ''} gap"
        )
    elif net > 0:
        bias, reason = "bullish", "weighted active demand gaps outweigh supply"
    elif net < 0:
        bias, reason = "bearish", "weighted active supply gaps outweigh demand"
    else:
        bias, reason = "neutral", "active demand and supply gaps are balanced"

    return {
        "bias": bias,
        "bias_reason": reason,
        "bull_weight": round(bull_w, 3),
        "bear_weight": round(bear_w, 3),
        "active_count": len(active),
        "price_inside_gap": bool(inside),
        "nearest_support": below[0].to_dict() if below else None,
        "nearest_resistance": above[0].to_dict() if above else None,
        "active_zones": [f.to_dict() for f in active],
    }


def summarize(base: Sequence[FVG], mtf: Sequence[FVG]) -> dict:
    allf = list(base) + list(mtf)
    by_state = {s.value: 0 for s in State}
    bull = bear = inverse = 0
    for f in allf:
        by_state[f.state.value] += 1
        if f.direction is Direction.BULLISH:
            bull += 1
        else:
            bear += 1
        if f.is_inverse:
            inverse += 1
    return {
        "total": len(allf),
        "base": len(base),
        "mtf": len(mtf),
        "bullish": bull,
        "bearish": bear,
        "inverse": inverse,
        "by_state": by_state,
    }


def analyze(bars_input, config: Optional[dict] = None) -> dict:
    """Full structured result for the agent."""

    cfg = Config.from_dict(config)
    bars, base, mtf, alerts = compute(bars_input, cfg)
    last_price = bars[-1].close if bars else 0.0
    last_time = bars[-1].time if bars else 0.0
    return {
        "ok": True,
        "bar_count": len(bars),
        "base_timeframe_minutes": infer_base_minutes(bars),
        "last_price": last_price,
        "last_time": last_time,
        "config": cfg.to_dict(),
        "summary": summarize(base, mtf),
        "fvgs": [f.to_dict() for f in base],
        "mtf_fvgs": [f.to_dict() for f in mtf],
        "zones": analyze_zones(list(base) + mtf, last_price),
        "alerts": [a.to_dict() for a in alerts],
    }
