"""Gap significance filtering — ATR multiple or percent-of-price."""

from __future__ import annotations

from .types import Config


def passes_threshold(size: float, price: float, atr: float, cfg: Config) -> bool:
    """Return True if a gap of `size` is large enough to keep.

    Mirrors the original indicator's optional "minimum gap size" filter, which
    can be expressed either as a multiple of ATR or a percent of price.
    """

    if size <= 0:
        return False
    mode = (cfg.threshold_mode or "none").lower()
    if mode == "none":
        return True
    if mode == "atr":
        if atr <= 0:
            # No ATR reference yet (very start of series) — do not filter out.
            return True
        return size >= atr * cfg.min_atr_mult
    if mode == "percent":
        if price <= 0:
            return True
        return (size / price * 100.0) >= cfg.min_pct
    raise ValueError(f"unknown threshold_mode: {cfg.threshold_mode!r}")
