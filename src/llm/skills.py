"""Registry skill (tools) — dipanggil agent via function-calling. Pola persis
crypto-trader-agent-system (_SKILLS = {name: (fn, json_schema, deskripsi)}).

LAPIS 1 (analisa live, read-only, tanpa DB): fvg_analyze/structure_analyze/sentiment_analyze/
momentum_analyze/confluence_signal — panggil engine metodologi langsung thd data Binance live.
LAPIS 2 (status dry-run, baca DB): dryrun_summary/dryrun_positions/tier_list/screening_highlights.
LAPIS 3 (akses data generik, READ-ONLY): db_query/read_file/list_dir — pola & guard SAMA PERSIS
dgn crypto-trader-agent-system (lihat catatan keamanan di sana): SELECT/WITH saja, path proyek
saja, file rahasia diblokir.
LAPIS 4 (PERINTAH operasi, bounded & non-destruktif): rnd_step/rnd_universe_refresh — SENGAJA
TANPA reset (destruktif, tetap gate manusia via UI confirm) & TANPA shell/file-write bebas.
"""
from __future__ import annotations

import contextlib as _ctx
import io as _io
import os as _os
import re as _re

from src.smc.binance_adapter import BinanceAdapter
from src.smc.confluence import analyze_confluence, fib_preset, ind, sfib
from src.smc.decide import GROUPS, decide
from src.smc.fvg_adapter import analyze_for_confluence
from src.smc.sentiment import aggregate_sentiment

_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
_WRITE_KW = _re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|truncate|grant|revoke)\b")
_SECRET_HINT = ("secret", "credential", "password", "token", "apikey", "api_key")


def _p(props, req):
    return {"type": "object", "properties": props, "required": req}


def _pair(symbol: str) -> str:
    s = (symbol or "").upper().replace("/USDT", "").replace("-USDT", "")
    return f"{s}/USDT"


def _fetch_candles(symbol: str, timeframe: str = "1h", limit: int = 220):
    cli = BinanceAdapter()
    return cli.fetch_ohlcv(_pair(symbol), timeframe, limit=limit, market_type="perp")


# ── LAPIS 1: analisa live (langsung ke engine metodologi) ──────────────────
def fvg_analyze(symbol: str, timeframe: str = "1h"):
    """Deteksi Fair Value Gap (FVG) — SATU-SATUNYA sumber = engine fvg-nephew-sam. Zona aktif
    (fresh/tested), bias, nearest_fvg (support/resistance terdekat dari imbalance)."""
    try:
        candles = _fetch_candles(symbol, timeframe)
        return analyze_for_confluence(candles, config={"threshold_mode": "atr", "min_atr_mult": 0.25})
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def structure_analyze(symbol: str, timeframe: str = "1h"):
    """Struktur SMC — swing (pivot+ATR), Fibonacci (golden pocket/OTE/ekuilibrium), Order Block,
    BOS/CHoCH. Engine swing-fib (satu-satunya sumber struktur/Fib/OB — jangan taksir visual)."""
    try:
        candles = _fetch_candles(symbol, timeframe)
        return sfib.analyze(candles, fib_preset(timeframe))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def sentiment_analyze(symbol: str):
    """Sentimen derivatif: Funding Rate (kontrarian di ekstrem), Open Interest (arah leverage),
    Long/Short Ratio (kontrarian crowd), CVD proxy (taker buy/sell). Sumber: Binance publik."""
    try:
        cli = BinanceAdapter()
        return aggregate_sentiment([cli], _pair(symbol))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def momentum_analyze(symbol: str, timeframe: str = "1h"):
    """Momentum/volatilitas/volume: RSI Wilder + divergensi, ADX, vol_state (trending/breakout/
    ranging/mixed — filter SKIP), volume z-score (anomaly filter)."""
    try:
        candles = _fetch_candles(symbol, timeframe)
        return ind.analyze(candles, {})
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def confluence_signal(symbol: str, style: str = "scalp"):
    """Sinyal TRADE lengkap 1 koin: confluence penuh (FVG+Fib+OI+FR+LSR, skor -4..+4) + verdict
    (open/skip + alasan) + rencana (entry/SL/TP bertahap) kalau lolos gerbang. style: scalp|swing.
    Ini yang MENENTUKAN dry-run — sama persis logic src/smc/decide.py."""
    st = (style or "scalp").lower()
    if st not in GROUPS:
        return {"error": f"style '{st}' tak dikenal — pilih: scalp | swing"}
    cfg = GROUPS[st]
    try:
        cli = BinanceAdapter()
        candles = cli.fetch_ohlcv(_pair(symbol), cfg["tf"], limit=cfg["candle_limit"], market_type="perp")
        sent = aggregate_sentiment([cli], _pair(symbol))
        from src.smc.oi_tracker import OITracker
        oi_score = OITracker().score(symbol.upper(), sent.get("total_open_interest"), candles[-1][4])
        d = decide(symbol.upper(), candles, sent["fr_score"], oi_score, 1000.0, cfg,
                    lsr_score=sent.get("lsr_score", 0))
        return d
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


