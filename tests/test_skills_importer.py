import sqlite3
import json

import app as application
from tools.build_skills import import_skills


def test_four_skills_import_is_complete_and_idempotent(tmp_path):
    database = tmp_path / "skills.db"
    first = import_skills(database, application.ROOT / "migrations")
    second = import_skills(database, application.ROOT / "migrations")
    assert first["lessons"] == second["lessons"] == 60
    assert first["objective_questions"] == second["objective_questions"] == 90
    assert first["by_skill"] == {"listening": 15, "reading": 15, "speaking": 15, "writing": 15}
    assert first["by_level"] == {"A0": 12, "A1": 12, "A2": 12, "B1": 12, "B2": 12}
    assert first["question_kinds"] == {
        "multiple_choice": 15, "fill_blank": 15, "dictation": 15, "reading_comprehension": 45,
    }
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM skill_lessons").fetchone()[0] == 60
    assert con.execute("SELECT COUNT(*) FROM skill_questions").fetchone()[0] == 90
    assert con.execute("SELECT COUNT(*) FROM skill_lessons WHERE review_status='human_reviewed'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM skill_lessons WHERE review_status='automated_checked'").fetchone()[0] == 60
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    for options_json, answers_json in con.execute(
        "SELECT options_json,answers_json FROM skill_questions WHERE json_array_length(options_json)>0"
    ):
        options = json.loads(options_json);answers = json.loads(answers_json)
        normal = lambda value: " ".join(__import__("re").findall(r"[a-z0-9]+", value.casefold()))
        assert any(normal(answer) == normal(option) for answer in answers for option in options)


def test_listening_transcripts_fit_on_demand_tts_and_have_three_question_types(tmp_path):
    database = tmp_path / "listening.db"
    import_skills(database, application.ROOT / "migrations")
    con = sqlite3.connect(database)
    assert con.execute(
        "SELECT COUNT(*) FROM skill_lessons WHERE skill='listening' AND length(transcript_en) BETWEEN 1 AND 500"
    ).fetchone()[0] == 15
    rows = con.execute("""SELECT l.id,COUNT(q.id),COUNT(DISTINCT q.kind)
        FROM skill_lessons l JOIN skill_questions q ON q.lesson_id=l.id
        WHERE l.skill='listening' GROUP BY l.id""").fetchall()
    assert len(rows) == 15
    assert all(question_count == kind_count == 3 for _, question_count, kind_count in rows)
