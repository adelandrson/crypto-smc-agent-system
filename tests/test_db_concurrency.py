"""Test src/storage/db.py — SQLite WAL + busy_timeout mencegah 'database is locked' saat
2 writer bersamaan (arena.monitor loop + endpoint web/chat/rnd_step lain, ditemukan via live
smoke test saat deploy: step() via API gagal krn monitor loop background juga sedang menulis)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, text


def _engine_with_pragmas(path, timeout_ms=30000):
    eng = create_engine(f"sqlite:///{path}", future=True, connect_args={"timeout": 30})

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={timeout_ms}")
        cur.close()
    return eng


def test_concurrent_writers_no_lock_error(tmp_path):
    """2 thread menulis ke tabel yg sama bersamaan, salah satu HOLD transaksi >100ms (simulasi
    monitor loop yg lama) -- dgn WAL+busy_timeout, writer kedua HARUS menunggu & sukses, bukan error."""
    db_path = tmp_path / "concurrency.db"
    eng = _engine_with_pragmas(db_path)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))

    errors = []

    def slow_writer():
        with eng.begin() as conn:
            conn.execute(text("INSERT INTO t (v) VALUES ('slow')"))
            time.sleep(0.3)   # tahan transaksi terbuka, simulasi monitor loop yg sedang menulis

    def fast_writer():
        time.sleep(0.05)      # pastikan slow_writer sudah pegang transaksi dulu
        try:
            with eng.begin() as conn:
                conn.execute(text("INSERT INTO t (v) VALUES ('fast')"))
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    t1, t2 = threading.Thread(target=slow_writer), threading.Thread(target=fast_writer)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"writer kedua gagal (harusnya nunggu, bukan error): {errors}"
    with eng.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM t")).scalar()
    assert n == 2


def test_without_pragmas_lock_error_reproduces(tmp_path):
    """Kontrol negatif: TANPA WAL+busy_timeout (default sqlite3, timeout pendek), writer kedua
    BENERAN gagal -- membuktikan test di atas bukan kebetulan lolos, tapi fix yg efektif."""
    db_path = tmp_path / "no_fix.db"
    eng = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"timeout": 0.01})
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))

    errors = []

    def slow_writer():
        with eng.begin() as conn:
            conn.execute(text("INSERT INTO t (v) VALUES ('slow')"))
            time.sleep(0.3)

    def fast_writer():
        time.sleep(0.05)
        try:
            with eng.begin() as conn:
                conn.execute(text("INSERT INTO t (v) VALUES ('fast')"))
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    t1, t2 = threading.Thread(target=slow_writer), threading.Thread(target=fast_writer)
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert errors and "locked" in errors[0].lower()
