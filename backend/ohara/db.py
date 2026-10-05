"""All state in one SQLite file in the data volume: settings, sign-in sessions, OAuth grants,
cached access checks, and the search index.

State is a set of JSON records keyed by kind and key. A record with `expires_at` disappears
once that time has passed. JSON files from earlier versions are imported on first start.
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager

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

_ready: set[str] = set()


def path():
    return data_dir() / "ohara.db"


@contextmanager
def connect():
    """A connection whose changes are committed together when the block ends."""
    target = path()
    if str(target) not in _ready:
        _init(target)
    conn = sqlite3.connect(target, timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _init(target) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(target, os.O_WRONLY | os.O_CREAT, 0o600))  # readable only by the owner
    conn = sqlite3.connect(target, timeout=10)
    try:
        conn.executescript(SCHEMA)
        with conn:
            imported = _import_json(conn)
    finally:
        conn.close()
    for source in imported:  # only once the import is committed
        source.rename(source.with_suffix(".json.imported"))
    _ready.add(str(target))


def get(kind: str, key: str):
    with connect() as conn:
        row = conn.execute(f"SELECT value FROM records WHERE kind = ? AND key = ? AND {LIVE}", (kind, key, time.time())).fetchone()
    return json.loads(row[0]) if row else None


def all(kind: str) -> dict:
    with connect() as conn:
        rows = conn.execute(f"SELECT key, value FROM records WHERE kind = ? AND {LIVE} ORDER BY rowid", (kind, time.time()))
        return {key: json.loads(value) for key, value in rows}


def put(kind: str, key: str, value, expires_at: float | None = None, conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        with connect() as conn:
            return put(kind, key, value, expires_at, conn)
    conn.execute("DELETE FROM records WHERE expires_at <= ?", (time.time(),))
    conn.execute(
        "INSERT INTO records (kind, key, value, expires_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
        (kind, key, json.dumps(value), expires_at),
    )


def pop(kind: str, key: str):
    """Remove a record and return its value, or None. Only one caller ever gets a given record."""
    with connect() as conn:
        row = conn.execute(
            f"DELETE FROM records WHERE kind = ? AND key = ? AND {LIVE} RETURNING value", (kind, key, time.time())
        ).fetchone()
    return json.loads(row[0]) if row else None


def delete(kind: str, key: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM records WHERE kind = ? AND key = ?", (kind, key))


def delete_where(kinds: tuple[str, ...], field: str, value) -> None:
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


def _import_json(conn: sqlite3.Connection) -> list:
    """Import the JSON files written by earlier versions. Returns the files to set aside."""

    def read(name: str) -> dict:
        try:
            return json.loads((data_dir() / name).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    for key, value in read("settings.json").items():
        put("settings", key, value, conn=conn)
    for sid, session in read("sessions.json").items():
        put("session", sid, session, time.time() + 30 * 24 * 3600, conn=conn)
    oauth = read("oauth.json")
    for client_id, client in oauth.get("clients", {}).items():
        put("client", client_id, client, conn=conn)
    for kind in ("access", "refresh"):
        for key, token in oauth.get(kind, {}).items():
            put(kind, key, token, token["expires_at"], conn=conn)
    return [data_dir() / name for name in ("settings.json", "sessions.json", "oauth.json") if (data_dir() / name).exists()]