# ── LAPIS 2: status dry-run & universe (baca DB) ────────────────────────────
def dryrun_summary():
    """Ringkasan dry-run kedua gaya: equity, expectancy(R) — HEADLINE metric (bukan win-rate
    mentah; lihat AUDIT.md metodologi: hit-rate<50% wajar, ekspektasi datang dari R:R)."""
    from src.smc import arena
    return arena.summary()


def dryrun_positions(group: str | None = None):
    """List posisi TERBUKA saat ini (entry/SL/qty_remaining/TP bertahap yg sudah/belum kena)."""
    import json as _json
    from sqlalchemy import select
    from src.storage.db import SessionLocal
    from src.storage.models import DryRunTrade
    with SessionLocal() as s:
        q = select(DryRunTrade).where(DryRunTrade.status == "open")
        if group:
            q = q.where(DryRunTrade.group == group)
        rows = s.scalars(q).all()
        return [{"id": r.id, "symbol": r.symbol, "group": r.group, "leg": r.leg, "entry": r.entry,
                 "sl": r.sl, "qty_remaining": r.qty_remaining, "leverage": r.leverage,
                 "risk_usd": r.risk_usd, "full_score": r.full_score, "zone": r.zone,
                 "tps": _json.loads(r.tps)} for r in rows]


def tier_list(tier: str | None = None):
    """Universe: koin CEX (Binance) mcap>=$300M, tier S/A/B/C berdasar volume 24h."""
    from sqlalchemy import select
    from src.storage.db import SessionLocal
    from src.storage.models import Token
    with SessionLocal() as s:
        q = select(Token).where(Token.in_watchlist.is_(True))
        if tier:
            q = q.where(Token.tier == tier.upper())
        rows = s.scalars(q.order_by(Token.market_cap.desc())).all()
        return [{"symbol": r.symbol, "name": r.name, "market_cap": r.market_cap,
                 "volume_24h": r.volume_24h, "tier": r.tier, "cmc_rank": r.cmc_rank} for r in rows]


def screening_highlights(group: str | None = None, full_strong_only: bool = True):
    """Kandidat sinyal TERBARU (dari snapshot scan terakhir) — full_strong (|score|>=2) by
    default. Sumber: SignalSnapshot, diisi tiap screen_place() jalan."""
    from sqlalchemy import select, desc
    from src.storage.db import SessionLocal
    from src.storage.models import SignalSnapshot
    with SessionLocal() as s:
        q = select(SignalSnapshot)
        if group:
            q = q.where(SignalSnapshot.group == group)
        if full_strong_only:
            q = q.where(SignalSnapshot.full_strong.is_(True))
        rows = s.scalars(q.order_by(desc(SignalSnapshot.ts)).limit(60)).all()
        return [{"symbol": r.symbol, "group": r.group, "ts": r.ts.isoformat() if r.ts else None,
                 "full_score": r.full_score, "zone": r.zone, "high_confluence": r.high_confluence,
                 "confirmed": r.confirmed, "direction": r.direction, "entry": r.entry, "sl": r.sl,
                 "reason": r.reason} for r in rows]


