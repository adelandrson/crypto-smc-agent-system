"""Test 3 mode otoritas agent (none/medium/full) meng-gate tool + admin-only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from src.smc import admin_settings
from src.agents import roster


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_settings, "_path", lambda: str(tmp_path / "admin_settings.json"))


def test_default_authority_is_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert admin_settings.get_authority() == "none"        # DEFAULT tanpa otoritas


def test_set_authority_validates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert admin_settings.set_authority("full") == "full"
    assert admin_settings.get_authority() == "full"
    with pytest.raises(ValueError):
        admin_settings.set_authority("god")


def test_tool_gating_per_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    def names(mode):
        admin_settings.set_authority(mode)
        return {t["function"]["name"] for t in roster.agent_tools_spec("orchestrator")}
    none_t = names("none"); med_t = names("medium"); full_t = names("full")
    # none: tak ada tool yang mengubah apa pun
    assert not ({"config_set", "config_reset", "write_source", "run_tests", "rnd_step"} & none_t)
    assert "confluence_signal" in none_t and "config_get" in none_t   # observasi tetap ada
    # medium: config + ops, TANPA edit kode
    assert {"config_set", "config_reset", "rnd_step"} <= med_t
    assert not ({"write_source", "run_tests"} & med_t)
    # full: semua termasuk kode
    assert {"config_set", "write_source", "run_tests"} <= full_t
    # monoton: none ⊂ medium ⊂ full
    assert none_t <= med_t <= full_t


def test_impls_match_spec_gating(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    admin_settings.set_authority("none")
    impls = roster.agent_tool_impls("orchestrator")
    assert "write_source" not in impls and "config_set" not in impls
