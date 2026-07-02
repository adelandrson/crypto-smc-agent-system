"""FVG (Fair Value Gap) engine — a programmatic replica of the
"FVG by Nephew_sam_" TradingView indicator.

Public API:
    analyze(bars, config)   -> full structured result (detect + analysis)
    compute(bars, config)   -> (bars, base_fvgs, mtf_fvgs, alerts)
    load_csv(path)          -> list[Bar]
"""

from .types import Bar, Config, Direction, State, FVG, Alert, AlertType
from .data import normalize_bars, compute_atr, load_csv
from .detector import detect_fvgs
from .mitigation import resolve_all
from .mtf import detect_mtf, resample_bars
from .alerts import build_alerts
from .engine import analyze, compute, analyze_zones, summarize, infer_base_minutes

__all__ = [
    "Bar",
    "Config",
    "Direction",
    "State",
    "FVG",
    "Alert",
    "AlertType",
    "normalize_bars",
    "compute_atr",
    "load_csv",
    "detect_fvgs",
    "resolve_all",
    "detect_mtf",
    "resample_bars",
    "build_alerts",
    "analyze",
    "compute",
    "analyze_zones",
    "summarize",
    "infer_base_minutes",
]

__version__ = "1.0.0"
