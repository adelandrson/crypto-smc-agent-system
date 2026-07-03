"""Universe builder — CMC mcap>=$300M, exclude stablecoin/gold-index/derivative,
Binance-perp-tradable. TIER TERPISAH per gaya: scalp (mcap40/vol60) & swing (mcap60/vol40),
rank-percentile → kuartil S/A/B/C. Jalankan: python -m src.smc.universe
"""
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from src import config
from src.adapters.cmc import CMCClient
from src.smc.base import http_get_json
from src.storage.db import SessionLocal, init_db
from src.storage.models import Token

_FAPI_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"


def binance_perp_bases() -> set[str]:
    """Base asset (mis. 'BTC') utk semua kontrak PERPETUAL/USDT TRADING di Binance."""
    data = http_get_json(_FAPI_EXCHANGE_INFO)
    return {s["baseAsset"] for s in data.get("symbols", [])
            if s.get("quoteAsset") == "USDT" and s.get("contractType") == "PERPETUAL"
            and s.get("status") == "TRADING"}


def _exclude_reason(coin: dict) -> str | None:
    """None bila layak ditrack; selain itu alasan dikecualikan. Sama persis dgn logika
    crypto-trader-agent-system (src/phase0/seed_watchlist.py:_exclude_reason)."""
    tags = {t.lower() for t in (coin.get("tags") or [])}
    symbol = (coin.get("symbol") or "").upper()
    if "stablecoin" in tags or symbol in config.STABLECOIN_DENYLIST:
        return "stablecoin"
    if any(marker in symbol for marker in config.FIAT_MARKERS):
        return "stablecoin"
    tag_hit = tags & config.EXCLUDED_TAGS
    if tag_hit:
        return sorted(tag_hit)[0]           # incl. "tokenized-gold" (mis. PAXG/XAUT — "GOLD index")
    if symbol in config.DERIVATIVE_DENYLIST:
        return "derivative"
    return None


def _tier(volume_24h: float | None) -> str | None:
    if not volume_24h:
        return None
    for t, floor in sorted(config.TIER_THRESHOLDS.items(), key=lambda kv: -kv[1]):
        if volume_24h >= floor:
            return t
    return None   # di bawah tier C -> tak ditier (bisa disimpan tapi tak aktif ditrading)


def _rank_pct(values: list) -> dict:
    """Rank-percentile 0..1 per indeks (1 = tertinggi). Robust thd outlier BTC."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = len(values)
    return {idx: (rank + 1) / n if n else 0.0 for rank, idx in enumerate(order)}


def _quartile_tier(rank: int, n: int) -> str:
    q = rank / n if n else 1.0
    return "S" if q < 0.25 else ("A" if q < 0.50 else ("B" if q < 0.75 else "C"))


def _assign_dual_tiers(rows: list):
    """Tier TERPISAH per gaya (spec final): SCALP 0.4*mcap+0.6*vol, SWING 0.6*mcap+0.4*vol.
    Normalisasi rank-percentile, tier = kuartil skor. Set scalp_tier/swing_tier/scores tiap token."""
    if not rows:
        return
    mcap_pct = _rank_pct([(t.market_cap or 0) for t in rows])
    vol_pct = _rank_pct([(t.volume_24h or 0) for t in rows])
    for w_mcap, w_vol, tier_attr, score_attr in ((0.40, 0.60, "scalp_tier", "scalp_score"),
                                                  (0.60, 0.40, "swing_tier", "swing_score")):
        scored = [(i, round(w_mcap * mcap_pct[i] + w_vol * vol_pct[i], 4)) for i in range(len(rows))]
        for i, sc in scored:
            setattr(rows[i], score_attr, sc)
        for rank, (i, _sc) in enumerate(sorted(scored, key=lambda t: -t[1])):
            setattr(rows[i], tier_attr, _quartile_tier(rank, len(rows)))


def build() -> dict:
    init_db()
    client = CMCClient(config.CMC_API_KEY)
    coins = client.listings_latest(market_cap_min=config.MARKETCAP_FLOOR)
    perp_bases = binance_perp_bases()

    now = datetime.now(timezone.utc)
    kept = 0
    excluded = Counter()
    tiers = Counter()

    with SessionLocal() as session:
        for coin in coins:
            usd = (coin.get("quote") or {}).get("USD") or {}
            mcap = usd.get("market_cap")
            if not mcap or mcap < config.MARKETCAP_FLOOR:
                continue
            symbol = (coin.get("symbol") or "").upper()
            reason = _exclude_reason(coin)
            tradable = symbol in perp_bases

            token = session.get(Token, coin["id"]) or Token(token_id=coin["id"])
            token.symbol = symbol
            token.name = coin.get("name")
            token.market_cap = mcap
            token.volume_24h = usd.get("volume_24h")
            token.percent_change_24h = usd.get("percent_change_24h")
            token.cmc_rank = coin.get("cmc_rank")
            token.exclude_reason = reason
            token.tradable = tradable
            # in_watchlist = layak jadi kandidat trading: tak dikecualikan & ada di Binance perp
            token.in_watchlist = reason is None and tradable
            token.last_seen = now
            session.add(token)

            if reason is not None:
                excluded[reason] += 1
            elif not tradable:
                excluded["not_binance_perp"] += 1
            else:
                kept += 1

        # TIER TERPISAH scalp/swing dihitung LINTAS seluruh watchlist (rank-percentile) — bukan per-token
        session.flush()
        wl = session.scalars(select(Token).where(Token.in_watchlist.is_(True))).all()
        _assign_dual_tiers(wl)
        for t in wl:
            t.tier = t.swing_tier          # legacy field = swing_tier
            tiers[t.swing_tier or "unranked"] += 1
        for t in session.scalars(select(Token).where(Token.in_watchlist.is_(False))).all():
            t.tier = t.scalp_tier = t.swing_tier = None
        session.commit()

    breakdown = " | ".join(f"{r}: {n}" for r, n in excluded.most_common()) or "-"
    tier_breakdown = " | ".join(f"{t}: {n}" for t, n in sorted(tiers.items()))
    print(f"Universe diperbarui -> {kept} koin (mcap>=${config.MARKETCAP_FLOOR:,}, Binance-perp-tradable)\n"
          f"  Tier: {tier_breakdown}\n  Dikecualikan: {breakdown}")
    return {"kept": kept, "excluded": dict(excluded), "tiers": dict(tiers)}


if __name__ == "__main__":
    build()
