"""Binance adapter (USDⓂ futures + spot public endpoints) — DATA ONLY.

Sistem ini dry-run/paper murni; TIDAK ada eksekusi order nyata (tak ada API key,
tak ada signing). `_native_order` cuma dipertahankan agar `ExchangeAdapter` ABC
tetap terpenuhi — tak pernah dipanggil di jalur dry-run. Endpoint & parsing sama
persis dgn sumber metodologi (agent-trading/exchanges/binance.py).
"""

from __future__ import annotations

from typing import List, Optional

from .base import ExchangeAdapter, OrderIntent, http_get_json

_FAPI = "https://fapi.binance.com"
_SPOT = "https://api.binance.com"
_TF = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}


class BinanceAdapter(ExchangeAdapter):
    name = "binance"
    execution_skill = "binance-skills-hub"

    def normalize_symbol(self, canonical: str, market_type: str = "perp") -> str:
        # BTC/USDT -> BTCUSDT (both spot and USDM perp use this form)
        return canonical.replace("/", "").replace("-", "").upper()

    def map_timeframe(self, tf: str) -> str:
        return _TF[tf]

    def fetch_ohlcv(self, symbol, timeframe="1h", limit=200, market_type="perp"):
        sym = self.normalize_symbol(symbol, market_type)
        iv = self.map_timeframe(timeframe)
        if market_type == "spot":
            url = f"{_SPOT}/api/v3/klines?symbol={sym}&interval={iv}&limit={limit}"
        else:
            url = f"{_FAPI}/fapi/v1/klines?symbol={sym}&interval={iv}&limit={limit}"
        rows = http_get_json(url)
        # Binance returns ASCENDING [openTime, o, h, l, c, v, ...]
        return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                 float(k[4]), float(k[5])] for k in rows]

    def fetch_funding(self, symbol, market_type="perp"):
        if market_type == "spot":
            return None
        sym = self.normalize_symbol(symbol, market_type)
        data = http_get_json(f"{_FAPI}/fapi/v1/premiumIndex?symbol={sym}")
        return float(data["lastFundingRate"])

    def fetch_open_interest(self, symbol, market_type="perp"):
        if market_type == "spot":
            return None
        sym = self.normalize_symbol(symbol, market_type)
        data = http_get_json(f"{_FAPI}/fapi/v1/openInterest?symbol={sym}")
        return float(data["openInterest"])

    def fetch_long_short_ratio(self, symbol, market_type="perp"):
        if market_type == "spot":
            return None
        sym = self.normalize_symbol(symbol, market_type)
        data = http_get_json(
            f"{_FAPI}/futures/data/globalLongShortAccountRatio"
            f"?symbol={sym}&period=1h&limit=1")
        return float(data[0]["longShortRatio"]) if data else None

    def fetch_taker_buy_volume(self, symbol, timeframe="1h", limit=200, market_type="perp"):
        """Taker-buy base volume series (Binance kline index 9). Proxy for order
        flow: aggressive buying vs selling. None for spot/unsupported."""
        if market_type == "spot":
            return None
        sym = self.normalize_symbol(symbol, market_type)
        iv = self.map_timeframe(timeframe)
        rows = http_get_json(f"{_FAPI}/fapi/v1/klines?symbol={sym}&interval={iv}&limit={limit}")
        # [openTime, o, h, l, c, vol, closeTime, quoteVol, trades, takerBuyBase, ...]
        return [float(k[9]) for k in rows] if rows else None

    # ---- historical series (for backtesting OI/FR legs) ----------------
    def fetch_funding_history(self, symbol, limit=1000, market_type="perp"):
        """Return [(fundingTime_ms, rate_fraction), ...] ascending (8h cadence)."""
        sym = self.normalize_symbol(symbol, market_type)
        data = http_get_json(f"{_FAPI}/fapi/v1/fundingRate?symbol={sym}&limit={limit}")
        return [(int(d["fundingTime"]), float(d["fundingRate"])) for d in data]

    def fetch_oi_history(self, symbol, period="1h", limit=500, market_type="perp"):
        """Return [(timestamp_ms, sum_open_interest), ...] ascending (~30d retention)."""
        sym = self.normalize_symbol(symbol, market_type)
        url = (f"{_FAPI}/futures/data/openInterestHist"
               f"?symbol={sym}&period={period}&limit={limit}")
        data = http_get_json(url)
        return [(int(d["timestamp"]), float(d["sumOpenInterest"])) for d in data]

    def _native_order(self, intent: OrderIntent) -> dict:
        # Binance Futures order params (USDM). Spot omits positionSide/leverage.
        p = {
            "symbol": self.normalize_symbol(intent.symbol, intent.market_type),
            "side": intent.side.upper(),
            "type": "MARKET" if intent.order_type == "market" else "LIMIT",
        }
        if intent.qty is not None:
            p["quantity"] = intent.qty
        if intent.quote_qty is not None and intent.market_type == "spot":
            p["quoteOrderQty"] = intent.quote_qty
        if intent.order_type == "limit":
            p["price"] = intent.price
            p["timeInForce"] = "GTC"
        if intent.reduce_only and intent.market_type == "perp":
            p["reduceOnly"] = True
        if intent.client_id:
            p["newClientOrderId"] = intent.client_id
        return p
