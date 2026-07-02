"""Test src/smc/decide.py — monkeypatch analyze_confluence (deterministic; sinyal full_strong
nyata jarang muncul dari data acak, by design — lihat PAPER-TRADING.md sumber metodologi)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.smc import decide as decide_mod
from src.smc.decide import GROUPS, _choose_leverage, decide
from src.smc.risk import limit_entry


def test_limit_entry_retest_zone():
    """Entry = harga LIMIT ORDER di retest zona imbalance (bukan market di harga kini)."""
    assert limit_entry(1, 100.0, {"top": 99.0, "bottom": 96.0}) == 99.0    # long: TOP FVG di bawah
    assert limit_entry(-1, 100.0, {"top": 105.0, "bottom": 102.0}) == 102.0  # short: BOTTOM FVG di atas
    assert limit_entry(1, 100.0, None) == 100.0 * (1 - 0.0015)             # tanpa FVG -> pullback kecil
    assert limit_entry(1, 100.0, {"top": 80.0}) == 100.0 * (1 - 0.05)      # zona jauh -> clamp max_pullback


def test_decide_uses_limit_entry_below_price_for_long(monkeypatch):
    """decide() long menaruh entry di TOP FVG (96) di bawah harga kini (100), bukan di 100."""
    monkeypatch.setattr(decide_mod, "analyze_confluence",
                        lambda *a, **k: _c(full_score=3, zone="discount", price=100.0,
                                           nearest_fvg={"bottom": 95.0, "top": 96.0}))
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"], lsr_score=1)
    assert d["action"] == "open" and d["entry"] == 96.0 and d["entry"] < 100.0


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


def test_skip_when_below_score_gate(monkeypatch):
    _patch(monkeypatch, _c(full_score=1))                    # |1| < gerbang default 2 -> skip
    d = decide("BTC", [], 0, 0, 1000.0, GROUPS["scalp"])
    assert d["action"] == "skip" and "gate" in d["reason"]


def test_config_gate_min_abs_score(monkeypatch):
    """Agen menaikkan gerbang ke 3 -> sinyal score-2 di-skip; turun ke 2 -> lolos."""
    _patch(monkeypatch, _c(full_score=2, zone="discount"))
    assert decide("BTC", [], 1, 1, 1000.0, dict(GROUPS["scalp"], min_abs_score=3), lsr_score=1)["action"] == "skip"
    assert decide("BTC", [], 1, 1, 1000.0, dict(GROUPS["scalp"], min_abs_score=2), lsr_score=1)["action"] == "open"


def test_config_enforce_zone_toggle(monkeypatch):
    """Long di premium normal-nya di-skip; enforce_zone=False -> lolos (wewenang agen)."""
    _patch(monkeypatch, _c(full_score=3, zone="premium"))
    assert decide("BTC", [], 1, 1, 1000.0, dict(GROUPS["scalp"], enforce_zone=True), lsr_score=1)["action"] == "skip"
    assert decide("BTC", [], 1, 1, 1000.0, dict(GROUPS["scalp"], enforce_zone=False), lsr_score=1)["action"] == "open"


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
    # SCALP = SINGLE TP 100% (main cepat), tanpa TP berkala
    assert len(d["tps"]) == 1
    assert d["tps"][0]["frac"] == 1.0
    assert d["tps"][0]["price"] > d["entry"]        # TP long di atas entry


def test_open_short_zone_premium_swing_dynamic_tp(monkeypatch):
    # vol_state trending -> 3 TP berkala (fixed, sum=100%, tanpa moonbag)
    _patch(monkeypatch, _c(full_score=-3, zone="premium", price=100.0, vol_state="trending",
                            nearest_fvg={"bottom": 104.0, "top": 106.0},
                            structure={"last_swing_low": 90.0, "last_swing_high": 108.0}))
    d = decide("ETH", [], -1, -1, 1000.0, GROUPS["swing"], lsr_score=-1)
    assert d["action"] == "open" and d["direction"] == -1
    assert d["sl"] > d["entry"]          # short SL di atas entry
    assert d["tps"][0]["price"] < d["entry"]
    assert len(d["tps"]) == 3             # trending -> 3 level
    assert all(t["price"] is not None for t in d["tps"])   # tak ada moonbag
    assert abs(sum(t["frac"] for t in d["tps"]) - 1.0) < 1e-9


def test_swing_tp_count_by_volatility(monkeypatch):
    """Jumlah TP swing dari VOLATILITY STATE + ATR (bukan confluence). trending/breakout->3,
    mixed->2, ranging->1; ATR sangat rendah (<0.3) turunkan 1."""
    base = dict(full_score=-3, zone="premium", price=100.0, nearest_fvg={"bottom": 104.0, "top": 106.0},
                structure={"last_swing_low": 90.0, "last_swing_high": 108.0})

    def n(vol, atr=None):
        _patch(monkeypatch, _c(vol_state=vol, atr_percentile=atr, **base))
        return len(decide("E", [], -1, -1, 1000.0, GROUPS["swing"], lsr_score=-1)["tps"])

    assert n("trending") == 3 and n("breakout") == 3
    assert n("mixed") == 2 and n(None) == 2
    assert n("ranging") == 1
    assert n("trending", 0.2) == 2       # ATR rendah -> turun 1


def test_decide_market_entry_when_price_in_zone(monkeypatch):
    """Harga kini di dalam FVG -> order_type=market (bukan limit)."""
    _patch(monkeypatch, _c(full_score=3, zone="discount", price=97.0,   # 95<=97<=99 -> di zona
                            nearest_fvg={"bottom": 95.0, "top": 99.0},
                            structure={"last_swing_low": 94.0, "last_swing_high": 110.0}))
    d = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"], lsr_score=1)
    assert d["action"] == "open" and d["order_type"] == "market" and d["entry"] == 97.0
    # harga di luar zona -> limit
    _patch(monkeypatch, _c(full_score=3, zone="discount", price=100.0,
                            nearest_fvg={"bottom": 95.0, "top": 96.0},
                            structure={"last_swing_low": 94.0, "last_swing_high": 110.0}))
    d2 = decide("BTC", [], 1, 1, 1000.0, GROUPS["scalp"], lsr_score=1)
    assert d2["order_type"] == "limit" and d2["entry"] == 96.0


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
