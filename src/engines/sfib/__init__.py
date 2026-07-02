"""swing-fib — deterministic swing detection + Fibonacci + market structure.

Public API:
    analyze(bars, config) -> swings, active-leg Fib levels/zones, structure, score
"""

from .core import Bar, normalize_bars, compute_atr
from .swings import Pivot, raw_pivots, zigzag, significant_swings
from .structure import classify
from .fib import fib_for_leg, RETRACEMENTS, EXTENSIONS, OTE, GOLDEN_POCKET
from .ob import detect_order_blocks, retest
from .engine import analyze, DEFAULTS, PRESETS, preset_for

__all__ = [
    "Bar", "normalize_bars", "compute_atr", "Pivot", "raw_pivots", "zigzag",
    "significant_swings", "classify", "fib_for_leg", "RETRACEMENTS",
    "EXTENSIONS", "OTE", "GOLDEN_POCKET", "detect_order_blocks", "retest",
    "analyze", "DEFAULTS", "PRESETS", "preset_for",
]
__version__ = "1.1.0"
