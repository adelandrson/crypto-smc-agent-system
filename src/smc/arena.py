"""Dry-run broker DB-backed — posisi dibuka LANGSUNG (market-fill+slippage) saat sinyal
full_strong, sama seperti paper/broker.py sumber (metodologi ini TAK punya konsep limit-order
pending seperti crypto-trader-agent-system — entry selalu di harga confluence TERKINI). TP
bertahap + evolusi SL dipersist ke SQL (DryRunTrade+DryRunFill) alih-alih in-memory dataclass,
supaya bisa ditampilkan web & bertahan lintas-restart — arsitektur operasional yang SAMA dengan
crypto-trader-agent-system (step()/monitor()/reset()/summary()), decision logic BEDA (confluence
FVG/SMC, bukan pattern-screening).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from src.smc.binance_adapter import BinanceAdapter
from src.smc.decide import GROUPS, decide
from src.smc.oi_tracker import OITracker
from src.smc.sentiment import aggregate_sentiment
from src.smc.session import session_ok
from src.storage.db import SessionLocal, init_db
from src.storage.models import DryRunFill, DryRunTrade, Token

START_EQUITY = 1000.0
TAKER_FEE = 0.00055    # sama persis dgn paper/broker.py PaperBroker default
SLIPPAGE = 0.0002      # 2 bps, sama persis
MIN_CANDLES = 60


def _now():
    return datetime.now(timezone.utc)


def _agent(group: str) -> str:
    return f"Wira·{group}"


def _fee(price: float, qty: float) -> float:
    return abs(price * qty) * TAKER_FEE


def equity(group: str, s) -> float:
    rows = s.scalars(select(DryRunTrade.realized_pnl_usd).where(
        DryRunTrade.agent == _agent(group), DryRunTrade.status == "closed")).all()
    open_fees = s.scalars(select(DryRunTrade.realized_pnl_usd).where(
        DryRunTrade.agent == _agent(group), DryRunTrade.status == "open")).all()  # entry fee sudah tercatat negatif
    return START_EQUITY + sum(r or 0.0 for r in rows) + sum(r or 0.0 for r in open_fees)


def open_count(group: str, s) -> int:
    return s.scalar(select(func.count()).select_from(DryRunTrade).where(
        DryRunTrade.agent == _agent(group), DryRunTrade.status == "open")) or 0


def universe_symbols(s, limit: int = 200) -> list[str]:
    rows = s.scalars(select(Token.symbol).where(Token.in_watchlist.is_(True))
                     .order_by(Token.market_cap.desc()).limit(limit)).all()
    return list(rows)


# ── buka posisi ──────────────────────────────────────────────────────────────
def open_trade(s, group: str, symbol: str, d: dict) -> DryRunTrade:
    """d = decide() 'open' action dict. Fill disimulasikan dgn slippage+fee (sama persis
    formula paper/broker.py PaperBroker.open)."""
    direction = d["direction"]
    fill = d["entry"] * (1 + direction * SLIPPAGE)
    fee = _fee(fill, d["qty"])
    tr = DryRunTrade(
        agent=_agent(group), group=group, symbol=symbol, leg=("long" if direction > 0 else "short"),
        status="open", entry_ts=_now(), entry=fill, sl=d["sl"],
        original_qty=d["qty"], qty_remaining=d["qty"], leverage=d["leverage"],
        risk_frac=d["risk_frac"], risk_usd=d["risk_usd"], margin_usd=d["margin_usd"],
        tps=json.dumps(d["tps"]), full_score=d["full_score"], zone=d["zone"],
        high_confluence=d["high_confluence"], fr_score=d.get("fr_score"),
        oi_score=d.get("oi_score"), lsr_score=d.get("lsr_score"),
        realized_pnl_usd=-fee,
    )
    s.add(tr)
    s.commit()
    return tr


# ── kelola posisi terbuka (TP bertahap + evolusi SL, per bar) ────────────────
def _apply_sl_after(tr: DryRunTrade, tp: dict, close: float, direction: int) -> None:
    """Evolusi SL sesuai metadata sl_after tiap TP (skill B3: BE -> lock-TP1 -> trailing) —
    sama persis paper/broker.py sumber `_apply_sl_after`, termasuk trail LANGSUNG dievaluasi
    thd `close` bar ini juga (bukan nunggu bar berikutnya)."""
    sa = tp.get("sl_after") or {}
    mode = sa.get("mode")
    if mode == "be":
        tr.sl = tr.entry
    elif mode == "lock":
        tps = json.loads(tr.tps)
        lock_tp = next((t for t in tps if t["label"] == sa.get("lock_label")), None)
        if lock_tp and lock_tp.get("price") is not None:
            tr.sl = lock_tp["price"]
    elif mode == "trail":
        # ASSIGNMENT (bukan scan/first-match) -- TP trail TERBARU yg fill selalu menang,
        # sama persis semantik `pos.trail = value` di sumber. SL langsung diratchet jg (bukan
        # nunggu bar berikutnya) -- dulu porting-ku kelewat ini, ketauan dari test moonbag.
        tr.trail = sa.get("value", 0.05)
        tr.sl = max(tr.sl, close * (1 - tr.trail)) if direction > 0 else min(tr.sl, close * (1 + tr.trail))


def manage_position(s, tr: DryRunTrade, high: float, low: float, close: float) -> list[str]:
    """Proses TP/SL 1 posisi terhadap 1 bar (high/low/close). Return event strings."""
    direction = 1 if tr.leg == "long" else -1
    tps = json.loads(tr.tps)
    events: list[str] = []
    changed = False

    # 1. ratchet trailing SL dari trail TERAKTIF (tr.trail — field, bukan scan tps; lihat _apply_sl_after)
    if tr.trail:
        tr.sl = max(tr.sl, close * (1 - tr.trail)) if direction > 0 else min(tr.sl, close * (1 + tr.trail))

    # 2. take-profit bertahap (urut, skip moonbag -- tanpa harga fixed)
    for tp in tps:
        if tp["filled"] or tr.qty_remaining <= 1e-12:
            continue
        px = tp.get("price")
        if px is None:
            continue
        hit = (direction > 0 and high >= px) or (direction < 0 and low <= px)
        if not hit:
            continue
        q = min(tr.qty_remaining, tr.original_qty * tp["frac"])
        fill_px = px * (1 - direction * SLIPPAGE)
        pnl = (fill_px - tr.entry) * direction * q - _fee(fill_px, q)
        tr.realized_pnl_usd = (tr.realized_pnl_usd or 0.0) + pnl
        tr.qty_remaining -= q
        tp["filled"] = True
        changed = True
        s.add(DryRunFill(trade_id=tr.id, label=tp["label"], price=round(fill_px, 8),
                          qty=round(q, 10), pnl_usd=round(pnl, 4), ts=_now()))
        events.append(f"{tr.symbol} {tp['label']} hit @ {fill_px:.6g} ({pnl:+.2f}$)")
        _apply_sl_after(tr, tp, close, direction)   # bisa set tr.trail (assignment, latest wins)

    # 3. stop-loss pada sisa qty (moonbag keluar lewat trailing SL di sini juga)
    if tr.qty_remaining > 1e-12:
        sl_hit = (direction > 0 and low <= tr.sl) or (direction < 0 and high >= tr.sl)
        if sl_hit:
            mb = next((t for t in tps if t.get("price") is None and not t["filled"]), None)
            reason = "moonbag" if mb else "SL"
            if mb:
                mb["filled"] = True
                changed = True
            fill_px = tr.sl * (1 - direction * SLIPPAGE)
            pnl = (fill_px - tr.entry) * direction * tr.qty_remaining - _fee(fill_px, tr.qty_remaining)
            tr.realized_pnl_usd = (tr.realized_pnl_usd or 0.0) + pnl
            s.add(DryRunFill(trade_id=tr.id, label=reason, price=round(fill_px, 8),
                              qty=round(tr.qty_remaining, 10), pnl_usd=round(pnl, 4), ts=_now()))
            events.append(f"{tr.symbol} {reason} hit @ {fill_px:.6g} ({pnl:+.2f}$)")
            tr.qty_remaining = 0.0
            changed = True

    if tr.qty_remaining <= 1e-12 and tr.status == "open":
        tr.status = "closed"
        tr.closed_at = _now()
        all_tp_filled = all(t["filled"] for t in tps if t.get("price") is not None)
        moonbag_filled = any(t["filled"] for t in tps if t.get("price") is None)
        tr.outcome = "moonbag" if moonbag_filled else ("tp_full" if all_tp_filled else "sl")
        tr.r_multiple = round(tr.realized_pnl_usd / tr.risk_usd, 3) if tr.risk_usd else None
    if changed:
        tr.tps = json.dumps(tps)
    return events


def check_open(cli=None) -> list[str]:
    cli = cli or BinanceAdapter()
    events: list[str] = []
    with SessionLocal() as s:
        trades = s.scalars(select(DryRunTrade).where(DryRunTrade.status == "open")).all()
        for tr in trades:
            try:
                bars = cli.fetch_ohlcv(f"{tr.symbol}/USDT", GROUPS[tr.group]["tf"], limit=2, market_type="perp")
            except Exception as e:  # noqa: BLE001
                events.append(f"{tr.symbol}: fetch error {type(e).__name__}")
                continue
            if not bars:
                continue
            last = bars[-1]
            events += manage_position(s, tr, last[2], last[3], last[4])
        s.commit()
    return events


# ── screening (scan universe -> decide -> buka posisi baru) ──────────────────
def screen_place(cli=None, group: str = "scalp", symbols: list[str] | None = None) -> int:
    cli = cli or BinanceAdapter()
    init_db()
    oi_tracker = OITracker()
    cfg = GROUPS[group]
    placed = 0
    with SessionLocal() as s:
        syms = symbols or universe_symbols(s)
        eq = equity(group, s)
        for sym in syms:
            if open_count(group, s) >= cfg["max_open"]:
                break
            has_pos = s.scalar(select(func.count()).select_from(DryRunTrade).where(
                DryRunTrade.agent == _agent(group), DryRunTrade.symbol == sym, DryRunTrade.status == "open"))
            if has_pos:
                continue
            try:
                candles = cli.fetch_ohlcv(f"{sym}/USDT", cfg["tf"], limit=cfg["candle_limit"], market_type="perp")
                sent = aggregate_sentiment([cli], f"{sym}/USDT")
            except Exception:  # noqa: BLE001
                continue
            if not candles or len(candles) < MIN_CANDLES:
                continue
            oi_score = oi_tracker.score(sym, sent.get("total_open_interest"), candles[-1][4])
            now_dt = datetime.fromtimestamp(candles[-1][0] / 1000.0, tz=timezone.utc)
            if not session_ok(now_dt, cfg["mode"], allow_asia=False):
                continue
            d = decide(sym, candles, sent["fr_score"], oi_score, eq, cfg, lsr_score=sent.get("lsr_score", 0))
            if d["action"] == "open":
                open_trade(s, group, sym, d)
                placed += 1
                eq = equity(group, s)
    return placed


def step(symbols: list[str] | None = None) -> dict:
    """Siklus cron: (1) kelola posisi terbuka kedua gaya, (2) scan sinyal baru kedua gaya."""
    cli = BinanceAdapter()
    closed_events = check_open(cli)
    placed = {g: screen_place(cli, group=g, symbols=symbols) for g in GROUPS}
    print(f"[smc-arena {_now():%F %H:%M}] kelola: {len(closed_events)} event · pasang: "
          f"{'+'.join(f'{g}={n}' for g, n in placed.items())}")
    return {"closed_events": closed_events, "placed": placed}


def monitor(interval: int = 20):
    """Loop near-real-time (service) — cek TP/SL tiap `interval` detik; screening baru tiap step()."""
    while True:
        try:
            step()
        except Exception as e:  # noqa: BLE001
            print(f"[smc-arena monitor] error: {type(e).__name__}: {e}")
        time.sleep(max(5, interval))


def reset() -> dict:
    """RESET TOTAL dry-run kedua gaya: hapus SEMUA trade+fill, mulai ulang dari nol equity."""
    init_db()
    with SessionLocal() as s:
        n_fill = s.execute(DryRunFill.__table__.delete()).rowcount
        n_trade = s.execute(DryRunTrade.__table__.delete()).rowcount
        s.commit()
    return {"deleted_trades": int(n_trade or 0), "deleted_fills": int(n_fill or 0)}


def summary() -> list[dict]:
    """Ringkasan per-gaya: equity, expectancy(R rata2)/win-rate — expectancy JADI HEADLINE
    (bukan win-rate mentah), konsisten dgn temuan jujur AUDIT.md sumber (hit-rate<50% wajar,
    ekspektasi positif datang dari R:R bukan frekuensi menang)."""
    out = []
    with SessionLocal() as s:
        for g in GROUPS:
            closed = s.scalars(select(DryRunTrade).where(
                DryRunTrade.agent == _agent(g), DryRunTrade.status == "closed")).all()
            n = len(closed)
            wins = [t for t in closed if (t.realized_pnl_usd or 0) > 0]
            rs = [t.r_multiple for t in closed if t.r_multiple is not None]
            eq = equity(g, s)
            out.append({
                "group": g, "agent": _agent(g), "equity": round(eq, 2),
                "return_pct": round((eq / START_EQUITY - 1) * 100, 2),
                "open": open_count(g, s), "closed": n,
                "win_rate": round(len(wins) / n * 100, 1) if n else None,
                "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
                "leverage_range": f"{GROUPS[g]['lev_min']}-{GROUPS[g]['lev_max']}x",
                "max_open": GROUPS[g]["max_open"],
            })
    return out


def main(argv):
    init_db()
    if "reset" in argv:
        if "--yes" not in argv:
            print("RESET TOTAL dry-run (hapus SEMUA trade). Tambah --yes untuk konfirmasi.")
        else:
            r = reset()
            print(f"[reset] hapus {r['deleted_trades']} trade, {r['deleted_fills']} fill")
    elif "step" in argv:
        step()
    elif "monitor" in argv:
        iv = 20
        for a in argv:
            if a.startswith("--interval="):
                iv = int(a.split("=", 1)[1])
        monitor(interval=iv)
    else:
        for row in summary():
            print(f"[{row['group']:5}] ${row['equity']:.2f} ({row['return_pct']:+.1f}%) "
                  f"open={row['open']} closed={row['closed']} WR={row['win_rate']} "
                  f"E[R]={row['expectancy_r']} lev={row['leverage_range']}")


if __name__ == "__main__":
    main(sys.argv[1:])
