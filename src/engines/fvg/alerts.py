"""Turn resolved gaps into a chronological stream of alert events."""

from __future__ import annotations

from typing import List, Optional, Sequence

from .types import Alert, AlertType, Bar, FVG


def _price_at(bars: Optional[Sequence[Bar]], index: Optional[int], default: float) -> float:
    if bars is None or index is None or index < 0 or index >= len(bars):
        return default
    return bars[index].close


def build_alerts(fvgs: Sequence[FVG], bars: Optional[Sequence[Bar]] = None) -> List[Alert]:
    """Emit one alert per lifecycle transition, sorted by bar index then id."""

    events: List[Alert] = []
    for f in fvgs:
        # formation
        events.append(
            Alert(
                type=AlertType.IFVG_FORMED if f.is_inverse else AlertType.NEW_FVG,
                fvg_id=f.id,
                index=f.formed_index,
                time=f.formed_time,
                price=_price_at(bars, f.formed_index, f.midpoint),
                direction=f.direction,
                is_inverse=f.is_inverse,
                source_tf_minutes=f.source_tf_minutes,
                note=f"{f.direction.value} {'inverse ' if f.is_inverse else ''}gap "
                f"[{f.bottom:g}, {f.top:g}]",
            )
        )
        if f.mitigated_index is not None:
            events.append(
                Alert(
                    type=AlertType.MITIGATED,
                    fvg_id=f.id,
                    index=f.mitigated_index,
                    time=f.mitigated_time,
                    price=_price_at(bars, f.mitigated_index, f.midpoint),
                    direction=f.direction,
                    is_inverse=f.is_inverse,
                    source_tf_minutes=f.source_tf_minutes,
                    note="price returned into the gap",
                )
            )
        if f.filled_index is not None:
            events.append(
                Alert(
                    type=AlertType.FILLED,
                    fvg_id=f.id,
                    index=f.filled_index,
                    time=f.filled_time,
                    price=_price_at(bars, f.filled_index, f.midpoint),
                    direction=f.direction,
                    is_inverse=f.is_inverse,
                    source_tf_minutes=f.source_tf_minutes,
                    note="gap fully filled",
                )
            )
        if f.invalidated_index is not None:
            events.append(
                Alert(
                    type=AlertType.INVALIDATED,
                    fvg_id=f.id,
                    index=f.invalidated_index,
                    time=f.invalidated_time,
                    price=_price_at(bars, f.invalidated_index, f.midpoint),
                    direction=f.direction,
                    is_inverse=f.is_inverse,
                    source_tf_minutes=f.source_tf_minutes,
                    note="price closed through — flips to inverse FVG",
                )
            )
    events.sort(key=lambda a: (a.index if a.index is not None else 0, a.fvg_id))
    return events