# ── LAPIS 3: akses data generik (READ-ONLY) — pola & guard sama persis dgn
# crypto-trader-agent-system: SELECT/WITH saja, path proyek saja, file rahasia diblokir. ──
def db_query(query: str, limit: int = 200):
    """Query SQL READ-ONLY (SELECT/WITH). Tabel: dryrun_trade, dryrun_fill, token,
    signal_snapshot, chat_session. Tulis/ubah skema DITOLAK."""
    q = (query or "").strip().rstrip(";").strip()
    if not q:
        return {"error": "query kosong"}
    low = q.lower()
    if not (low.startswith("select") or low.startswith("with")):
        return {"error": "read-only: cuma SELECT / WITH yang diizinkan"}
    if _WRITE_KW.search(low):
        return {"error": "read-only: kata kunci yang mengubah data/skema ditolak"}
    if ";" in q:
        return {"error": "satu statement saja (tanpa ';')"}
    lim = max(1, min(int(limit or 200), 1000))
    from src import config
    url = config.DATABASE_URL
    try:
        if url.startswith("sqlite:///"):
            import sqlite3
            path = url[len("sqlite:///"):]
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                cur = con.execute(q)
                cols = [d[0] for d in (cur.description or [])]
                rows = [dict(r) for r in cur.fetchmany(lim)]
            finally:
                con.close()
        else:
            from sqlalchemy import text
            from src.storage.db import engine
            with engine.connect() as c:
                res = c.execute(text(q))
                cols = list(res.keys())
                rows = [dict(zip(cols, r)) for r in res.fetchmany(lim)]
        return {"columns": cols, "rows": rows, "n": len(rows), "truncated": len(rows) >= lim}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:300]}


def _safe_target(path: str):
    target = _os.path.abspath(_os.path.join(_PROJECT_ROOT, path or ""))
    if target != _PROJECT_ROOT and not target.startswith(_PROJECT_ROOT + _os.sep):
        return None, {"error": "akses ditolak: di luar direktori proyek"}
    low = target.lower()
    base = _os.path.basename(low)
    if (low.endswith((".db", ".db-wal", ".db-shm", ".key", ".pem", ".sqlite")) or base.startswith(".env")
            or ".env" in base or any(h in low for h in _SECRET_HINT)):
        return None, {"error": "file sensitif (rahasia/DB) tak boleh diakses lewat sini"}
    return target, None


def read_file(path: str):
    """Baca isi 1 file teks dalam direktori proyek (READ-ONLY). File rahasia (.env/*.db/kredensial)
    diblokir. Maks 200KB."""
    target, err = _safe_target(path)
    if err:
        return err
    if not _os.path.isfile(target):
        return {"error": "file tak ada"}
    if _os.path.getsize(target) > 200_000:
        return {"error": "file terlalu besar (>200KB)"}
    try:
        txt = open(target, encoding="utf-8", errors="replace").read()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}
    return {"path": _os.path.relpath(target, _PROJECT_ROOT), "bytes": len(txt), "content": txt[:60000]}


def list_dir(path: str = "."):
    """List isi 1 direktori dalam proyek (READ-ONLY)."""
    target, err = _safe_target(path)
    if err:
        return err
    if not _os.path.isdir(target):
        return {"error": "bukan direktori"}
    out = []
    for name in sorted(_os.listdir(target)):
        if name.startswith(".") or name in ("__pycache__", "node_modules", ".venv", "venv"):
            continue
        full = _os.path.join(target, name)
        out.append({"name": name, "type": "dir" if _os.path.isdir(full) else "file",
                    "size": _os.path.getsize(full) if _os.path.isfile(full) else None})
    return {"dir": _os.path.relpath(target, _PROJECT_ROOT), "entries": out}


