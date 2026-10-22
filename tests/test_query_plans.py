import sqlite3
from pathlib import Path

from migrations import run_migrations


ROOT = Path(__file__).resolve().parents[1]


def details(con, sql, params):
    return " ".join(row[3] for row in con.execute("EXPLAIN QUERY PLAN " + sql, params))


def test_hot_queries_use_beta_indexes(tmp_path):
    database = tmp_path / "plans.db"; run_migrations(database, ROOT / "migrations")
    with sqlite3.connect(database) as con:
        assert "INDEX" in details(con, "SELECT id FROM library_words WHERE stage=? AND reviewed=1 ORDER BY id", ("B1",))
        assert "idx_grammar_lessons_level_published" in details(con, "SELECT id FROM grammar_lessons WHERE level=? AND published=1 ORDER BY unit_id,sequence", ("B1",))
        assert "idx_skill_lessons_path" in details(con, "SELECT id FROM skill_lessons WHERE skill=? AND level=? AND published=1 ORDER BY sequence", ("reading", "B1"))
        assert "idx_learning_events_type_time" in details(con, "SELECT id FROM learning_events WHERE user_id=? AND event_type=? AND occurred_at>=?", (1, "grammar_answer", "2026"))
