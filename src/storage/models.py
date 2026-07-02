"""Model ORM — crypto-smc-agent-system (metodologi FVG/SMC, terpisah dari crypto-trader-agent-system).

Skema sengaja RAMPING dibanding sistem pembanding: TANPA tabel holder/wallet/flow-onchain,
TANPA unlock/risk-flag/X-sentiment/dev-activity — fitur itu memang tak ada di metodologi
sumber (~/Downloads/agent-trading_final) & sengaja dikecualikan (lihat plan). Yang ADA di sini
murni utk menjalankan & menampilkan metodologi confluence (FVG+Fib+OB+struktur+OI+FR+LSR+CVD).
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Datetime selalu disimpan & dibaca sebagai UTC-aware (lihat crypto-trader-agent-system
    utk alasan lengkap: SQLite tak simpan tzinfo → tanpa ini aritmetika waktu meleset lintas-TZ)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class Token(Base):
    """Universe: koin CEX (Binance) mcap >= $300M, exclude stablecoin/gold-index/derivative.
    `tier` dikalibrasi dari volume 24h (S/A/B/C) — lihat src/smc/universe.py."""

    __tablename__ = "token"

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True)   # CMC id
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    market_cap: Mapped[float | None] = mapped_column(Float)
    volume_24h: Mapped[float | None] = mapped_column(Float)
    cmc_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)  # legacy (=swing_tier)
    scalp_tier: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)  # S/A/B/C mcap40/vol60
    swing_tier: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)  # S/A/B/C mcap60/vol40
    scalp_score: Mapped[float | None] = mapped_column(Float)
    swing_score: Mapped[float | None] = mapped_column(Float)
    tradable: Mapped[bool] = mapped_column(Boolean, default=False)     # listed Binance perp/spot
    # None = ditrack; selain itu: stablecoin | tokenized-gold | wrapped-tokens | liquid-staking | derivative
    exclude_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    in_watchlist: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())


class DryRunTrade(Base):
    """Posisi dry-run (parent, 1 baris = 1 posisi). SL & qty EVOLVE seiring TP bertahap
    terisi (lihat DryRunFill utk tiap partial-close) — mengikuti persis struktur
    paper/broker.py (Position dataclass) dari metodologi sumber, dipersist ke SQL.

    `tps` = JSON list rencana TP bertahap (dari src/smc/risk.tp_targets): tiap elemen
    {label, price, frac, filled, sl_after}. `full_score`/`zone`/`high_confluence` = snapshot
    confluence SAAT entry (audit trail — kenapa sinyal ini diambil)."""

    __tablename__ = "dryrun_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(24), index=True)          # Wira·scalp | Wira·swing
    group: Mapped[str] = mapped_column(String(8), index=True)           # scalp | swing
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    leg: Mapped[str] = mapped_column(String(8))                         # long | short
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | open | closed | canceled
    placed_ts: Mapped[datetime | None] = mapped_column(UTCDateTime())   # saat LIMIT order dipasang (pending)
    mark_price: Mapped[float | None] = mapped_column(Float)             # harga pasar saat sinyal (limit=entry di bawah/atas ini)
    entry_ts: Mapped[datetime | None] = mapped_column(UTCDateTime())    # = placed_ts saat pending; ditimpa waktu fill saat terisi
    entry: Mapped[float] = mapped_column(Float)                         # harga LIMIT (=harga fill saat terisi, maker)
    sl: Mapped[float] = mapped_column(Float)                            # mutable: BE -> lock-TP1 -> trail
    original_qty: Mapped[float] = mapped_column(Float)
    qty_remaining: Mapped[float] = mapped_column(Float)
    leverage: Mapped[int] = mapped_column(Integer)
    risk_frac: Mapped[float] = mapped_column(Float)                     # %equity dipertaruhkan
    risk_usd: Mapped[float] = mapped_column(Float)
    margin_usd: Mapped[float] = mapped_column(Float)                    # modal terkomit (notional/leverage, capped)
    tps: Mapped[str] = mapped_column(Text)                              # JSON: rencana TP bertahap (risk.tp_targets)
    trail: Mapped[float | None] = mapped_column(Float)                  # fraksi trailing AKTIF (TP terakhir yg set mode=trail menang — sama spt Position.trail sumber)
    # ── snapshot confluence saat entry (audit) ──
    full_score: Mapped[int] = mapped_column(Integer)                    # -4..+4
    zone: Mapped[str] = mapped_column(String(16))                       # premium | discount | equilibrium
    high_confluence: Mapped[bool] = mapped_column(Boolean, default=False)  # A+ flag
    fr_score: Mapped[int | None] = mapped_column(Integer)
    oi_score: Mapped[int | None] = mapped_column(Integer)
    lsr_score: Mapped[int | None] = mapped_column(Integer)
    # ── hasil akhir (terisi saat status=closed) ──
    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)  # akumulasi lintas partial-fill
    r_multiple: Mapped[float | None] = mapped_column(Float)              # realized_pnl_usd / risk_usd
    outcome: Mapped[str | None] = mapped_column(String(12))              # tp_full | sl | moonbag
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class DryRunFill(Base):
    """1 baris = 1 partial-close (TP1/TP2/.../SL/moonbag) — audit trail TP bertahap,
    dipakai jg utk progress-bar TP-ladder di UI Agent."""

    __tablename__ = "dryrun_fill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, ForeignKey("dryrun_trade.id"), index=True)
    label: Mapped[str] = mapped_column(String(16))          # TP1 | TP2 | TP3 | TP4 | moonbag | SL
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    pnl_usd: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(UTCDateTime())


class SignalSnapshot(Base):
    """Cache hasil scan confluence (scalp+swing) — isi halaman Sinyal, refresh tiap cadence.
    `full_score`/`zone`/dst = output analyze_confluence(); `entry`/`sl`/`tps` = rencana kalau
    diambil (belum tentu dieksekusi — lihat DryRunTrade utk yg beneran dibuka)."""

    __tablename__ = "signal_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    group: Mapped[str] = mapped_column(String(8), index=True)   # scalp | swing
    full_score: Mapped[int] = mapped_column(Integer)
    full_strong: Mapped[bool] = mapped_column(Boolean, default=False)
    high_confluence: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    zone: Mapped[str | None] = mapped_column(String(16))
    direction: Mapped[int | None] = mapped_column(Integer)      # +1 long, -1 short
    entry: Mapped[float | None] = mapped_column(Float)
    sl: Mapped[float | None] = mapped_column(Float)
    tps_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(120))     # kalau skip: alasan (SKIP filter mana)
    detail_json: Mapped[str | None] = mapped_column(Text)       # snapshot penuh analyze_confluence()


class ChatSession(Base):
    """Histori sesi chat user <-> Orchestrator (Orin) — memori agent persisten. Sama persis
    dgn pola crypto-trader-agent-system (ChatSession): [{role,content}] JSON, resume via id."""

    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    n_messages: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
