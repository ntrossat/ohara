"""All state in one SQLite file in the data volume: settings, sign-in sessions, OAuth grants,
cached access checks, and the search index.

State is a set of JSON records keyed by kind and key. A record with `expires_at` disappears
once that time has passed.
"""

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ohara.config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    expires_at REAL,
    PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS records_expiry ON records (expires_at);
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(path UNINDEXED, title, body, tokenize = 'porter unicode61');
"""
LIVE = "(expires_at IS NULL OR expires_at > ?)"
BUSY_TIMEOUT = 10  # seconds to wait for another connection's write

_ready: set[str] = set()


def path() -> Path:
    return data_dir() / "ohara.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """A connection whose changes are committed together when the block ends."""
    target = path()
    if str(target) not in _ready:
        _init(target)
    conn = sqlite3.connect(target, timeout=BUSY_TIMEOUT)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _init(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(target, os.O_WRONLY | os.O_CREAT, 0o600))  # readable only by the owner
    conn = sqlite3.connect(target, timeout=BUSY_TIMEOUT)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
    _ready.add(str(target))


def get(kind: str, key: str) -> Any:
    with connect() as conn:
        row = conn.execute(f"SELECT value FROM records WHERE kind = ? AND key = ? AND {LIVE}", (kind, key, time.time())).fetchone()
    return json.loads(row[0]) if row else None


def all(kind: str) -> dict:
    with connect() as conn:
        rows = conn.execute(f"SELECT key, value FROM records WHERE kind = ? AND {LIVE} ORDER BY rowid", (kind, time.time()))
        return {key: json.loads(value) for key, value in rows}


def put(kind: str, key: str, value: Any, expires_at: float | None = None, conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        with connect() as conn:
            return put(kind, key, value, expires_at, conn)
    conn.execute("DELETE FROM records WHERE expires_at <= ?", (time.time(),))
    conn.execute(
        "INSERT INTO records (kind, key, value, expires_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
        (kind, key, json.dumps(value), expires_at),
    )


def pop(kind: str, key: str) -> Any:
    """Remove a record and return its value, or None. Only one caller ever gets a given record."""
    with connect() as conn:
        row = conn.execute(
            f"DELETE FROM records WHERE kind = ? AND key = ? AND {LIVE} RETURNING value", (kind, key, time.time())
        ).fetchone()
    return json.loads(row[0]) if row else None


def delete(kind: str, key: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM records WHERE kind = ? AND key = ?", (kind, key))


def delete_kind(kind: str, conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        with connect() as conn:
            return delete_kind(kind, conn)
    conn.execute("DELETE FROM records WHERE kind = ?", (kind,))


def delete_where(kinds: tuple[str, ...], field: str, value: Any) -> None:
    """Remove the records of these kinds whose JSON `field` equals `value`."""
    marks = ", ".join("?" * len(kinds))
    with connect() as conn:
        conn.execute(f"DELETE FROM records WHERE kind IN ({marks}) AND json_extract(value, '$.' || ?) = ?", (*kinds, field, value))


def keep_newest(kind: str, count: int) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM records WHERE kind = ? AND rowid NOT IN"
            " (SELECT rowid FROM records WHERE kind = ? ORDER BY rowid DESC LIMIT ?)",
            (kind, kind, count),
        )


def replace_pages(rows: list[tuple[str, str, str]]) -> None:
    """Replace the search index with these (path, title, text) rows."""
    with connect() as conn:
        conn.execute("DELETE FROM pages")
        conn.executemany("INSERT INTO pages (path, title, body) VALUES (?, ?, ?)", rows)


def search_pages(words: list[str], limit: int) -> list[tuple[str, str, str]]:
    """(path, title, snippet) of the pages containing every word, best matches first. Titles weigh more than text."""
    match = " ".join('"' + word.replace('"', '""') + '"' for word in words)
    with connect() as conn:
        return conn.execute(
            "SELECT path, title, snippet(pages, 2, '', '', '…', 32) FROM pages"
            " WHERE pages MATCH ? ORDER BY bm25(pages, 0, 10, 1) LIMIT ?",
            (match, limit),
        ).fetchall()
