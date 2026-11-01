"""SQLite access layer: connection helper, query helpers and schema bootstrap.

All SQL in this project is parameterised (no string-built queries from user input).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_FILE.read_text())
        conn.commit()
    finally:
        conn.close()


def rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def row(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict | None:
    r = conn.execute(sql, tuple(params)).fetchone()
    return dict(r) if r else None


def scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    r = conn.execute(sql, tuple(params)).fetchone()
    return r[0] if r else None


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement and return lastrowid."""
    cur = conn.execute(sql, tuple(params))
    return cur.lastrowid


def audit(conn: sqlite3.Connection, actor_id: int | None, action: str, entity: str, entity_id: int | None, detail: str = "") -> None:
    execute(
        conn,
        "INSERT INTO audit_log (actor_id, action, entity, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, entity, entity_id, detail[:500]),
    )


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
