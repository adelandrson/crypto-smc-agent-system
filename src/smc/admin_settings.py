"""Setelan ADMIN — HANYA diubah lewat panel Admin ber-password (/api/admin/*), TERPISAH dari
config_store (yang boleh diubah agent). Yang paling penting: `agent_authority` menentukan tool
apa yang diberikan ke agent:

    none   (DEFAULT) — tanpa otoritas: agent cuma OBSERVASI/ANALISA (read-only), tak bisa ubah
                       config maupun kode, tak bisa trigger operasi yang mengubah state.
    medium — otoritas menengah: agent bisa set CONFIG (parameter metodologi) + operasi dry-run,
                       TAPI tak bisa edit kode.
    full   — otoritas penuh: + edit KODE (write_source/run_tests).

Agent TIDAK BISA mengubah file ini: write_source hanya izinkan src/ & tests/, dan file ini
di-blocklist eksplisit. Jadi agent tak bisa menaikkan otoritasnya sendiri — hanya manusia (admin)."""
from __future__ import annotations

import json
import os

from src import config

AUTHORITY_LEVELS = ("none", "medium", "full")
DEFAULTS = {"agent_authority": "none"}   # DEFAULT tanpa otoritas (permintaan user)


def _path() -> str:
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        d = os.path.dirname(os.path.abspath(url[len("sqlite:///"):]))
    else:
        d = os.getcwd()
    return os.path.join(d, "admin_settings.json")


def _load() -> dict:
    try:
        with open(_path()) as f:
            return {**DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def get_authority() -> str:
    a = _load().get("agent_authority")
    return a if a in AUTHORITY_LEVELS else "none"


def set_authority(mode: str) -> str:
    if mode not in AUTHORITY_LEVELS:
        raise ValueError(f"mode tak valid: {mode} (pilih: {AUTHORITY_LEVELS})")
    d = _load()
    d["agent_authority"] = mode
    tmp = _path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _path())
    return mode


def snapshot() -> dict:
    return {"agent_authority": get_authority(), "levels": list(AUTHORITY_LEVELS)}
