"""Engine & session SQLAlchemy. Ganti DATABASE_URL untuk pindah SQLite→Postgres."""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from src import config
from src.storage.models import Base

# connect_args timeout=30 (SQLite): PENTING di sistem ini krn ADA writer background terus-menerus
# (arena.monitor loop tiap MONITOR_INTERVAL detik) + writer on-demand (endpoint web/chat/rnd_step) —
# tanpa ini, writer kedua langsung gagal "database is locked" (default sqlite3 timeout=5s, sering
# kepotong). WAL mode (di bawah) tambah lagi: reader tak diblokir writer, lock jauh lebih jarang.
_connect_args = {"timeout": 30} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")     # reader tak diblokir writer (beda dari default rollback-journal)
        cur.execute("PRAGMA busy_timeout=30000")    # ms — tunggu lock lepas, jangan langsung error
        cur.close()


def _ensure_columns() -> None:
    """Auto-migrasi RINGAN: tambah kolom yg ada di model tapi belum di tabel (ADD COLUMN, non-destruktif).
    Cegah drift skema (kolom baru di model → query tabel lama crash). Hanya kolom nullable/ber-default."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    todo = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            if not col.nullable and col.default is None and col.server_default is None:
                continue                          # SQLite tak bisa ADD COLUMN NOT NULL tanpa default → lewati
            todo.append((table.name, col.name, col.type.compile(dialect=engine.dialect)))
    if not todo:
        return
    with engine.begin() as conn:
        for tname, cname, ctype in todo:
            try:                                  # quote identifier → aman utk kata-kunci SQL (mis. 'group')
                conn.execute(text(f'ALTER TABLE "{tname}" ADD COLUMN "{cname}" {ctype}'))
            except Exception:
                pass                              # best-effort; jangan patahkan startup


def init_db() -> None:
    """Buat tabel bila belum ada + sinkron kolom (auto-migrasi ringan)."""
    Base.metadata.create_all(engine)
    _ensure_columns()
