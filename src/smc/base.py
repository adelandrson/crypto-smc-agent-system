"""Common multi-CEX abstraction.

DATA is fetched directly from each exchange's PUBLIC market endpoints (no API
key needed) and normalised to a single OHLCV shape that feeds the FVG engine.
EXECUTION is normalised into an `OrderIntent` and handed off to each exchange's
official skill (Bybit `bybit-trading`, OKX `okx-cex-trade`, Binance skills-hub)
which own signing/confirmation/safety — this layer never signs orders itself.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Optional

CANONICAL_TFS = ("5m", "15m", "1h", "4h", "1d")


def http_get_json(url: str, timeout: float = 20.0) -> dict:
    """GET a URL and parse JSON. Raises on network/HTTP/parse error."""
    req = urllib.request.Request(url, headers={"User-Agent": "gabungan-skills/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


@dataclass
class OrderIntent:
    """Exchange-agnostic order request. Routed to a venue's official skill."""

    symbol: str                 # canonical, e.g. "BTC/USDT"
    side: str                   # "buy" | "sell"
    order_type: str = "market"  # "market" | "limit"
    qty: Optional[float] = None         # base qty (or quote for spot market buy)
    quote_qty: Optional[float] = None   # spend amount in quote (e.g. USDT)
    price: Optional[float] = None       # required for limit
    market_type: str = "perp"   # "perp" | "spot"
    leverage: Optional[float] = None
    reduce_only: bool = False
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    client_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class ExchangeAdapter(ABC):
    """One adapter per CEX. Data methods are live; execution is delegated."""

    name: str = "base"
    # natural-language venue + the official skill that executes orders there
    execution_skill: str = ""

    # ---- symbol / timeframe normalisation -----------------------------
    @abstractmethod
    def normalize_symbol(self, canonical: str, market_type: str = "perp") -> str:
        ...

    @abstractmethod
    def map_timeframe(self, tf: str) -> str:
        ...

    # ---- public market data (no auth) ---------------------------------
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h",
                    limit: int = 200, market_type: str = "perp") -> List[list]:
        """Return candles ASCENDING as [ts_ms, open, high, low, close, volume]."""

    @abstractmethod
    def fetch_funding(self, symbol: str, market_type: str = "perp") -> Optional[float]:
        """Latest funding rate as a fraction (e.g. 0.0001 = 0.01%)."""

    @abstractmethod
    def fetch_open_interest(self, symbol: str, market_type: str = "perp") -> Optional[float]:
        """Open interest (contracts or base units, exchange-defined)."""

    def fetch_long_short_ratio(self, symbol: str, market_type: str = "perp") -> Optional[float]:
        """Global long/short account ratio (retail crowd positioning). None if the
        venue does not expose it publicly (Bybit/OKX) — the sentiment layer
        degrades gracefully. Contrarian signal at extremes."""
        return None

    def fetch_taker_buy_volume(self, symbol: str, timeframe: str = "1h",
                               limit: int = 200, market_type: str = "perp") -> Optional[list]:
        """Taker-buy volume series (aggressive buy flow proxy). None if unsupported.
        Used by the CVD proxy sentiment leg."""
        return None

    # ---- execution (delegated to the venue's official skill) ----------
    def build_order(self, intent: OrderIntent) -> dict:
        """Translate an OrderIntent into this venue's native order params +
        a handoff descriptor. Does NOT execute — the official skill does.
        """
        return {
            "venue": self.name,
            "execution_skill": self.execution_skill,
            "native_params": self._native_order(intent),
            "intent": intent.to_dict(),
            "note": f"Hand off to '{self.execution_skill}' to sign & execute on {self.name}.",
        }

    @abstractmethod
    def _native_order(self, intent: OrderIntent) -> dict:
        """Native order parameter dict in the venue's own schema."""

    def market_snapshot(self, symbol: str, timeframe: str = "1h",
                        limit: int = 200, market_type: str = "perp") -> dict:
        """Bundle OHLCV + funding + OI for one symbol (best-effort per field)."""
        out = {"exchange": self.name, "symbol": symbol,
               "timeframe": timeframe, "market_type": market_type}
        try:
            out["candles"] = self.fetch_ohlcv(symbol, timeframe, limit, market_type)
        except Exception as e:  # noqa: BLE001
            out["candles"], out["candles_error"] = [], f"{type(e).__name__}: {e}"
        for fld, fn in (("funding_rate", self.fetch_funding),
                        ("open_interest", self.fetch_open_interest),
                        ("long_short_ratio", self.fetch_long_short_ratio)):
            try:
                out[fld] = fn(symbol, market_type)
            except Exception as e:  # noqa: BLE001
                out[fld] = None
                out[f"{fld}_error"] = f"{type(e).__name__}: {e}"
        return out
