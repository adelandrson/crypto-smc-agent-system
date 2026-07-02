"""Klien minimal CoinMarketCap (free Basic tier).

Hemat kredit: satu panggilan listings/latest dengan market_cap_min server-side
(blueprint §2 — Basic hanya 15k credit/bln).
"""
import time

import requests

BASE_URL = "https://pro-api.coinmarketcap.com"
_RATE_LIMIT_CODES = {429, 1008, 1009, 1010, 1011}   # HTTP 429 / CMC error_code rate-limit


class CMCError(RuntimeError):
    pass


class CMCClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise CMCError("CMC_API_KEY kosong — isi di .env")
        self._session = requests.Session()
        self._session.headers.update(
            {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}
        )

    def _get(self, path, params, retries=3, backoff=3.0):
        """GET dgn retry/backoff pada rate-limit (HTTP 429 / error_code 1008-1011) & 5xx/koneksi."""
        for attempt in range(retries + 1):
            try:
                resp = self._session.get(f"{BASE_URL}{path}", params=params, timeout=30)
            except requests.RequestException as e:
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1)); continue
                raise CMCError(f"Network error: {e}")
            try:
                payload = resp.json()
            except ValueError:
                if resp.status_code >= 500 and attempt < retries:
                    time.sleep(backoff * (attempt + 1)); continue
                raise CMCError(f"Respons CMC bukan JSON (HTTP {resp.status_code})")
            code = (payload.get("status", {}) or {}).get("error_code")
            if (resp.status_code in _RATE_LIMIT_CODES or code in _RATE_LIMIT_CODES or resp.status_code >= 500):
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1)); continue
            if code:
                raise CMCError(f"CMC error {code}: {payload.get('status', {}).get('error_message')}")
            if not resp.ok:
                raise CMCError(f"HTTP {resp.status_code}")
            return payload.get("data", [])

    def listings_latest(self, market_cap_min: int, limit: int = 5000) -> list[dict]:
        """Listing terbaru di atas market_cap_min (USD).

        aux=platform,tags → wajib untuk filter chain Ethereum & exclude stablecoin.
        """
        params = {
            "start": 1,
            "limit": limit,
            "convert": "USD",
            "sort": "market_cap",
            "market_cap_min": market_cap_min,
            "aux": "platform,tags,circulating_supply",
        }
        return self._get("/v1/cryptocurrency/listings/latest", params)

    def info(self, ids: list) -> dict:
        """cryptocurrency/info by CMC ID (HINDARI kolisi simbol) → {id: {symbol, urls:{...}}}."""
        return self._get("/v1/cryptocurrency/info",
                         {"id": ",".join(str(i) for i in ids), "aux": "urls"}) or {}
