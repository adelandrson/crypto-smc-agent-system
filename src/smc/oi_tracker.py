"""Persistent Open-Interest change tracker — the OI confluence leg.

The OI leg of confluence is *directional*: rising OI + rising price = trend
confirmation (+1); rising OI + falling price = bearish pressure (-1). That needs
the PREVIOUS OI and close, which a stateless one-shot cron call does not have.

This tiny SQLite store keeps `{last_oi, last_close}` per symbol across runs so
`router.data_for_symbol` / `fetch_market_data.py` can compute a real `oi_score`
on the live path (previously only the paper engine could, in-memory).

Same scoring logic as `paper/engine.PaperTradingEngine._oi_score`, but persisted
and shared. Degrades to 0 when there is no prior sample (first run / venue down).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(os.getenv(       # path adapted: default to repo root (was plugin root), env var renamed to this project
    "SMC_OI_DB", str(Path(__file__).resolve().parents[2] / ".oi_state.sqlite")))


class OITracker:
    """Thread-safe per-symbol {last_oi, last_close} store → OI confluence leg."""

    def __init__(self, db_path: Optional[str] = None):
        self._db = str(db_path) if db_path else str(_DEFAULT_DB)
        self._lock = threading.Lock()
        self._init()

    def _conn(self):
        # check_same_thread=False — access guarded by self._lock
        return sqlite3.connect(self._db, check_same_thread=False)

    def _init(self):
        with self._lock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS oi_state (
                symbol TEXT PRIMARY KEY,
                last_oi REAL,
                last_close REAL
            )""")

    def score(self, symbol: str, total_oi: Optional[float],
              close: Optional[float]) -> int:
        """Return the OI confluence leg (+1/0/-1) and persist the new sample.

        +1 : OI rose and price rose (or OI fell and price fell -> long unwind
             is bearish, so that path returns -1 via the same sign rule).
        -1 : OI rose and price fell.
         0 : no prior data, equal, or missing inputs.
        """
        if total_oi is None or close is None:
            return 0
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT last_oi, last_close FROM oi_state WHERE symbol=?", (symbol,)
            ).fetchone()
            score = 0
            if row and row[0] is not None and row[1] is not None:
                prev_oi, prev_close = row
                if total_oi > prev_oi:
                    score = 1 if close > prev_close else (-1 if close < prev_close else 0)
                # falling OI is a position-unwind signal, not a fresh-trend leg -> 0
            c.execute(
                "INSERT INTO oi_state(symbol,last_oi,last_close) VALUES(?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET last_oi=excluded.last_oi, "
                "last_close=excluded.last_close",
                (symbol, float(total_oi), float(close)))
        return score

    def reset(self, symbol: Optional[str] = None):
        with self._lock, self._conn() as c:
            if symbol:
                c.execute("DELETE FROM oi_state WHERE symbol=?", (symbol,))
            else:
                c.execute("DELETE FROM oi_state")
