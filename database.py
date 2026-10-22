"""Small DB-API compatibility layer for SQLite and PostgreSQL.

The application historically uses qmark parameters and sqlite Row objects. This
module keeps that API while allowing a migrated PostgreSQL database to use
psycopg. Schema creation/import remains explicit and is never performed against
PostgreSQL during normal app startup.
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


POSTGRES_PREFIXES = ("postgres://", "postgresql://")
IDENTITY_TABLES = {
    "users", "placement_attempts", "skill_lessons", "skill_questions",
    "speaking_sessions", "writing_drafts", "learning_events", "import_runs",
    "library_words", "library_grammar", "library_sentences", "library_exercises",
    "grammar_units", "grammar_lessons", "grammar_examples", "grammar_exercises",
    "ai_usage",
}


def configured_database(default_sqlite: Path) -> Path | str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if not url.startswith(POSTGRES_PREFIXES):
            raise RuntimeError("DATABASE_URL chỉ hỗ trợ postgres:// hoặc postgresql://")
        return url
    if os.getenv("VERCEL") == "1":
        raise RuntimeError(
            "DATABASE_URL PostgreSQL bắt buộc trên Vercel; không được lưu dữ liệu người dùng vào filesystem serverless"
        )
    return Path(os.getenv("DB_PATH", str(default_sqlite)))


def is_postgres(target: Path | str) -> bool:
    return isinstance(target, str) and target.startswith(POSTGRES_PREFIXES)


class HybridRow:
    def __init__(self, values, names: list[str] | None = None):
        if isinstance(values, Mapping):
            self._values = list(values.values()); self._keys = list(values.keys())
        else:
            self._values = list(values); raw_names = names or [str(index) for index in range(len(self._values))]
            seen = {}; self._keys = []
            for name in raw_names:
                seen[name] = seen.get(name, 0) + 1
                self._keys.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
        self._data = dict(zip(self._keys, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._data)

    def keys(self):
        return list(self._keys)


def _postgres_sql(statement: str) -> str:
    sql = statement.strip()
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    was_ignore = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", statement, flags=re.I))
    sql = sql.replace("?", "%s")
    sql = re.sub(r"\bMAX\(completed\s*,", "GREATEST(completed,", sql, flags=re.I)
    sql = re.sub(r"\bMAX\(attempted\s*,", "GREATEST(attempted,", sql, flags=re.I)
    sql = re.sub(r"\bMAX\(audio_evidence\s*,", "GREATEST(audio_evidence,", sql, flags=re.I)
    insert = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.I)
    if insert and "ON CONFLICT" in sql.upper():
        table = insert.group(1)
        # PostgreSQL treats an unqualified target column as ambiguous when the
        # EXCLUDED pseudo-table exposes the same name; SQLite accepts it.
        for column in ("attempts", "correct", "wrong", "completed", "attempted", "audio_evidence"):
            sql = re.sub(rf"(\b{column}\s*=\s*){column}\b", rf"\1{table}.{column}", sql, flags=re.I)
            sql = re.sub(rf"GREATEST\(\s*{column}\s*,", f"GREATEST({table}.{column},", sql, flags=re.I)
    if was_ignore and "ON CONFLICT" not in sql.upper():
        sql += " ON CONFLICT DO NOTHING"
    return sql


class CursorAdapter:
    def __init__(self, cursor, *, postgres: bool, lastrowid=None):
        self._cursor = cursor
        self._postgres = postgres
        self.lastrowid = lastrowid if postgres else getattr(cursor, "lastrowid", None)
        self.rowcount = getattr(cursor, "rowcount", -1)
        self._names = [column.name for column in (getattr(cursor, "description", None) or [])]

    def _wrap(self, row):
        if row is None or not self._postgres:
            return row
        return HybridRow(row, self._names)

    def fetchone(self):
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor:
            yield self._wrap(row)


class ConnectionAdapter:
    def __init__(self, connection, *, postgres: bool):
        self._connection = connection
        self.postgres = postgres

    def execute(self, statement: str, params=()):
        if not self.postgres:
            return self._connection.execute(statement, params)
        sql = _postgres_sql(statement)
        match = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.I)
        wants_id = bool(match and match.group(1).lower() in IDENTITY_TABLES and "RETURNING" not in sql.upper())
        if wants_id:
            sql += " RETURNING id"
        cursor = self._connection.execute(sql, params)
        lastrowid = cursor.fetchone()[0] if wants_id else None
        return CursorAdapter(cursor, postgres=True, lastrowid=lastrowid)

    def executemany(self, statement: str, params):
        if not self.postgres:
            return self._connection.executemany(statement, params)
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_sql(statement), params)
        return CursorAdapter(cursor, postgres=True)

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def connect_database(target: Path | str, *, timeout: int = 15) -> ConnectionAdapter:
    if is_postgres(target):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL cần cài psycopg[binary] từ requirements.txt") from exc
        connection = psycopg.connect(target, connect_timeout=timeout)
        return ConnectionAdapter(connection, postgres=True)
    connection = sqlite3.connect(Path(target), timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    return ConnectionAdapter(connection, postgres=False)


def require_postgres_schema(target: Path | str, minimum_version: str) -> None:
    with connect_database(target) as con:
        row = con.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        if not row or row["version"] < minimum_version:
            raise RuntimeError(
                f"PostgreSQL chưa có schema {minimum_version}; chạy tools/migrate_to_postgres.py trước"
            )