# ── LAPIS 4: PERINTAH operasi (write/execute) — BOUNDED & NON-DESTRUKTIF ────
# Sama prinsip dgn crypto-trader-agent-system: hanya operasi rutin yg cron jg jalanin.
# TANPA reset (destruktif -> gate manusia via UI+confirm), TANPA shell/file-write bebas,
# TANPA ubah kode/parameter (itu usulan buat developer, lihat _CHAT_SYS di app.py).
def _run_capture(fn):
    buf = _io.StringIO()
    try:
        with _ctx.redirect_stdout(buf):
            r = fn()
        out = buf.getvalue().strip()
        return {"log": out or "selesai", "result": r if isinstance(r, (dict, list, int, float, str)) else str(r)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def rnd_step(symbols: str = ""):
    """PERINTAH: jalankan 1 siklus dry-run (kelola posisi terbuka + scan sinyal baru, kedua
    gaya). symbols opsional: daftar simbol dipisah koma (kosong = seluruh universe). Non-
    destruktif (trade virtual). Sama dgn job cron."""
    from src.smc import arena
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    return _run_capture(lambda: arena.step(symbols=syms))


def rnd_universe_refresh():
    """PERINTAH: refresh universe dari CoinMarketCap (mcap>=$300M, exclude stablecoin/gold-
    index/derivative) + tier ulang berdasar volume 24h. Non-destruktif (update data koin)."""
    from src.smc import universe
    return _run_capture(universe.build)


# registry: nama -> (impl, schema-parameter, deskripsi)
_TF = {"type": "string", "enum": ["5m", "15m", "1h", "4h", "1d"]}
_SYM = {"symbol": {"type": "string", "description": "simbol koin, mis. BTC / ETH / SOL"}}

_SKILLS = {
    "fvg_analyze": (fvg_analyze, _p({**_SYM, "timeframe": _TF}, ["symbol"]), fvg_analyze.__doc__.strip()),
    "structure_analyze": (structure_analyze, _p({**_SYM, "timeframe": _TF}, ["symbol"]), structure_analyze.__doc__.strip()),
    "sentiment_analyze": (sentiment_analyze, _p(_SYM, ["symbol"]), sentiment_analyze.__doc__.strip()),
    "momentum_analyze": (momentum_analyze, _p({**_SYM, "timeframe": _TF}, ["symbol"]), momentum_analyze.__doc__.strip()),
    "confluence_signal": (confluence_signal,
        _p({**_SYM, "style": {"type": "string", "enum": ["scalp", "swing"]}}, ["symbol"]),
        confluence_signal.__doc__.strip()),
    "dryrun_summary": (dryrun_summary, _p({}, []), dryrun_summary.__doc__.strip()),
    "dryrun_positions": (dryrun_positions,
        _p({"group": {"type": "string", "enum": ["scalp", "swing"]}}, []), dryrun_positions.__doc__.strip()),
    "tier_list": (tier_list, _p({"tier": {"type": "string", "enum": ["S", "A", "B", "C"]}}, []), tier_list.__doc__.strip()),
    "screening_highlights": (screening_highlights,
        _p({"group": {"type": "string", "enum": ["scalp", "swing"]}, "full_strong_only": {"type": "boolean"}}, []),
        screening_highlights.__doc__.strip()),
    "db_query": (db_query, _p({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]), db_query.__doc__.strip()),
    "read_file": (read_file, _p({"path": {"type": "string"}}, ["path"]), read_file.__doc__.strip()),
    "list_dir": (list_dir, _p({"path": {"type": "string"}}, []), list_dir.__doc__.strip()),
    "rnd_step": (rnd_step, _p({"symbols": {"type": "string"}}, []), rnd_step.__doc__.strip()),
    "rnd_universe_refresh": (rnd_universe_refresh, _p({}, []), rnd_universe_refresh.__doc__.strip()),
}


def tools_spec() -> list[dict]:
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": p}}
            for n, (_fn, p, d) in _SKILLS.items()]


def tool_impls() -> dict:
    return {n: fn for n, (fn, _p, _d) in _SKILLS.items()}
