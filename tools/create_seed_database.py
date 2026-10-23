"""Create a content-only install seed without modifying the working database."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


EXPECTED = {"library_words": 6280, "grammar_lessons": 100, "grammar_exercises": 1000}


def create_seed(source: Path, destination: Path) -> None:
    if destination.exists(): raise FileExistsError(destination)
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst); dst.execute("PRAGMA foreign_keys=ON")
        dst.execute("DELETE FROM users")
        dst.execute("DELETE FROM auth_rate_limits")
        dst.execute("DELETE FROM ai_usage")
        dst.commit()
        for table, expected in EXPECTED.items():
            actual = dst.execute(f"SELECT COUNT(*) FROM {table} WHERE reviewed=1" if table == "library_words" else f"SELECT COUNT(*) FROM {table} WHERE published=1").fetchone()[0]
            if actual != expected: raise RuntimeError(f"{table}: cần {expected}, có {actual}")
        if dst.execute("SELECT COUNT(*) FROM users").fetchone()[0]: raise RuntimeError("Seed còn dữ liệu tài khoản")
        if dst.execute("PRAGMA foreign_key_check").fetchall(): raise RuntimeError("Seed có lỗi foreign key")
        dst.execute("VACUUM")
    except Exception:
        dst.close(); destination.unlink(missing_ok=True); raise
    finally:
        try: dst.close()
        except Exception: pass
        src.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path); parser.add_argument("destination", type=Path)
    args = parser.parse_args(); create_seed(args.source, args.destination)

