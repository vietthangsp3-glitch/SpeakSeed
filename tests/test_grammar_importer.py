import sqlite3
from collections import Counter

from migrations import run_migrations
from tools.build_grammar import build_rows, import_curriculum, validate
from tools.audit_grammar import audit


def test_catalog_has_balanced_meaningful_content():
    units, lessons, examples, exercises = build_rows()
    validate(units, lessons, examples, exercises)
    assert len(units) == 20
    assert Counter(row["level"] for row in lessons) == Counter({x: 20 for x in ("A0", "A1", "A2", "B1", "B2")})
    assert Counter(row["kind"] for row in exercises) == Counter({
        "multiple_choice": 200, "fill_blank": 200, "sentence_ordering": 200,
        "error_correction": 200, "vi_to_en": 200,
    })
    assert all(len(row["explanation_vi"]) >= 30 and len(row["formula"]) >= 5 for row in lessons)
    assert all(row["answers"] and row["prompt"] for row in exercises)
    for unit_id in range(1, 21):
        test_items = [row for row in exercises if row["unit_id"] == unit_id and row["is_unit_test"]]
        assert len(test_items) == 10
        assert Counter(row["kind"] for row in test_items) == Counter({kind: 2 for kind in (
            "multiple_choice", "fill_blank", "sentence_ordering", "error_correction", "vi_to_en"
        )})
        assert len({row["lesson_id"] for row in test_items}) == 5


def test_grammar_import_is_idempotent_and_preserves_users(tmp_path, monkeypatch):
    database = tmp_path / "grammar.db"
    migrations = __import__("app").ROOT / "migrations"
    run_migrations(database, migrations)
    con = sqlite3.connect(database)
    con.execute("INSERT INTO users(name,email,salt,hash,created) VALUES('Lan','lan@example.com','s','h','now')")
    con.commit()
    con.close()
    first = import_curriculum(database, migrations)
    second = import_curriculum(database, migrations)
    con = sqlite3.connect(database)
    assert first["lessons"] == second["lessons"] == 100
    assert con.execute("SELECT COUNT(*) FROM grammar_units WHERE published=1").fetchone()[0] == 20
    assert con.execute("SELECT COUNT(*) FROM grammar_lessons WHERE published=1").fetchone()[0] == 100
    assert con.execute("SELECT COUNT(*) FROM grammar_exercises WHERE published=1").fetchone()[0] == 1000
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM grammar_exercises WHERE review_status='human_reviewed'").fetchone()[0] == 0


def test_production_grammar_links_existing_vocabulary():
    import app
    con = sqlite3.connect(app.DB)
    vocab_count = con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0]
    linked = con.execute("SELECT COUNT(DISTINCT exercise_id) FROM grammar_exercise_words").fetchone()[0]
    assert vocab_count == 6280
    assert linked >= 900


def test_full_catalog_qa_audit_has_no_structural_failures():
    report = audit()
    assert report["summary"]["units_checked"] == 20
    assert report["summary"]["lessons_checked"] == 100
    assert report["summary"]["examples_checked"] == 200
    assert report["summary"]["exercises_checked"] == 1000
    assert report["summary"]["structural_failures"] == 0
    assert report["summary"]["human_reviewed"] == 0
