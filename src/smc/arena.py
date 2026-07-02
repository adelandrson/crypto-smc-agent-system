"""Dry-run broker DB-backed — LIMIT ORDER: sinyal full_strong memasang order PENDING di harga
retest zona imbalance (risk.limit_entry), lalu check_pending() mengisinya saat harga menyentuh
limit (long: low<=limit / short: high>=limit) atau membatalkannya (TTL habis / harga kabur).
Ini BEDA dari paper/broker.py sumber yg market-fill seketika — sesuai instruksi user "tentukan
harga limit order, bukan bermain market order". Setelah terisi (open), TP bertahap + evolusi SL
dipersist ke SQL (DryRunTrade+DryRunFill). Siklus operasional: check_pending()/check_open()/
screen_place() via step()/monitor()/reset()/summary(). Decision logic = confluence FVG/SMC.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import case, func, select

from src.smc.binance_adapter import BinanceAdapter
from src.smc.config_store import effective_groups
from src.smc.decide import GROUPS, decide
from src.smc.oi_tracker import OITracker
from src.smc.risk import fmt_price
from src.smc.sentiment import aggregate_sentiment
from src.smc.session import session_ok
from src.storage.db import SessionLocal, init_db
from src.storage.models import DryRunFill, DryRunTrade, SignalSnapshot, Token

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


def active_count(group: str, s) -> int:
    """Slot terpakai = pending (limit menunggu isi) + open. Cap max_open dihitung dari ini,
    supaya limit order yg belum terisi tetap memesan slot (tak over-place)."""
    return s.scalar(select(func.count()).select_from(DryRunTrade).where(
        DryRunTrade.agent == _agent(group), DryRunTrade.status.in_(("pending", "open")))) or 0


# Urutan tier-list S->A->B->C (koin tier atas dipindai/diisi lebih dulu), lalu volume 24h.
TIER_ORDER = case((Token.tier == "S", 0), (Token.tier == "A", 1),
                  (Token.tier == "B", 2), (Token.tier == "C", 3), else_=4)


def universe_symbols(s, limit: int = 200) -> list[str]:
    rows = s.scalars(select(Token.symbol).where(Token.in_watchlist.is_(True))
                     .order_by(TIER_ORDER, Token.volume_24h.desc().nullslast()).limit(limit)).all()
    return list(rows)


# ── pasang LIMIT order (pending) → fill on pullback → cancel ─────────────────
CANCEL_RUN = 0.02      # harga kabur >2% searah dari limit tanpa pullback -> batal (jangan chase)


def place_pending(s, group: str, symbol: str, d: dict, mark: float | None = None) -> DryRunTrade:
    """Pasang LIMIT order PENDING di harga d['entry'] (retest zona imbalance, dari
    risk.limit_entry). BELUM terisi, BELUM kena fee — menunggu harga menyentuh limit
    (lihat check_pending). Slot posisi (max_open) sudah terpakai sejak pending."""
    direction = d["direction"]
    now = _now()
    # entry_ts di-set = waktu pasang (placeholder) — bukan None — supaya kompatibel dgn tabel lama
    # yg kolom entry_ts-nya NOT NULL (SQLite tak bisa relax constraint via ALTER ADD COLUMN).
    # fill_pending menimpanya dgn waktu fill SEBENARNYA saat terisi. UI pending pakai placed_ts.
    tr = DryRunTrade(
        agent=_agent(group), group=group, symbol=symbol, leg=("long" if direction > 0 else "short"),
        status="pending", placed_ts=now, mark_price=mark, entry_ts=now, entry=d["entry"], sl=d["sl"],
        original_qty=d["qty"], qty_remaining=d["qty"], leverage=d["leverage"],
        risk_frac=d["risk_frac"], risk_usd=d["risk_usd"], margin_usd=d["margin_usd"],
        tps=json.dumps(d["tps"]), full_score=d["full_score"], zone=d["zone"],
        high_confluence=d["high_confluence"], fr_score=d.get("fr_score"),
        oi_score=d.get("oi_score"), lsr_score=d.get("lsr_score"),
        realized_pnl_usd=0.0,
    )
    s.add(tr)
    s.commit()
    return tr


def fill_pending(s, tr: DryRunTrade) -> str:
    """Limit terisi: pending -> open. Fill TEPAT di harga limit (maker, TANPA slippage —
    justru keunggulan limit vs market), potong fee entry saat itu."""
    fee = _fee(tr.entry, tr.qty_remaining)
    tr.status = "open"
    tr.entry_ts = _now()
    tr.realized_pnl_usd = (tr.realized_pnl_usd or 0.0) - fee
    return f"{tr.symbol} LIMIT {tr.leg} terisi @ {fmt_price(tr.entry)}"


def cancel_pending(s, tr: DryRunTrade, reason: str) -> str:
    tr.status = "canceled"
    tr.outcome = "canceled"
    tr.closed_at = _now()
    return f"{tr.symbol} LIMIT {tr.leg} batal — {reason}"


def open_market(s, group: str, symbol: str, d: dict, mark: float | None = None) -> DryRunTrade:
    """Entry MARKET (order_type='market'): harga kini SUDAH di zona entry -> isi SEKETIKA di harga
    pasar dgn slippage TAKER (bukan menunggu pullback). status=open langsung, fee taker dipotong."""
    direction = d["direction"]
    fill = d["entry"] * (1 + direction * SLIPPAGE)   # slippage adverse (taker fill)
    fee = _fee(fill, d["qty"])
    now = _now()
    tr = DryRunTrade(
        agent=_agent(group), group=group, symbol=symbol, leg=("long" if direction > 0 else "short"),
        status="open", placed_ts=now, mark_price=mark, entry_ts=now, entry=fill, sl=d["sl"],
        original_qty=d["qty"], qty_remaining=d["qty"], leverage=d["leverage"],
        risk_frac=d["risk_frac"], risk_usd=d["risk_usd"], margin_usd=d["margin_usd"],
        tps=json.dumps(d["tps"]), full_score=d["full_score"], zone=d["zone"],
        high_confluence=d["high_confluence"], fr_score=d.get("fr_score"),
        oi_score=d.get("oi_score"), lsr_score=d.get("lsr_score"), realized_pnl_usd=-fee,
    )
    s.add(tr)
    s.commit()
    return tr


def open_trade(s, group: str, symbol: str, d: dict, mark: float | None = None) -> DryRunTrade:
    """Konvenien: pasang pending LALU langsung isi (fill seketika di harga limit). Dipakai
    saat entry ingin dieksekusi tanpa menunggu (mis. test, atau harga sudah di zona)."""
    tr = place_pending(s, group, symbol, d, mark=mark)
    fill_pending(s, tr)
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
        events.append(f"{tr.symbol} {tp['label']} hit @ {fmt_price(fill_px)} ({pnl:+.2f}$)")
        _apply_sl_after(tr, tp, close, direction)   # bisa set tr.trail (assignment, latest wins)

    # 2b. fase moonbag — begitu SEMUA TP berharga terisi, terapkan trail moonbag SENDIRI. Moonbag
    # (price=None) tak pernah masuk loop fill, jadi sl_after-nya tak pernah kepasang -> sisa posisi
    # diam-diam mewarisi trail TP terakhir. No-op di preset kita (swing TP4==moonbag==8%; scalp tak
    # ada moonbag); menutup footgun sama spt fix upstream paper/broker.py (AUDIT.md §H sumber).
    if tr.qty_remaining > 1e-12 and not any(t.get("price") is not None and not t["filled"] for t in tps):
        mb = next((t for t in tps if t.get("price") is None and not t["filled"]), None)
        sa = (mb or {}).get("sl_after") or {}
        v = sa.get("value")
        if sa.get("mode") == "trail" and v is not None and tr.trail != v:
            tr.trail = v
            tr.sl = max(tr.sl, close * (1 - v)) if direction > 0 else min(tr.sl, close * (1 + v))
            changed = True

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
            events.append(f"{tr.symbol} {reason} hit @ {fmt_price(fill_px)} ({pnl:+.2f}$)")
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


def check_pending(cli=None) -> list[str]:
    """Untuk tiap LIMIT order PENDING: fetch bar terbaru, ISI bila harga menyentuh limit
    (long: low<=limit, short: high>=limit), BATALKAN bila TTL habis atau harga kabur searah
    >CANCEL_RUN tanpa pullback (jangan chase). Commit per-order (hindari lock spt check_open)."""
    cli = cli or BinanceAdapter()
    events: list[str] = []
    with SessionLocal() as s:
        ids = [tid for tid, in s.execute(
            select(DryRunTrade.id).where(DryRunTrade.status == "pending")).all()]
    for tid in ids:
        try:
            with SessionLocal() as s:
                tr = s.get(DryRunTrade, tid)
                if not tr or tr.status != "pending":
                    continue
                cfg = effective_groups().get(tr.group, {})
                mkt = cfg.get("data_market_type", "perp")
                try:
                    bars = cli.fetch_ohlcv(f"{tr.symbol}/USDT", cfg.get("tf", "5m"), limit=2, market_type=mkt)
                except Exception as e:  # noqa: BLE001
                    events.append(f"{tr.symbol}: fetch error {type(e).__name__}")
                    continue
                if not bars:
                    continue
                direction = 1 if tr.leg == "long" else -1
                high, low, close = bars[-1][2], bars[-1][3], bars[-1][4]
                touched = (direction > 0 and low <= tr.entry) or (direction < 0 and high >= tr.entry)
                if touched:
                    events.append(fill_pending(s, tr)); s.commit(); continue
                ttl_h = cfg.get("pending_ttl_h", 24)
                run = cfg.get("cancel_run", CANCEL_RUN)
                age_h = (_now() - tr.placed_ts).total_seconds() / 3600.0 if tr.placed_ts else 0.0
                ran = (direction > 0 and close > tr.entry * (1 + run)) or \
                      (direction < 0 and close < tr.entry * (1 - run))
                if age_h >= ttl_h:
                    events.append(cancel_pending(s, tr, f"TTL {ttl_h}h lewat")); s.commit()
                elif ran:
                    events.append(cancel_pending(s, tr, f"harga kabur >{run*100:.1f}%")); s.commit()
        except Exception as e:  # noqa: BLE001
            events.append(f"pending {tid}: error {type(e).__name__}")
    return events


def check_open(cli=None) -> list[str]:
    """Commit PER-POSISI (bukan 1 transaksi raksasa di akhir) -- posisi lain butuh scan
    (screen_place, dry-run cron lain) BISA menulis DB bersamaan tanpa 'database is locked'
    (ditemukan via live smoke test: 1 sesi lama menahan write-lock sepanjang scan network)."""
    cli = cli or BinanceAdapter()
    events: list[str] = []
    trade_ids = []
    with SessionLocal() as s:
        trade_ids = [tid for tid, in s.execute(
            select(DryRunTrade.id).where(DryRunTrade.status == "open")).all()]
    for tid in trade_ids:
        try:
            bars_fetched = None
            with SessionLocal() as s:
                tr = s.get(DryRunTrade, tid)
                if not tr or tr.status != "open":
                    continue
                _cfg = effective_groups().get(tr.group, GROUPS.get(tr.group, {}))
                try:
                    bars_fetched = cli.fetch_ohlcv(f"{tr.symbol}/USDT", _cfg.get("tf", "5m"),
                                                   limit=2, market_type=_cfg.get("data_market_type", "perp"))
                except Exception as e:  # noqa: BLE001
                    events.append(f"{tr.symbol}: fetch error {type(e).__name__}")
                    continue
                if not bars_fetched:
                    continue
                last = bars_fetched[-1]
                events += manage_position(s, tr, last[2], last[3], last[4])
                s.commit()
        except Exception as e:  # noqa: BLE001
            events.append(f"trade {tid}: error {type(e).__name__}")
    return events


# ── screening (scan universe -> decide -> buka posisi baru) ──────────────────
def _snapshot(s, group: str, sym: str, d: dict) -> None:
    """Simpan hasil decide() (open ATAU skip) ke SignalSnapshot — isi halaman Sinyal +
    dasar skill screening_highlights. Ditulis utk SEMUA simbol yg dievaluasi (bukan cuma
    yg dibuka), termasuk alasan skip -- transparansi penuh (SOUL.md: no green theatre)."""
    c = d.get("confluence") or {}
    tps = d.get("tps")
    s.add(SignalSnapshot(
        ts=_now(), symbol=sym, group=group,
        full_score=d.get("full_score", c.get("full_score", 0)),
        full_strong=bool(c.get("full_strong", d["action"] == "open")),
        high_confluence=bool(d.get("high_confluence", c.get("high_confluence", False))),
        confirmed=bool(c.get("confirmed", False)),
        zone=d.get("zone", c.get("zone")),
        direction=d.get("direction"),
        entry=d.get("entry"), sl=d.get("sl"),
        tps_json=json.dumps(tps) if tps else None,
        reason=None if d["action"] == "open" else (d.get("reason") or "")[:120],
        detail_json=json.dumps(c, default=str)[:6000] if c else None,
    ))


def screen_place(cli=None, group: str = "scalp", symbols: list[str] | None = None) -> int:
    """Scan universe (atau `symbols`) utk 1 gaya: decide() + SIMPAN snapshot semua hasil
    (open/skip, dgn alasan), buka posisi baru bila full_strong & lolos filter & masih ada
    slot (max_open). Scan TERUS berjalan meski slot penuh -- snapshot tetap informatif.

    Sesi DB dibuka PER-SIMBOL (bukan 1 sesi raksasa utk seluruh scan) -- scan network
    (fetch_ohlcv+sentiment per simbol) bisa lama utk universe besar; 1 sesi panjang menahan
    write-lock SQLite sepanjang itu, bikin writer lain (screen_place gaya lain, check_open,
    endpoint web/chat/rnd_step) gagal 'database is locked'. Ditemukan via live smoke test."""
    cli = cli or BinanceAdapter()
    init_db()
    oi_tracker = OITracker()
    cfg = effective_groups()[group]        # knob metodologi/leverage/data yg bisa disetel agen
    mkt = cfg.get("data_market_type", "perp")
    placed = 0
    with SessionLocal() as s:
        syms = symbols or universe_symbols(s)
    for sym in syms:
        try:
            candles = cli.fetch_ohlcv(f"{sym}/USDT", cfg["tf"], limit=cfg["candle_limit"], market_type=mkt)
            sent = aggregate_sentiment([cli], f"{sym}/USDT")
        except Exception:  # noqa: BLE001
            continue
        if not candles or len(candles) < MIN_CANDLES:
            continue
        now_dt = datetime.fromtimestamp(candles[-1][0] / 1000.0, tz=timezone.utc)
        if not session_ok(now_dt, cfg["mode"], allow_asia=False):
            continue
        with SessionLocal() as s:
            has_pos = s.scalar(select(func.count()).select_from(DryRunTrade).where(
                DryRunTrade.agent == _agent(group), DryRunTrade.symbol == sym,
                DryRunTrade.status.in_(("pending", "open"))))   # skip bila sudah ada pending/open utk simbol ini
            if has_pos:
                s.commit()
                continue
            eq = equity(group, s)
            oi_score = oi_tracker.score(sym, sent.get("total_open_interest"), candles[-1][4])
            d = decide(sym, candles, sent["fr_score"], oi_score, eq, cfg, lsr_score=sent.get("lsr_score", 0))
            _snapshot(s, group, sym, d)
            # slot dari active (pending+open). Entry FLEKSIBEL: market=isi seketika, limit=pending
            if d["action"] == "open" and active_count(group, s) < cfg["max_open"]:
                if d.get("order_type") == "market":
                    open_market(s, group, sym, d, mark=candles[-1][4])
                else:
                    place_pending(s, group, sym, d, mark=candles[-1][4])
                placed += 1
            s.commit()
    return placed


def step(symbols: list[str] | None = None) -> dict:
    """Siklus cron: (1) isi/batalkan LIMIT order pending, (2) kelola posisi terbuka, (3) scan
    sinyal baru → pasang limit order baru. Urutan penting: pending dulu (mungkin jadi open),
    lalu kelola open, lalu scan (slot dihitung setelah pending diproses)."""
    cli = BinanceAdapter()
    pending_events = check_pending(cli)
    closed_events = check_open(cli)
    placed = {g: screen_place(cli, group=g, symbols=symbols) for g in GROUPS}
    print(f"[smc-arena {_now():%F %H:%M}] pending: {len(pending_events)} · kelola: "
          f"{len(closed_events)} event · pasang: {'+'.join(f'{g}={n}' for g, n in placed.items())}")
    return {"pending_events": pending_events, "closed_events": closed_events, "placed": placed}


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
