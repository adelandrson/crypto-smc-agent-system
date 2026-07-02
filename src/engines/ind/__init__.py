"""indicators — momentum / volatility / volume engine (single source of truth).

The confluence layer's 4th dimension beyond price-structure (FVG/Fib) and
sentiment (OI/FR): RSI divergence (momentum confirmation), ADX/ATR/BB (volatility
state — replaces the premium "Volatility State"), and volume z-score (the
"volume above average" rule, now computed).

Public API: analyze(candles, config) -> one dict consumed by shared/confluence.py.
"""
from .core import (rsi, adx, atr, atr_percentile, bollinger_width, volume_zscore,
                   true_range, _to_arrays)
from .divergence import detect
from .engine import analyze, DEFAULTS

__all__ = [
    "rsi", "adx", "atr", "atr_percentile", "bollinger_width", "volume_zscore",
    "true_range", "detect", "analyze", "DEFAULTS",
]
__version__ = "1.0.0"
