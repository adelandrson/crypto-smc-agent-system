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
from src.storage.models import Base, DryRunFill, DryRunTrade


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


def test_open_trade_persists_fields_and_deducts_fee():
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        assert tr.id is not None
        assert tr.status == "open" and tr.leg == "long" and tr.group == "scalp"
        assert tr.agent == "Wira·scalp"
        assert tr.qty_remaining == tr.original_qty == 2.0
        assert tr.entry > LONG_DECIDE["entry"]          # slippage adverse on entry (long -> fill higher)
        assert tr.realized_pnl_usd < 0                  # entry fee sudah dipotong
        assert json.loads(tr.tps)[0]["label"] == "TP1"


def test_manage_position_tp1_moves_sl_to_breakeven():
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        entry = tr.entry
        tp1 = json.loads(tr.tps)[0]
        # low DI ATAS entry (bar realistis: TP1 kena tapi harga tak pernah balik ke entry di bar yg sama)
        events = arena.manage_position(s, tr, high=tp1["price"] + 1, low=entry + 1, close=tp1["price"])
        assert any("TP1" in e for e in events)
        assert tr.sl == entry            # sl_after mode=be -> SL to breakeven
        assert tr.qty_remaining < tr.original_qty
        assert tr.status == "open"       # scalp TP1=50% -> masih ada sisa
        fills = s.scalars(select(DryRunFill).where(DryRunFill.trade_id == tr.id)).all()
        assert len(fills) == 1 and fills[0].label == "TP1"


def test_manage_position_full_tp_ladder_closes_trade():
    """3 bar berurutan, tiap bar `low` dijaga TETAP DI ATAS SL yg baru saja di-evolve pada
    bar itu (bar realistis — TP kena duluan, harga tak langsung retrace ke SL lama/baru)."""
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "scalp", "BTC", LONG_DECIDE)
        # bar 1: TP1 (107.5) -> SL jadi BE(~entry, ~100.02); low dijaga > entry
        arena.manage_position(s, tr, high=108.0, low=101.0, close=107.5)
        assert tr.status == "open"
        # bar 2: TP2 (112.5, trail 0.3%) -> SL trail jadi ~112.5*0.997=112.16; low dijaga > itu
        arena.manage_position(s, tr, high=113.0, low=112.2, close=112.5)
        assert tr.status == "open"
        # bar 3: TP3 (120, frac 20% = SISA TERAKHIR) -> qty_remaining tepat 0, closed apapun low-nya
        arena.manage_position(s, tr, high=120.5, low=119.0, close=120.0)
        assert tr.status == "closed"
        assert tr.outcome == "tp_full"
        assert tr.qty_remaining == 0.0
        assert tr.r_multiple is not None and tr.r_multiple > 0     # semua TP = untung
        assert tr.closed_at is not None


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


def test_manage_position_swing_moonbag_via_trailing():
    """5 bar berurutan (TP1..TP4 lalu trailing-exit moonbag). Trailing SL DIEVALUASI ULANG
    tiap bar (ratchet di awal `manage_position`, thd `close` bar ITU JUGA) — bukan cuma
    saat TP baru fill — jadi `low` tiap bar dijaga di atas hasil ratchet TERBARU, bukan cuma
    hasil trail dari TP yg baru saja fill di bar itu sendiri."""
    swing_decide = dict(LONG_DECIDE, tps=tp_targets(1, 100.0, 95.0, mode="swing"))
    Mk = _mk_session()
    with Mk() as s:
        tr = arena.open_trade(s, "swing", "ETH", swing_decide)
        # TP1(107.5,be) -> SL~entry(~100.02)
        arena.manage_position(s, tr, high=108.0, low=101.0, close=107.5)
        # TP2(112.5,lock->TP1=107.5) -> SL=107.5; low dijaga >107.5
        arena.manage_position(s, tr, high=113.0, low=108.0, close=112.5)
        # TP3(120,trail 5%) -> tr.trail=0.05, SL=max(107.5,120*0.95=114)=114; low dijaga >114
        arena.manage_position(s, tr, high=121.0, low=114.5, close=120.0)
        # TP4(130,trail 8%): ratchet AWAL bar pakai trail LAMA(0.05) x close(130)=123.5 dulu
        # (>114) SEBELUM TP4 diproses; TP4 fill set trail=0.08 tapi max(123.5,119.6)=123.5
        # tetap menang -> SL efektif jadi 123.5, bukan 119.6. low dijaga >123.5.
        arena.manage_position(s, tr, high=131.0, low=124.0, close=130.0)
        assert tr.status == "open"           # moonbag masih terbuka (trailing, tanpa target fixed)
        assert tr.qty_remaining > 0
        assert tr.sl == pytest.approx(123.5, abs=0.01)
        # bar terakhir: retrace di bawah SL efektif (123.5) -> moonbag exit
        events = arena.manage_position(s, tr, high=124.0, low=122.0, close=122.0)
        assert tr.status == "closed"
        assert tr.outcome == "moonbag"
        assert any("moonbag" in e for e in events)


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


def test_max_open_positions_is_four_for_both_styles():
    assert GROUPS["scalp"]["max_open"] == 4
    assert GROUPS["swing"]["max_open"] == 4
