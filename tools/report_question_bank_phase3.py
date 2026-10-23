"""Read-only evidence report for the Phase-3 staging question bank."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def report(database: Path) -> dict:
    con = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        by_type_level = [dict(row) for row in con.execute(
            """SELECT question_type,skill,cefr_level,COUNT(*) count FROM question_bank_drafts
               GROUP BY question_type,skill,cefr_level ORDER BY question_type,skill,cefr_level""")]
        issues = Counter()
        for row in con.execute("SELECT issues_json FROM question_qa_results"):
            issues.update(item["code"] for item in json.loads(row[0]))
        return {
            "schema": con.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()[0],
            "integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": len(con.execute("PRAGMA foreign_key_check").fetchall()),
            "tables": con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0],
            "published_words": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
            "grammar_lessons": con.execute("SELECT COUNT(*) FROM grammar_lessons WHERE published=1").fetchone()[0],
            "grammar_exercises": con.execute("SELECT COUNT(*) FROM grammar_exercises WHERE published=1").fetchone()[0],
            "questions": con.execute("SELECT COUNT(*) FROM question_bank_drafts").fetchone()[0],
            "by_type_level": by_type_level,
            "qa": [dict(row) for row in con.execute("SELECT overall_status,COUNT(*) count FROM question_qa_results GROUP BY overall_status")],
            "issues": dict(sorted(issues.items())),
            "with_vietnamese_explanation": con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE trim(explanation_vi)<>''").fetchone()[0],
            "draft_explanations": con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE explanation_vi LIKE '[Bản nháp%'").fetchone()[0],
            "human_reviewed": con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE review_status='human_reviewed'").fetchone()[0],
            "rejected": con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE review_status='rejected'").fetchone()[0],
            "published": con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE published=1").fetchone()[0],
            "review_ready": con.execute("""SELECT COUNT(*) FROM question_bank_drafts d JOIN question_qa_results q ON q.question_id=d.id
                WHERE d.review_status='pending' AND q.overall_status IN ('pass','warn') AND trim(d.explanation_vi)<>''""").fetchone()[0],
            "attempts": con.execute("SELECT COUNT(*) FROM question_bank_attempts").fetchone()[0],
        }
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("database", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); data = report(args.database)
    if args.output: args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=True, indent=2))


if __name__ == "__main__": main()
