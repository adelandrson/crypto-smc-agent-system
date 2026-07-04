"""Data pasar dengan FALLBACK lintas bursa (ccxt): Binance (REST langsung) → Bybit → OKX.

Saat Binance mem-block IP / down, otomatis pindah ke bursa lain supaya sistem tetap jalan (kejadian
nyata: scan agresif memicu IP-ban Binance → seluruh data mati). Bybit & OKX diakses via **ccxt**
(format OHLCV identik `[ts,o,h,l,c,v]`). LSR & taker-buy Binance-spesifik → degradasi netral (None)
saat fallback — confluence tetap jalan dari FVG/Fib/OI/FR. Drop-in pengganti BinanceAdapter.
"""
from __future__ import annotations

import time as _time

from src.smc.binance_adapter import BinanceAdapter

_FALLBACKS = ("bybit", "okx")     # urutan fallback saat Binance gagal

# CIRCUIT-BREAKER per-host (termasuk ccxt) — saat SEMUA bursa down, request berikutnya GAGAL-CEPAT
# (tak menunggu timeout 8s×3). Setelah 1 kegagalan, host di-skip `_CB_COOLDOWN` detik.
_CB: dict = {}
_CB_COOLDOWN = 45.0


def _cb_open(host: str) -> bool:
    return _CB.get(host, 0.0) > _time.monotonic()


def _cb_note(host: str, ok: bool) -> None:
    if ok:
        _CB.pop(host, None)
    else:
        _CB[host] = _time.monotonic() + _CB_COOLDOWN


class FallbackAdapter:
    name = "binance+fallback"
    execution_skill = "binance-skills-hub"

    def __init__(self):
        self.binance = BinanceAdapter()
        self._cx: dict = {}

    def _ex(self, name):
        """Instans ccxt (lazy) — perp swap, rate-limit aktif, timeout pendek."""
        if name not in self._cx:
            import ccxt
            self._cx[name] = getattr(ccxt, name)({
                "enableRateLimit": True, "timeout": 5000,
                "options": {"defaultType": "swap"}})
        return self._cx[name]

    @staticmethod
    def _sym(symbol: str) -> str:
        base = symbol.split("/")[0].upper()
        return f"{base}/USDT:USDT"     # perp swap settle USDT (format ccxt Bybit/OKX)

    def normalize_symbol(self, canonical, market_type="perp"):
        return self.binance.normalize_symbol(canonical, market_type)

    def map_timeframe(self, tf):
        return self.binance.map_timeframe(tf)

    # ── OHLCV (paling kritis) ──
    def fetch_ohlcv(self, symbol, timeframe="1h", limit=200, market_type="perp"):
        if not _cb_open("binance"):
            try:
                r = self.binance.fetch_ohlcv(symbol, timeframe, limit, market_type)
                _cb_note("binance", True)
                return r
            except Exception:  # noqa: BLE001
                _cb_note("binance", False)
        for nm in _FALLBACKS:
            if _cb_open(nm):
                continue
            try:
                o = self._ex(nm).fetch_ohlcv(self._sym(symbol), timeframe, limit=limit)
                if o and len(o) >= 2:
                    _cb_note(nm, True)
                    return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                             float(k[4]), float(k[5])] for k in o]
            except Exception:  # noqa: BLE001
                _cb_note(nm, False)
        raise RuntimeError("semua bursa tak terjangkau (data sementara tak tersedia)")

    # ── funding (fallback ke ccxt) ──
    def fetch_funding(self, symbol, market_type="perp"):
        if market_type == "spot":
            return None
        if not _cb_open("binance"):
            try:
                return self.binance.fetch_funding(symbol, market_type)
            except Exception:  # noqa: BLE001
                _cb_note("binance", False)
        for nm in _FALLBACKS:
            if _cb_open(nm):
                continue
            try:
                fr = self._ex(nm).fetch_funding_rate(self._sym(symbol))
                if fr and fr.get("fundingRate") is not None:
                    return float(fr["fundingRate"])
            except Exception:  # noqa: BLE001
                _cb_note(nm, False)
        return None

    # ── open interest (fallback ke ccxt) ──
    def fetch_open_interest(self, symbol, market_type="perp"):
        if market_type == "spot":
            return None
        if not _cb_open("binance"):
            try:
                return self.binance.fetch_open_interest(symbol, market_type)
            except Exception:  # noqa: BLE001
                _cb_note("binance", False)
        for nm in _FALLBACKS:
            if _cb_open(nm):
                continue
            try:
                oi = self._ex(nm).fetch_open_interest(self._sym(symbol)) or {}
                v = oi.get("openInterestAmount") or oi.get("openInterestValue")
                if v is not None:
                    return float(v)
            except Exception:  # noqa: BLE001
                _cb_note(nm, False)
        return None

    # ── LSR & taker-buy: Binance-spesifik → degradasi netral saat fallback ──
    def fetch_long_short_ratio(self, symbol, market_type="perp"):
        try:
            return self.binance.fetch_long_short_ratio(symbol, market_type)
        except Exception:  # noqa: BLE001
            return None

    def fetch_taker_buy_volume(self, symbol, timeframe="1h", limit=200, market_type="perp"):
        try:
            return self.binance.fetch_taker_buy_volume(symbol, timeframe, limit, market_type)
        except Exception:  # noqa: BLE001
            return None

    # ── seri historis (backtest) — delegasi Binance ──
    def fetch_funding_history(self, symbol, limit=1000, market_type="perp"):
        return self.binance.fetch_funding_history(symbol, limit, market_type)

    def fetch_oi_history(self, symbol, period="1h", limit=500, market_type="perp"):
        return self.binance.fetch_oi_history(symbol, period, limit, market_type)

    # ── harga mark SEMUA perp (utk _live_prices) dgn fallback ──
    def all_prices(self) -> dict:
        """Return {SYMBOL_no_slash: price} mis. {'BTCUSDT': 61500.0}. Binance ticker/price →
        fallback ccxt Bybit/OKX fetch_tickers."""
        from src.smc.base import http_get_json
        if not _cb_open("binance"):
            try:
                rows = http_get_json("https://fapi.binance.com/fapi/v1/ticker/price", timeout=4.0)
                out = {r["symbol"]: float(r["price"]) for r in rows
                       if str(r.get("symbol", "")).endswith("USDT")}
                if out:
                    _cb_note("binance", True)
                    return out
            except Exception:  # noqa: BLE001
                _cb_note("binance", False)
        for nm in _FALLBACKS:
            if _cb_open(nm):
                continue
            try:
                tk = self._ex(nm).fetch_tickers()
                out = {}
                for sym, t in tk.items():
                    if sym.endswith("/USDT:USDT"):
                        base = sym.split("/")[0]
                        px = t.get("last") or t.get("close")
                        if px:
                            out[f"{base}USDT"] = float(px)
                if out:
                    _cb_note(nm, True)
                    return out
            except Exception:  # noqa: BLE001
                _cb_note(nm, False)
        return {}
