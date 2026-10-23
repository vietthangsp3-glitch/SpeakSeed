"""Read-only Phase-2 staging evidence report."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def scalar(con: sqlite3.Connection, sql: str):
    return con.execute(sql).fetchone()[0]


def inspect(path: Path) -> dict:
    con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        result = {
            "path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "integrity": scalar(con, "PRAGMA integrity_check"),
            "foreign_key_errors": len(con.execute("PRAGMA foreign_key_check").fetchall()),
            "schema": scalar(con, "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"),
            "tables": scalar(con, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"),
        }
        for table in ("library_words", "grammar_lessons", "grammar_exercises", "users", "progress"):
            result[table] = scalar(con, f"SELECT COUNT(*) FROM {table}")
        result["published_words"] = scalar(con, "SELECT COUNT(*) FROM library_words WHERE reviewed=1")
        if result["schema"] >= "011_content_import_pipeline.sql":
            result["batches"] = [dict(row) for row in con.execute(
                "SELECT source_key,status,processed,accepted,rejected FROM content_import_batches ORDER BY id")]
        if result["schema"] >= "013_content_question_payload.sql":
            result["drafts"] = [dict(row) for row in con.execute(
                "SELECT question_type,cefr_level,COUNT(*) count FROM question_bank_drafts GROUP BY question_type,cefr_level ORDER BY question_type,cefr_level")]
            result["enrichment"] = [dict(row) for row in con.execute(
                "SELECT field_name,COUNT(*) count,COUNT(DISTINCT word_id) words FROM word_enrichment_values GROUP BY field_name ORDER BY field_name")]
            result["enriched_words"] = scalar(con, "SELECT COUNT(DISTINCT word_id) FROM word_enrichment_values")
            result["review_eligible"] = scalar(con, "SELECT COUNT(*) FROM question_bank_drafts WHERE review_status='pending' AND answer_key_json NOT IN ('','[]','{}','null') AND explanation_vi<>''")
            result["human_reviewed"] = scalar(con, "SELECT COUNT(*) FROM question_bank_drafts WHERE review_status='human_reviewed'")
            result["published_drafts"] = scalar(con, "SELECT COUNT(*) FROM question_bank_drafts WHERE published=1")
        return result
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(args.database)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
