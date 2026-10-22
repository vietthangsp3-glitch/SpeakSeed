"""Transactional, repeatable SQLite migration runner."""
from pathlib import Path
import sqlite3


def run_migrations(db_path: Path, migrations_dir: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        applied = {row[0] for row in con.execute("SELECT version FROM schema_migrations")}
        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name in applied:
                continue
            script = path.read_text(encoding="utf-8")
            con.executescript("BEGIN IMMEDIATE;\n" + script + f"\nINSERT INTO schema_migrations(version) VALUES('{path.name}');\nCOMMIT;")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
