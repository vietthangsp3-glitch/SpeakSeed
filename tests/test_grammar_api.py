import json
import sqlite3

from fastapi.testclient import TestClient

import app as application
from tools.build_grammar import import_curriculum


def setup_client(tmp_path, monkeypatch):
    database = tmp_path / "grammar-api.db"
    import_curriculum(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    return TestClient(application.app), database


def register(client, email="lan@example.com"):
    response = client.post("/api/register", json={"name": "Lan", "email": email, "password": "correct-horse"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_curriculum_and_lesson_do_not_leak_answers(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    curriculum = client.get("/api/grammar/curriculum?level=A0")
    assert curriculum.status_code == 200
    data = curriculum.json()
    assert data["totals"] == {"units": 4, "lessons": 20, "exercises": 200}
    lesson_id = data["units"][0]["lessons"][0]["id"]
    lesson = client.get(f"/api/grammar/lessons/{lesson_id}").json()
    assert len(lesson["examples"]) == 2 and len(lesson["exercises"]) == 10
    assert {item["kind"] for item in lesson["exercises"]} == {
        "multiple_choice", "fill_blank", "sentence_ordering", "error_correction", "vi_to_en"
    }
    assert all("answers" not in item and "answers_json" not in item for item in lesson["exercises"])
    assert all(isinstance(item["vocabulary"], list) for item in lesson["exercises"])


def test_grammar_attempts_and_progress_are_account_scoped(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    con = sqlite3.connect(database)
    exercise_id, answers = con.execute("SELECT id,answers_json FROM grammar_exercises ORDER BY id LIMIT 1").fetchone()
    answer = json.loads(answers)[0]
    result = client.post("/api/grammar/check", headers=headers, json={"exercise_id": exercise_id, "answer": answer})
    assert result.status_code == 200 and result.json()["correct"] is True
    assert result.json()["lesson_progress"]["correct"] == 1
    progress = client.get("/api/grammar/progress", headers=headers).json()
    assert progress["summary"]["attempted_exercises"] == 1
    assert client.get("/api/grammar/progress").status_code == 401
    other = register(client, "minh@example.com")
    assert client.get("/api/grammar/progress", headers=other).json()["summary"]["attempted_exercises"] == 0


def test_unit_test_contains_ten_questions(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    data = client.get("/api/grammar/units/1/test").json()
    assert len(data["exercises"]) == 10
    assert all(item["is_unit_test"] == 1 for item in data["exercises"])


def test_grading_accepts_contractions_and_explicit_cloze_alternatives(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    con = sqlite3.connect(database)
    translation_id = con.execute(
        "SELECT id FROM grammar_exercises WHERE kind='vi_to_en' AND answers_json LIKE '%I am Lan.%'"
    ).fetchone()[0]
    result = client.post(
        "/api/grammar/check", headers=headers,
        json={"exercise_id": translation_id, "answer": "I'm Lan."},
    )
    assert result.status_code == 200 and result.json()["correct"] is True

    exercise_id, answers_json = con.execute(
        "SELECT id,answers_json FROM grammar_exercises "
        "WHERE kind='fill_blank' AND json_array_length(answers_json)>1 ORDER BY id LIMIT 1"
    ).fetchone()
    alternative = json.loads(answers_json)[1]
    result = client.post(
        "/api/grammar/check", headers=headers,
        json={"exercise_id": exercise_id, "answer": alternative},
    )
    assert result.status_code == 200 and result.json()["correct"] is True
    assert client.post(
        "/api/grammar/check", json={"exercise_id": exercise_id, "answer": alternative}
    ).status_code == 401


def test_unit_is_completed_after_eight_correct_test_answers(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    con = sqlite3.connect(database)
    rows = con.execute(
        "SELECT id,answers_json FROM grammar_exercises "
        "WHERE unit_id=1 AND is_unit_test=1 ORDER BY sequence LIMIT 8"
    ).fetchall()
    for exercise_id, answers_json in rows:
        response = client.post(
            "/api/grammar/check", headers=headers,
            json={"exercise_id": exercise_id, "answer": json.loads(answers_json)[0]},
        )
        assert response.status_code == 200
    assert response.json()["unit_test_progress"] == {
        "attempted": 8, "correct": 8, "total": 10, "completed": True,
    }
    progress = client.get("/api/grammar/progress", headers=headers).json()
    assert progress["summary"]["completed_units"] == 1
