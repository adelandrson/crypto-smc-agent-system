"""Test src/smc/arena.py — broker DB-backed (open_trade/manage_position/equity/reset).
In-memory SQLite, tanpa network (screen_place/check_open/step diuji live terpisah)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.smc import arena
from src.smc.decide import GROUPS
from src.smc.risk import tp_targets
from src.storage.models import Base, DryRunFill, DryRunTrade, Token


def _mk_session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)


LONG_DECIDE = {
    "action": "open", "direction": 1, "entry": 100.0, "sl": 95.0, "qty": 2.0,
    "leverage": 20, "margin_usd": 10.0, "risk_usd": 10.0, "risk_frac": 0.01,
    "tps": tp_targets(1, 100.0, 95.0, mode="scalp"),
    "full_score": 3, "zone": "discount", "high_confluence": False,
    "fr_score": 1, "oi_score": 1, "lsr_score": 1,
}


class _FakeCli:
    """cli palsu utk check_pending: fetch_ohlcv selalu balikkan bar yg sama."""
    def __init__(self, bar):
        self._bar = bar

    def fetch_ohlcv(self, symbol, tf, limit=2, market_type="perp"):
        return [self._bar, self._bar]


def test_universe_symbols_ordered_by_tier_then_volume():
    """Universe dipindai urut tier GAYA S->A->B->C, lalu volume desc. Tier scalp vs swing terpisah."""
    Mk = _mk_session()
    with Mk() as s:
        s.add_all([
            Token(token_id=1, symbol="CCC", in_watchlist=True, scalp_tier="C", swing_tier="S", volume_24h=9e9),
            Token(token_id=2, symbol="SSS", in_watchlist=True, scalp_tier="S", swing_tier="C", volume_24h=10.0),
            Token(token_id=3, symbol="AAA", in_watchlist=True, scalp_tier="A", swing_tier="A", volume_24h=50.0),
            Token(token_id=4, symbol="SS2", in_watchlist=True, scalp_tier="S", swing_tier="C", volume_24h=99.0),
        ])
        s.commit()
        assert arena.universe_symbols(s, group="scalp") == ["SS2", "SSS", "AAA", "CCC"]   # by scalp_tier
        assert arena.universe_symbols(s, group="swing")[0] == "CCC"                        # by swing_tier (S)


def test_open_trade_persists_fields_and_deducts_fee():
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        assert tr.id is not None
        assert tr.status == "open" and tr.leg == "long" and tr.group == "scalp"
        assert tr.agent == "Wira·scalp"
        assert tr.qty_remaining == tr.original_qty == 2.0
        assert tr.entry == pytest.approx(LONG_DECIDE["entry"])   # LIMIT maker fill: TEPAT di limit, no slippage
        assert tr.realized_pnl_usd < 0                  # entry fee sudah dipotong
        assert json.loads(tr.tps)[0]["label"] == "TP1"


def test_place_pending_then_fill_on_touch(monkeypatch):
    """LIMIT order: pending -> terisi saat harga menyentuh limit (long: low<=limit)."""
    Mk = _mk_session()
    monkeypatch.setattr(arena, "SessionLocal", Mk)
    d = dict(LONG_DECIDE, entry=99.0, sl=95.0)         # limit @ 99, di bawah mark 100
    with Mk() as s:
        tr = arena.place_pending(s, "scalp", "BTC", d, mark=100.0)
        assert tr.status == "pending" and tr.entry_ts is not None   # = placed_ts (kompat tabel NOT NULL lama)
        placed_at = tr.entry_ts
        assert (tr.realized_pnl_usd or 0.0) == 0.0     # belum kena fee saat pending
    events = arena.check_pending(_FakeCli([0, 100.0, 100.5, 98.5, 99.5]))   # low 98.5 <= 99 -> touch
    assert any("terisi" in e for e in events)
    with Mk() as s:
        tr = s.scalars(select(DryRunTrade)).first()
        assert tr.status == "open" and tr.entry_ts is not None and tr.entry_ts >= placed_at
        assert tr.entry == pytest.approx(99.0)         # fill TEPAT di limit (maker)
        assert tr.realized_pnl_usd < 0                 # fee entry dipotong saat fill


def test_pending_cancels_on_run_away(monkeypatch):
    """Harga kabur searah >CANCEL_RUN tanpa pullback -> limit batal (jangan chase)."""
    Mk = _mk_session()
    monkeypatch.setattr(arena, "SessionLocal", Mk)
    with Mk() as s:
        arena.place_pending(s, "scalp", "BTC", dict(LONG_DECIDE, entry=99.0, sl=95.0), mark=100.0)
    # bar low 100.5 (tak sentuh 99), close 102 > 99*(1+0.02)=100.98 -> kabur -> batal
    events = arena.check_pending(_FakeCli([0, 100.5, 103.0, 100.5, 102.0]))
    assert any("batal" in e for e in events)
    with Mk() as s:
        tr = s.scalars(select(DryRunTrade)).first()
        assert tr.status == "canceled" and tr.outcome == "canceled"


def test_pending_counts_toward_max_open_slot(monkeypatch):
    Mk = _mk_session()
    with Mk() as s:
        arena.place_pending(s, "scalp", "BTC", dict(LONG_DECIDE, entry=99.0), mark=100.0)
        assert arena.active_count("scalp", s) == 1     # pending memesan slot
        assert arena.open_count("scalp", s) == 0       # tapi belum 'open'


def test_manage_position_scalp_single_tp_full_close():
    """Scalp = SATU TP tutup 100% (main cepat). Tak ada BE/partial. R=5 -> TP @ 110 (2R)."""
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        tps = json.loads(tr.tps)
        assert len(tps) == 1 and tps[0]["frac"] == 1.0 and tps[0]["price"] == pytest.approx(110.0)
        events = arena.manage_position(s, tr, high=tps[0]["price"] + 1, low=101.0, close=tps[0]["price"])
        assert any("TP1" in e for e in events)
        assert tr.status == "closed" and tr.outcome == "tp_full"    # 100% sekaligus
        assert tr.qty_remaining == 0.0
        assert tr.r_multiple is not None and tr.r_multiple > 0
        fills = s.scalars(select(DryRunFill).where(DryRunFill.trade_id == tr.id)).all()
        assert len(fills) == 1 and fills[0].label == "TP1"


def test_manage_position_sl_hit_closes_with_loss():
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        events = arena.manage_position(s, tr, high=tr.entry + 0.1, low=tr.sl - 1, close=tr.sl)
        assert any("SL" in e for e in events)
        assert tr.status == "closed"
        assert tr.outcome == "sl"
        assert tr.r_multiple is not None and tr.r_multiple < 0
        fills = s.scalars(select(DryRunFill).where(DryRunFill.trade_id == tr.id)).all()
        assert len(fills) == 1 and fills[0].label == "SL"


def test_manage_position_swing_3level_ladder_be_lock():
    """Swing 3-level (max baru): BE -> lock TP1 -> TP3 fixed tutup penuh. R=5 dari entry100/sl95:
    TP1 110(BE), TP2 117.5(lock TP1), TP3 125(tutup)."""
    swing_decide = dict(LONG_DECIDE, tps=tp_targets(1, 100.0, 95.0, mode="swing", levels=3))
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "swing", "ETH", swing_decide)
        arena.manage_position(s, tr, high=110.5, low=101.0, close=111)     # TP1@110 -> BE(~100.02)
        assert tr.status == "open"
        arena.manage_position(s, tr, high=118.0, low=111.0, close=118)     # TP2@117.5 -> lock TP1(110)
        assert tr.status == "open"
        events = arena.manage_position(s, tr, high=125.5, low=118.0, close=126)  # TP3@125 (akhir) -> tutup penuh
        assert tr.status == "closed" and tr.outcome == "tp_full"
        assert tr.qty_remaining == 0.0 and tr.r_multiple is not None and tr.r_multiple > 0
        assert any("TP3" in e for e in events)


def test_open_market_immediate_fill_with_slippage():
    """order_type=market -> open_market: isi seketika (status open) di harga + slippage taker."""
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_market(s, "scalp", "BTC", LONG_DECIDE, mark=100.0)
        assert tr.status == "open" and tr.entry_ts is not None
        assert tr.entry > LONG_DECIDE["entry"]        # slippage adverse (long fill lebih tinggi)
        assert tr.realized_pnl_usd < 0                # fee taker dipotong


def test_moonbag_honors_own_trail_when_it_differs(monkeypatch):
    """Regresi: fase moonbag pakai trail-nya SENDIRI, bukan mewarisi trail TP4. Preset kita
    TP4==moonbag==8% (no-op); di sini sengaja beda (TP4=20%, moonbag=5%). Sinkron dgn fix
    upstream paper/broker.py (AUDIT.md §H sumber)."""
    import json
    Mk = _mk_session()
    tps = [
        {"label": "TP1", "price": 103.0, "frac": 0.25, "filled": False, "sl_after": {"mode": "be"}},
        {"label": "TP2", "price": 105.0, "frac": 0.25, "filled": False, "sl_after": {"mode": "lock", "lock_label": "TP1"}},
        {"label": "TP3", "price": 150.0, "frac": 0.25, "filled": False, "sl_after": {"mode": "trail", "value": 0.20}},
        {"label": "TP4", "price": 200.0, "frac": 0.15, "filled": False, "sl_after": {"mode": "trail", "value": 0.20}},
        {"label": "TP5", "price": None, "frac": 0.10, "filled": False, "sl_after": {"mode": "trail", "value": 0.05}},
    ]
    with Mk() as s:
        tr = arena.open_trade(s, "swing", "ETH", dict(LONG_DECIDE, entry=100.0, sl=98.0, tps=tps))
        arena.manage_position(s, tr, 103.5, 100.5, 104)
        arena.manage_position(s, tr, 105.5, 104, 106)
        arena.manage_position(s, tr, 150.5, 149, 151)
        arena.manage_position(s, tr, 200.5, 199, 201)   # TP4 -> fase moonbag -> trail 5% (entry di-fill ~100.02 dgn slippage)
        assert tr.trail == pytest.approx(0.05)
        assert tr.sl == pytest.approx(201 * 0.95, abs=0.5)   # ratchet ke trail moonbag seketika
        events = arena.manage_position(s, tr, 201, 185, 200)   # low 185 < ~191 -> exit (trail lama 20% SL~160, tak exit)
        assert tr.status == "closed" and tr.outcome == "moonbag"
        assert any("moonbag" in e for e in events)


def test_equity_and_open_count_across_open_and_closed(monkeypatch):
    Mk = _mk_session()
    monkeypatch.setattr(arena, "SessionLocal", Mk)
    with Mk() as s:
        t1 = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        t2 = arena.open_trade(s, "scalp", "ETH", LONG_DECIDE)
        assert arena.open_count("scalp", s) == 2
        # tutup t1 dgn profit manual
        t1.status = "closed"
        t1.realized_pnl_usd = 15.0
        s.commit()
        assert arena.open_count("scalp", s) == 1
        eq = arena.equity("scalp", s)
        # START_EQUITY + realized closed(15) + entry-fee kedua trade (t1 closed pnl SUDAH termasuk fee awal + t2 fee open)
        assert eq > arena.START_EQUITY   # closed profit dominan meski ada fee kecil


def test_reset_wipes_trades_and_fills():
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        tp1 = json.loads(tr.tps)[0]
        arena.manage_position(s, tr, high=tp1["price"] + 1, low=tr.entry + 1, close=tp1["price"])
        s.commit()
    import src.smc.arena as arena_mod
    orig = arena_mod.SessionLocal
    arena_mod.SessionLocal = Mk
    try:
        r = arena.reset()
        assert r["deleted_trades"] == 1 and r["deleted_fills"] == 1
        with Mk() as s:
            assert len(s.scalars(select(DryRunTrade)).all()) == 0
            assert len(s.scalars(select(DryRunFill)).all()) == 0
    finally:
        arena_mod.SessionLocal = orig


def test_max_open_positions_is_ten_with_scaled_risk():
    # web: max 10 posisi/gaya, risk & margin per-trade dikecilkan agar agregat sehat
    assert GROUPS["scalp"]["max_open"] == 10 and GROUPS["swing"]["max_open"] == 10
    # 10 x risk% <= ~10% risiko simultan; 10 x margin_cap <= ~35% margin simultan
    assert GROUPS["scalp"]["risk_pct"] * 10 <= 0.06 and GROUPS["swing"]["risk_pct"] * 10 <= 0.11
    assert GROUPS["scalp"]["margin_cap"] * 10 <= 0.20 and GROUPS["swing"]["margin_cap"] * 10 <= 0.40


def test_funding_fee_helper():
    """risk.funding_fee: long bayar saat rate>0, short terima, proporsional 8 jam."""
    from src.smc.risk import funding_fee
    # notional 1000, rate 0.0001, 8 jam, long -> -0.10 (bayar)
    assert round(funding_fee(1000, 0.0001, +1, 8.0), 4) == -0.1
    assert round(funding_fee(1000, 0.0001, -1, 8.0), 4) == 0.1     # short terima
    assert round(funding_fee(1000, 0.0001, +1, 4.0), 4) == -0.05   # 4 jam = separuh
    assert funding_fee(1000, 0.0, +1, 8.0) == 0.0                  # rate 0 -> tak ada
    assert funding_fee(1000, None, +1, 8.0) == 0.0                 # rate None -> tak ada


def test_open_market_stores_funding_rate():
    """open_market + place_pending menyimpan funding_rate; fill_pending set funding_last_ts."""
    d = {"direction": 1, "entry": 100.0, "sl": 95.0, "qty": 1.0, "leverage": 10,
         "risk_frac": 0.02, "risk_usd": 20.0, "margin_usd": 10.0, "tps": [], "full_score": 3,
         "zone": "discount", "high_confluence": True, "order_type": "market"}
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_market(s, "swing", "BTC", d, mark=100.0, funding_rate=0.0002)
        assert tr.funding_rate == 0.0002
        assert tr.funding_last_ts is not None      # market -> akrual mulai seketika
        assert tr.funding_paid_usd == 0.0
        # pending: funding_rate tersimpan, tapi funding_last_ts belum (mulai saat fill)
        tp = arena.place_pending(s, "swing", "ETH", dict(d, order_type="limit"), mark=100.0, funding_rate=0.0002)
        assert tp.funding_rate == 0.0002 and tp.funding_last_ts is None
        arena.fill_pending(s, tp)
        assert tp.funding_last_ts is not None       # fill -> akrual mulai


def test_funding_gate_blocks_high_adverse_funding():
    """funding_gate web: hindari funding EKSTREM (dua arah) + funding-bayar; wajar/terima lolos."""
    from src.smc.risk import funding_gate
    assert funding_gate(+1, -0.0005, 100.0, 102.0, "swing")[0] is True   # long terima wajar -> lolos
    assert funding_gate(+1, 0.0005, 100.0, 102.0, "swing")[0] is True    # bayar wajar -> lolos
    # EKSTREM dua arah (LAB -0.76%/8j): long "terima" pun TETAP ditolak (pasar tak stabil)
    assert funding_gate(+1, -0.0076, 10.0, 13.0, "swing")[0] is False
    assert funding_gate(-1, -0.0076, 10.0, 8.0, "swing")[0] is False
    assert funding_gate(+1, 0.0015, 100.0, 102.0, "swing")[0] is False   # bayar > 0.1% -> tolak
    assert funding_gate(+1, 0.0008, 100.0, 101.0, "swing")[0] is False   # makan >35% target -> tolak
