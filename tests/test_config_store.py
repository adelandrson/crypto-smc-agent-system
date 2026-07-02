"""Test src/smc/config_store.py — otoritas parameter agen: validasi ketat, clamp rentang,
effective_groups overlay. File config di-isolasi ke tmp_path (tak sentuh runtime)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.smc import config_store


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "_config_path", lambda: str(tmp_path / "cfg.json"))


def test_set_global_validates_and_clamps(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert config_store.set_param("min_abs_score", "3") == 3        # koersi string->int
    assert config_store.set_param("min_abs_score", 99) == 4         # clamp ke max 4
    assert config_store.set_param("enforce_zone", "false") is False  # koersi bool
    assert config_store.set_param("cancel_run", 999) == 0.1         # clamp float
    with pytest.raises(ValueError):
        config_store.set_param("evil_exec", 1)                      # key tak dikenal DITOLAK
    with pytest.raises(ValueError):
        config_store.set_param("data_market_type", "futures")       # choice tak valid DITOLAK


def test_set_group_param_isolated_per_style(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert config_store.set_param("lev_max", "40", group="scalp") == 40
    assert config_store.set_param("lev_max", 999, group="scalp") == 125   # clamp
    eff = config_store.effective_groups()
    assert eff["scalp"]["lev_max"] == 125
    assert eff["swing"]["lev_max"] == 15                            # gaya lain tak terpengaruh
    with pytest.raises(ValueError):
        config_store.set_param("lev_max", 10, group="perp")         # gaya tak dikenal
    with pytest.raises(ValueError):
        config_store.set_param("min_abs_score", 3, group="scalp")   # param global bukan per-gaya


def test_effective_groups_injects_globals(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    config_store.set_param("min_abs_score", 3)
    eff = config_store.effective_groups()
    assert eff["scalp"]["min_abs_score"] == 3 and eff["swing"]["min_abs_score"] == 3
    # default GROUPS tetap ada
    assert eff["scalp"]["risk_pct"] == 0.01 and eff["swing"]["tf"] == "4h"


def test_reset(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    config_store.set_param("min_abs_score", 4)
    config_store.set_param("lev_max", 30, group="swing")
    config_store.reset("min_abs_score")
    assert config_store.get_global("min_abs_score") == 2            # global kembali default
    assert config_store.effective_groups()["swing"]["lev_max"] == 30  # per-gaya masih
    config_store.reset()                                            # reset SEMUA
    assert config_store.effective_groups()["swing"]["lev_max"] == 15


def test_snapshot_shape(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    snap = config_store.snapshot()
    assert "global" in snap and "groups" in snap and "allowed_global" in snap
    assert snap["global"]["min_abs_score"] == 2
    assert set(snap["groups"]) == {"scalp", "swing"}
