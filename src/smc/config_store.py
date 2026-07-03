"""Runtime config store — knob METODOLOGI/LOGIC/DATA yang boleh diubah AGEN via chat (wewenang
penuh atas web, sesuai instruksi user). Overlay JSON di atas GROUPS default + knob global.

KEAMANAN: divalidasi ketat — HANYA key yang dikenal, tipe dikoersi, nilai di-clamp ke rentang
aman. Ini otoritas PARAMETER (gerbang confluence, filter SKIP, disiplin zona, leverage/risk,
timeframe/sumber-data, perilaku limit-order), BUKAN eksekusi kode arbitrer. Batas ini disengaja:
agen menyerap konten eksternal (bisa kena prompt-injection) — memberi exec kode mentah = RCE.
Seluruh permukaan logika yang seorang trader nyata ingin setel tersedia; kode inti tak tersentuh.

Dibaca oleh decide()/arena lewat `effective_groups()`. File dibaca FRESH tiap panggilan supaya
perubahan dari proses web langsung terlihat proses monitor/cron (beda proses)."""
from __future__ import annotations

import json
import os
from copy import deepcopy

from src import config
from src.smc.decide import GROUPS as _BASE_GROUPS


def _config_path() -> str:
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        db = url[len("sqlite:///"):]
        d = os.path.dirname(os.path.abspath(db))
    else:
        d = os.getcwd()
    return os.path.join(d, "smc_runtime_config.json")


# knob GLOBAL (berlaku lintas gaya) + default
GLOBAL_DEFAULTS = {
    "min_abs_score": 2,          # gerbang: |full_score| minimum utk trade (inti metodologi)
    "enforce_zone": True,        # disiplin zona (long=discount/short=premium)
    "skip_ranging": True,        # filter SKIP: pasar ranging
    "skip_volume_anomaly": True, # filter SKIP: volume di bawah normal
    "lsr_contrarian": True,      # filter SKIP: LSR kontrarian (fade crowd)
    "limit_max_pullback": 0.05,  # limit order: jarak maksimum dari harga kini
    "limit_min_pullback": 0.0015,  # limit order: pullback minimum bila tak ada FVG searah
    "cancel_run": 0.02,          # limit order: batal bila harga kabur >x searah
    "data_market_type": "perp",  # sumber data: perp | spot
}
# spec validasi global: key -> (tipe, ...batas)
GLOBAL_SPEC = {
    "min_abs_score": ("int", 1, 4),
    "enforce_zone": ("bool",),
    "skip_ranging": ("bool",),
    "skip_volume_anomaly": ("bool",),
    "lsr_contrarian": ("bool",),
    "limit_max_pullback": ("float", 0.005, 0.2),
    "limit_min_pullback": ("float", 0.0, 0.05),
    "cancel_run": ("float", 0.005, 0.1),
    "data_market_type": ("choice", ["perp", "spot"]),
}
# spec validasi per-gaya (scalp/swing)
GROUP_SPEC = {
    "lev_min": ("int", 1, 50),
    "lev_max": ("int", 1, 125),
    "risk_pct": ("float", 0.001, 0.05),
    "margin_cap": ("float", 0.005, 0.5),
    "max_open": ("int", 0, 20),
    "pending_ttl_h": ("int", 1, 720),
    "tf": ("choice", ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]),
    "candle_limit": ("int", 60, 500),
    # funding gate — hindari funding tinggi yg menggerus PnL (agen/admin bisa longgar/ketat)
    "funding_max_pay_8h": ("float", 0.0001, 0.02),    # adverse funding/8j di atas ini -> tolak (0.01%..2%)
    "funding_max_profit_frac": ("float", 0.05, 1.0),  # funding boleh makan max X dari target profit
}


def _load() -> dict:
    """Baca overlay FRESH dari disk (lintas-proses konsisten)."""
    try:
        with open(_config_path()) as f:
            d = json.load(f)
            d.setdefault("global", {})
            d.setdefault("groups", {})
            return d
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"global": {}, "groups": {}}


def _save(d: dict) -> None:
    path = _config_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def get_global(key: str):
    return _load().get("global", {}).get(key, GLOBAL_DEFAULTS.get(key))


def effective_groups() -> dict:
    """GROUPS efektif = base GROUPS + knob global (di-inject ke tiap gaya) + override per-gaya."""
    ov = _load()
    g_over = ov.get("global", {})
    groups = deepcopy(_BASE_GROUPS)
    for gname, gcfg in groups.items():
        for k, dv in GLOBAL_DEFAULTS.items():
            gcfg[k] = g_over.get(k, dv)
        gcfg.update(ov.get("groups", {}).get(gname, {}))
    return groups


def _coerce(spec: tuple, value):
    t = spec[0]
    if t == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "ya", "aktif")
        return bool(value)
    if t == "int":
        return max(spec[1], min(spec[2], int(float(value))))
    if t == "float":
        return max(spec[1], min(spec[2], float(value)))
    if t == "choice":
        v = str(value)
        if v not in spec[1]:
            raise ValueError(f"nilai tak valid; pilih salah satu: {spec[1]}")
        return v
    raise ValueError("tipe spec tak dikenal")


def set_param(key: str, value, group: str | None = None):
    """Set 1 param (global atau per-gaya). Validasi ketat; return nilai efektif tersimpan."""
    ov = _load()
    if group:
        if group not in _BASE_GROUPS:
            raise ValueError(f"gaya tak dikenal: {group} (pilih scalp/swing)")
        if key not in GROUP_SPEC:
            raise ValueError(f"param per-gaya tak diizinkan: {key}. Diizinkan: {sorted(GROUP_SPEC)}")
        v = _coerce(GROUP_SPEC[key], value)
        ov.setdefault("groups", {}).setdefault(group, {})[key] = v
    else:
        if key not in GLOBAL_SPEC:
            raise ValueError(f"param global tak diizinkan: {key}. Diizinkan: {sorted(GLOBAL_SPEC)}")
        v = _coerce(GLOBAL_SPEC[key], value)
        ov.setdefault("global", {})[key] = v
    _save(ov)
    return v


def reset(key: str | None = None, group: str | None = None) -> None:
    """Hapus override (kembali ke default). key=None -> reset semua."""
    if key is None:
        _save({"global": {}, "groups": {}})
        return
    ov = _load()
    if group:
        ov.get("groups", {}).get(group, {}).pop(key, None)
    else:
        ov.get("global", {}).pop(key, None)
    _save(ov)


def snapshot() -> dict:
    """Config efektif + apa yang di-override + daftar param yg diizinkan (utk skill get_config)."""
    ov = _load()
    eff = effective_groups()
    return {
        "global": {k: get_global(k) for k in GLOBAL_DEFAULTS},
        "global_overridden": sorted(ov.get("global", {})),
        "groups": {g: {k: eff[g].get(k) for k in GROUP_SPEC} for g in _BASE_GROUPS},
        "group_overridden": ov.get("groups", {}),
        "allowed_global": {k: list(v[1:]) for k, v in GLOBAL_SPEC.items()},
        "allowed_group": {k: list(v[1:]) for k, v in GROUP_SPEC.items()},
    }
