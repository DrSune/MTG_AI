"""ID <-> name resolution against the card / vocabulary tables.

PERFORMANCE NOTE, do not undo this. The original implementation opened a fresh
``sqlite3.connect()`` on every single lookup. The engine performs roughly 70 lookups
per game step, so a single Commander game cost tens of thousands of connections and
the mapper alone accounted for a large share of engine wall time. Memoising the two
lookup functions measured a **3.2x** end-to-end speedup of the engine loop
(24.9 ms/step -> 7.8 ms/step) with no other change.

The tables are static for the lifetime of a process: ``game_vocabulary`` is 86 rows and
``cards`` is written only by the offline ingest step. Caching is therefore safe. If you
ever mutate either table in-process, call :func:`clear_caches` afterwards.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Dict, Optional, Tuple

_VALID_TABLES = ("cards", "game_vocabulary")

# Process-wide caches keyed by (db_path, table, key). Shared across every
# IDToNameMapper instance, of which the codebase constructs many.
_name_cache: Dict[Tuple[str, str, int], Optional[str]] = {}
_id_cache: Dict[Tuple[str, str, str], Optional[int]] = {}
_conn_cache: Dict[Tuple[str, int], sqlite3.Connection] = {}
_lock = threading.Lock()


def _connection(db_path: str) -> sqlite3.Connection:
    """One read-only-ish connection per (path, thread). sqlite3 objects are not
    thread-safe by default, so key on the thread id rather than sharing."""
    key = (db_path, threading.get_ident())
    conn = _conn_cache.get(key)
    if conn is None:
        conn = sqlite3.connect(db_path)
        _conn_cache[key] = conn
    return conn


def clear_caches() -> None:
    """Drop every cached lookup and connection. Call after mutating the tables."""
    with _lock:
        _name_cache.clear()
        _id_cache.clear()
        for conn in _conn_cache.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _conn_cache.clear()


class IDToNameMapper:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)

    def get_name(self, _id: int, table_name: str) -> Optional[str]:
        key = (self.db_path, table_name, _id)
        try:
            return _name_cache[key]
        except KeyError:
            pass

        name = None
        if table_name == "cards":
            row = _connection(self.db_path).execute(
                "SELECT name FROM cards WHERE card_id = ?", (_id,)
            ).fetchone()
            name = row[0] if row else None
        elif table_name == "game_vocabulary":
            row = _connection(self.db_path).execute(
                "SELECT name FROM game_vocabulary WHERE id = ?", (_id,)
            ).fetchone()
            name = row[0] if row else None

        _name_cache[key] = name
        return name

    def get_id_by_name(self, name: str, table_name: str) -> Optional[int]:
        key = (self.db_path, table_name, name)
        try:
            return _id_cache[key]
        except KeyError:
            pass

        _id = None
        if table_name == "cards":
            # Card names are not unique across printings; CardDataLoader owns card
            # identity. This path exists only for legacy callers.
            row = _connection(self.db_path).execute(
                "SELECT card_id FROM cards WHERE name = ?", (name,)
            ).fetchone()
            _id = row[0] if row else None
        elif table_name == "game_vocabulary":
            row = _connection(self.db_path).execute(
                "SELECT id FROM game_vocabulary WHERE name = ?", (name,)
            ).fetchone()
            _id = row[0] if row else None

        _id_cache[key] = _id
        return _id

    def prewarm(self) -> None:
        """Load both whole tables into the caches in two queries.

        Worth calling once at process start in an environment worker: it removes
        every remaining per-lookup query from the hot loop.
        """
        conn = _connection(self.db_path)
        for table, id_col in (("game_vocabulary", "id"), ("cards", "card_id")):
            try:
                rows = conn.execute(f"SELECT {id_col}, name FROM {table}").fetchall()
            except sqlite3.Error:
                continue
            for row_id, row_name in rows:
                _name_cache[(self.db_path, table, row_id)] = row_name
                _id_cache.setdefault((self.db_path, table, row_name), row_id)
