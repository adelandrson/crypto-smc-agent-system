"""Core data types for the FVG (Fair Value Gap) engine.

Replicates the behaviour of the "FVG by Nephew_sam_" TradingView indicator:
3-candle imbalance detection, mitigation state machine, inverse FVG (IFVG),
ATR/percent threshold filtering and multi-timeframe support.

Pure stdlib — no third-party dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    """Direction of the imbalance."""

    BULLISH = "bullish"
    BEARISH = "bearish"

    @property
    def opposite(self) -> "Direction":
        return Direction.BEARISH if self is Direction.BULLISH else Direction.BULLISH


class State(str, Enum):
    """Lifecycle state of a gap.

    UNMITIGATED -> price has not returned into the zone.
    MITIGATED   -> price wicked/closed into the zone (partial interaction).
    FILLED      -> price reached the far edge of the zone (gap closed).
    INVALIDATED -> price closed fully through the far edge; the zone flips
                   into an inverse FVG.
    """

    UNMITIGATED = "unmitigated"
    MITIGATED = "mitigated"
    FILLED = "filled"
    INVALIDATED = "invalidated"


@dataclass
class Bar:
    """A single OHLC(V) candle."""

    index: int
    time: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class FVG:
    """A Fair Value Gap zone.

    `top`/`bottom` are the price boundaries (top > bottom always). For a
    bullish gap price sits above the zone and returns downward to mitigate;
    for a bearish gap price sits below and returns upward.
    """

    id: int
    direction: Direction
    top: float
    bottom: float
    # The bar that *completes* the 3-candle pattern (the gap is anchored here
    # and projects forward). For a base FVG this is candle index `i`.
    formed_index: int
    formed_time: float
    # ATR and price captured at formation, used by threshold filtering and
    # for reporting how "significant" the gap is.
    atr_at_formation: float = 0.0
    price_at_formation: float = 0.0
    # State transitions (bar index at which each first occurred).
    mitigated_index: Optional[int] = None
    mitigated_time: Optional[float] = None
    filled_index: Optional[int] = None
    filled_time: Optional[float] = None
    invalidated_index: Optional[int] = None
    invalidated_time: Optional[float] = None
    # Whether this gap is an inverse FVG (a base gap that was invalidated and
    # flipped to act as the opposite side support/resistance).
    is_inverse: bool = False
    # Source timeframe in minutes (None / base resolution for the base chart,
    # a value for multi-timeframe gaps projected from a higher timeframe).
    source_tf_minutes: Optional[int] = None

    # ----- derived -----------------------------------------------------
    @property
    def size(self) -> float:
        return self.top - self.bottom

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def size_pct(self) -> float:
        if self.price_at_formation <= 0:
            return 0.0
        return self.size / self.price_at_formation * 100.0

    @property
    def atr_multiple(self) -> float:
        if self.atr_at_formation <= 0:
            return math.inf if self.size > 0 else 0.0
        return self.size / self.atr_at_formation

    @property
    def state(self) -> State:
        if self.invalidated_index is not None:
            return State.INVALIDATED
        if self.filled_index is not None:
            return State.FILLED
        if self.mitigated_index is not None:
            return State.MITIGATED
        return State.UNMITIGATED

    @property
    def is_active(self) -> bool:
        """A zone is tradeable while it has not been filled or invalidated."""
        return self.state in (State.UNMITIGATED, State.MITIGATED)

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        d["state"] = self.state.value
        d["size"] = round(self.size, 10)
        d["midpoint"] = round(self.midpoint, 10)
        d["size_pct"] = round(self.size_pct, 6)
        d["atr_multiple"] = (
            None if math.isinf(self.atr_multiple) else round(self.atr_multiple, 6)
        )
        d["is_active"] = self.is_active
        return d


class AlertType(str, Enum):
    NEW_FVG = "new_fvg"
    PRICE_ENTERED = "price_entered"
    MITIGATED = "mitigated"
    FILLED = "filled"
    INVALIDATED = "invalidated"
    IFVG_FORMED = "ifvg_formed"


@dataclass
class Alert:
    type: AlertType
    fvg_id: int
    index: int
    time: float
    price: float
    direction: Direction
    is_inverse: bool = False
    source_tf_minutes: Optional[int] = None
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["direction"] = self.direction.value
        return d


@dataclass
class Config:
    """Engine configuration. Mirrors the options of the original indicator."""

    # ATR lookback used both for threshold filtering and reporting.
    atr_period: int = 14
    # Threshold filtering mode: "none" | "atr" | "percent".
    # Calibrated default: "atr" with min_atr_mult=0.25 sits just below the
    # real-market median gap size (~0.29 ATR across BTC/ETH/SOL/BNB, 5m-4h),
    # removing ~44% of sub-quarter-ATR micro-noise while keeping the
    # structurally significant gaps. Set to "none" to show every imbalance.
    threshold_mode: str = "atr"
    # Minimum gap size as a multiple of ATR (threshold_mode == "atr").
    min_atr_mult: float = 0.25
    # Minimum gap size as a percent of price (threshold_mode == "percent").
    min_pct: float = 0.1
    # Mitigation trigger: "wick" (any penetration) or "close" (body close).
    mitigation_mode: str = "wick"
    # Whether an invalidated gap flips into an inverse FVG.
    enable_inverse: bool = True
    # Higher timeframes (in minutes) to additionally scan, e.g. [60, 240].
    mtf_minutes: list = field(default_factory=list)

    @staticmethod
    def from_dict(data: Optional[dict]) -> "Config":
        cfg = Config()
        if not data:
            return cfg
        for key, value in data.items():
            if hasattr(cfg, key) and value is not None:
                setattr(cfg, key, value)
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)
