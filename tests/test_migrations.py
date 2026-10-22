import sqlite3
from pathlib import Path

from migrations import run_migrations


ROOT = Path(__file__).resolve().parents[1]


def test_migrations_are_repeatable_on_fresh_database(tmp_path):
    database = tmp_path / "fresh.db"
    run_migrations(database, ROOT / "migrations")
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database)
    versions = con.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert len(versions) == len(list((ROOT / "migrations").glob("*.sql")))
    columns = {row[1] for row in con.execute("PRAGMA table_info(progress)")}
    assert {"due_at", "interval_days", "ease_factor", "repetitions", "lapses"} <= columns
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"grammar_units", "grammar_lessons", "grammar_exercises", "grammar_attempts",
            "grammar_lesson_progress", "grammar_unit_progress", "auth_rate_limits", "ai_usage"} <= tables
    session_columns = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    assert {"csrf_hash", "ip_hash", "user_agent_hash"} <= session_columns
