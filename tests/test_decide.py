"""Test src/smc/decide.py — monkeypatch analyze_confluence (deterministic; sinyal full_strong
nyata jarang muncul dari data acak, by design — lihat PAPER-TRADING.md sumber metodologi)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.smc import decide as decide_mod
from src.smc.decide import GROUPS, _choose_leverage, decide


def _c(**over):
    base = {"full_strong": True, "full_score": 3, "zone": "discount", "ranging": False,
            "volume_ok": True, "nearest_fvg": {"bottom": 95.0, "top": 96.0},
            "structure": {"last_swing_low": 94.0, "last_swing_high": 108.0},
            "price": 100.0, "high_confluence": False, "fr_score": 1, "oi_score": 1}
    base.update(over)
    return base


def _patch(monkeypatch, conf):
    monkeypatch.setattr(decide_mod, "analyze_confluence", lambda *a, **k: conf)


def test_leverage_range_scalp_and_swing():
    assert _choose_leverage(GROUPS["scalp"], 0.003) == 30    # SL rapat -> lev_max
    assert _choose_leverage(GROUPS["scalp"], 0.02) == 15      # SL lebar -> lev_min
    assert _choose_leverage(GROUPS["swing"], 0.01) == 15
    assert _choose_leverage(GROUPS["swing"], 0.08) == 8
    for cfg in (GROUPS["scalp"], GROUPS["swing"]):
        for sd in (0.001, 0.005, 0.015, 0.05):
            lev = _choose_leverage(cfg, sd)
            assert cfg["lev_min"] <= lev <= cfg["lev_max"]


def test_skip_when_not_full_strong(monkeypatch):
    _patch(monkeypatch, _c(full_strong=False))
    d = decide("BTC", [], 0, 0, 1000.0, GROUPS["scalp"])
    assert d["action"] == "skip" and "full_strong" in d["reason"]


def test_skip_when_ranging(monkeypatch):
    _patch(monkeypatch, _c(ranging=True))
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"])
    assert d["action"] == "skip" and "ranging" in d["reason"]


def test_skip_when_volume_anomaly(monkeypatch):
    _patch(monkeypatch, _c(volume_ok=False))
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"])
    assert d["action"] == "skip" and "volume" in d["reason"]


def test_skip_when_lsr_contrarian(monkeypatch):
    _patch(monkeypatch, _c(full_score=3))    # direction=+1 (long)
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"], lsr_score=-1)  # crowd short-side veto
    assert d["action"] == "skip" and "lsr_score" in d["reason"]


def test_skip_when_zone_blocks_direction(monkeypatch):
    _patch(monkeypatch, _c(full_score=3, zone="premium"))   # long but in premium -> blocked
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"])
    assert d["action"] == "skip" and "zone" in d["reason"]


def test_open_long_sizing_leverage_margin(monkeypatch):
    """entry=100, structure_sl -> below nearest_fvg.bottom(95)*(1-0.002)=94.81; risk%=1% scalp."""
    _patch(monkeypatch, _c(full_score=3, zone="discount", price=100.0))
    equity = 1000.0
    d = decide("BTC", [], 1, 1, equity, GROUPS["scalp"], lsr_score=1)
    assert d["action"] == "open"
    assert d["direction"] == 1
    assert d["sl"] < d["entry"]
    cfg = GROUPS["scalp"]
    assert cfg["lev_min"] <= d["leverage"] <= cfg["lev_max"]
    # risk_frac target ~= risk_pct (kecuali margin-cap ikut campur tangan)
    assert abs(d["risk_frac"] - cfg["risk_pct"]) < 0.003
    # margin tak pernah melebihi margin_cap x equity (+ toleransi rounding)
    assert d["margin_usd"] <= cfg["margin_cap"] * equity + 0.5
    # TP bertahap: 3 level utk scalp, total frac = 1.0
    assert len(d["tps"]) == 3
    assert abs(sum(t["frac"] for t in d["tps"]) - 1.0) < 1e-9
    assert d["tps"][0]["price"] > d["entry"]        # TP long di atas entry


def test_open_short_zone_premium(monkeypatch):
    _patch(monkeypatch, _c(full_score=-3, zone="premium", price=100.0,
                            nearest_fvg={"bottom": 104.0, "top": 106.0},
                            structure={"last_swing_low": 90.0, "last_swing_high": 108.0}))
    d = decide("ETH", [], -1, -1, 1000.0, GROUPS["swing"], lsr_score=-1)
    assert d["action"] == "open"
    assert d["direction"] == -1
    assert d["sl"] > d["entry"]          # short SL di atas entry
    assert d["tps"][0]["price"] < d["entry"]
    assert len(d["tps"]) == 5             # swing = 5 level + moonbag
    assert d["tps"][-1]["price"] is None  # moonbag: tanpa target fixed


def test_margin_cap_shrinks_notional_not_risk_target(monkeypatch):
    """Equity kecil + SL sangat rapat -> leverage max tapi margin tetap bisa kepentok cap;
    saat itu terjadi, notional/qty menyusut (risk_frac turun DI BAWAH target, bukan naik)."""
    _patch(monkeypatch, _c(full_score=3, zone="discount", price=100.0,
                            nearest_fvg={"bottom": 99.8, "top": 99.9},   # SL SANGAT rapat
                            structure={"last_swing_low": 99.7, "last_swing_high": 108.0}))
    cfg = dict(GROUPS["scalp"], margin_cap=0.001)   # cap ekstrem-kecil buat pemicu kondisi ini
    d = decide("BTC", [], 1, 1, 1000.0, cfg, lsr_score=1)
    assert d["action"] == "open"
    assert d["margin_usd"] <= cfg["margin_cap"] * 1000 + 0.5
    assert d["risk_frac"] <= cfg["risk_pct"] + 1e-9   # tak pernah MELEBIHI target risk%
