"""Engine & session SQLAlchemy. Ganti DATABASE_URL untuk pindah SQLite→Postgres."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src import config
from src.storage.models import Base

engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


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
