import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import app as application
from tools.build_grammar import import_curriculum
from tools.build_skills import import_skills


def setup_client(tmp_path, monkeypatch):
    database = tmp_path / "personalization.db"
    import_curriculum(database, application.ROOT / "migrations")
    con = sqlite3.connect(database)
    con.execute("ATTACH DATABASE ? AS bundled", (str(application.ROOT / "speakseed.db"),))
    columns = "word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at"
    con.execute(f"INSERT INTO library_words({columns}) SELECT {columns} FROM bundled.library_words WHERE reviewed=1")
    con.commit()
    con.execute("DETACH DATABASE bundled")
    con.close()
    import_skills(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    return TestClient(application.app), database


def register(client, email="lan@example.com"):
    response = client.post(
        "/api/register",
        json={"name": "Lan", "email": email, "password": "correct-horse"},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def answers_for_attempt(database, attempt_id, wrong=False):
    con = sqlite3.connect(database)
    questions = json.loads(con.execute(
        "SELECT questions_json FROM placement_attempts WHERE id=?", (attempt_id,)
    ).fetchone()[0])
    return [
        {"question_key": item["key"], "answer": "__definitely_wrong__" if wrong else item["answers"][0]}
        for item in questions
    ]


def test_placement_uses_40_balanced_real_questions_and_does_not_leak_answers(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    started = client.post("/api/placement/start", headers=headers)
    assert started.status_code == 200
    data = started.json()
    assert data["question_count"] == len(data["questions"]) == 40
    assert {item["domain"] for item in data["questions"]} == {"grammar", "vocabulary", "listening", "reading"}
    assert {item["section"] for item in data["questions"]} == {
        "grammar", "vocabulary", "listening", "fill_blank", "sentence_ordering", "reading"
    }
    assert {item["level"] for item in data["questions"]} == {"A0", "A1", "A2", "B1", "B2"}
    assert all("answers" not in item and "explanation_vi" not in item and "transcript_en" not in item
               and "audio_text" not in item for item in data["questions"])
    assert "không phải chứng chỉ CEFR" in data["limitation"]

    result = client.post(
        "/api/placement/submit", headers=headers,
        json={"attempt_id": data["attempt_id"], "answers": answers_for_attempt(database, data["attempt_id"])},
    )
    assert result.status_code == 200
    assert result.json()["total_correct"] == 40
    assert result.json()["recommended_level"] == "B2"
    assert result.json()["current_level"] == "B2"
    assert client.post(
        "/api/placement/submit", headers=headers,
        json={"attempt_id": data["attempt_id"], "answers": answers_for_attempt(database, data["attempt_id"])},
    ).status_code == 409


def test_placement_attempts_are_account_scoped_and_low_score_recommends_a0(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    first = register(client)
    second = register(client, "minh@example.com")
    started = client.post("/api/placement/start", headers=first).json()
    payload = {"attempt_id": started["attempt_id"], "answers": answers_for_attempt(database, started["attempt_id"], True)}
    assert client.post("/api/placement/submit", headers=second, json=payload).status_code == 404
    result = client.post("/api/placement/submit", headers=first, json=payload)
    assert result.status_code == 200 and result.json()["recommended_level"] == "A0"
    assert client.get("/api/placement/latest", headers=second).json()["attempt"] is None


def test_learning_path_unlocks_only_from_backend_grammar_evidence(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    path = client.get("/api/learning-path", headers=headers).json()
    assert path["level"] == "A0"
    assert path["lessons"][0]["unlocked"] is True
    assert all(item["unlocked"] is False for item in path["lessons"][1:])
    con = sqlite3.connect(database)
    rows = con.execute(
        "SELECT id,answers_json FROM grammar_exercises WHERE lesson_id=1 ORDER BY sequence LIMIT 8"
    ).fetchall()
    for exercise_id, answers_json in rows:
        result = client.post(
            "/api/grammar/check", headers=headers,
            json={"exercise_id": exercise_id, "answer": json.loads(answers_json)[0]},
        )
        assert result.status_code == 200
    path = client.get("/api/learning-path", headers=headers).json()
    assert path["lessons"][0]["completed"] is True
    assert path["lessons"][1]["unlocked"] is True
    assert path["next_lesson"]["id"] == 2


def test_daily_plan_and_dashboard_require_recorded_activity(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    first = register(client)
    second = register(client, "minh@example.com")
    initial = client.get("/api/dashboard", headers=first).json()
    assert initial["metrics"]["learned_words"] == 0
    assert initial["metrics"]["accuracy"] is None
    assert initial["metrics"]["streak_days"] == 0
    assert initial["daily_plan"]["completed"] is False
    assert all(item["completed_count"] == 0 for item in initial["daily_plan"]["items"])
    assert all(not item["completed"] for item in initial["daily_plan"]["items"])

    con = sqlite3.connect(database)
    word_id = con.execute("SELECT id FROM library_words WHERE reviewed=1 AND stage='A1' LIMIT 1").fetchone()[0]
    assert client.post("/api/progress", headers=first, json={"word_id": word_id, "correct": True}).status_code == 200
    updated = client.get("/api/dashboard", headers=first).json()
    assert updated["metrics"]["learned_words"] == 1
    assert updated["metrics"]["accuracy"] == 1.0
    assert updated["metrics"]["streak_days"] == 1
    vocabulary_item = next(item for item in updated["daily_plan"]["items"] if item["key"] == "vocabulary")
    assert vocabulary_item["completed_count"] == 1 and vocabulary_item["completed"] is False
    other = client.get("/api/dashboard", headers=second).json()
    assert other["metrics"]["learned_words"] == 0 and other["metrics"]["streak_days"] == 0


def test_profile_validation_and_concurrent_dashboard_snapshots(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    tokens = []
    for index in range(5):
        headers = register(client, f"user{index}@example.com")
        tokens.append(headers["Authorization"].removeprefix("Bearer "))
    assert client.post("/api/profile", headers={"Authorization": "Bearer " + tokens[0]}, json={"current_level": "C1"}).status_code == 400
    changed = client.post(
        "/api/profile", headers={"Authorization": "Bearer " + tokens[0]},
        json={"current_level": "B1", "daily_goal_minutes": 25},
    )
    assert changed.status_code == 200 and changed.json()["current_level"] == "B1"

    def load_dashboard(token):
        local = TestClient(application.app)
        return local.get("/api/dashboard", headers={"Authorization": "Bearer " + token})

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(load_dashboard, tokens))
    assert all(response.status_code == 200 for response in responses)
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM daily_plans").fetchone()[0] == 5


def test_beginner_plan_prioritizes_non_ai_skills_but_path_keeps_four_skills(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    path = client.get("/api/learning-path", headers=headers).json()
    assert set(path["skill_paths"]) == {"listening", "reading", "speaking", "writing"}
    assert all(len(path["skill_paths"][skill]["lessons"]) == 3 for skill in path["skill_paths"])
    assert all(path["skill_paths"][skill]["lessons"][0]["unlocked"] for skill in path["skill_paths"])
    plan = client.get("/api/daily-plan", headers=headers).json()
    items = {item["key"]: item for item in plan["items"]}
    assert {"vocabulary", "review", "grammar", "listening", "reading"} == set(items)
    assert "speaking" not in items and "writing" not in items
    assert all(items[skill]["completed"] is False for skill in ("listening", "reading"))
    assert "tùy chọn" in plan["evidence_note"]
    dashboard = client.get("/api/dashboard", headers=headers).json()
    assert dashboard["metrics"]["skills"] == {
        skill: {"completed_lessons": 0, "total_lessons": 15}
        for skill in ("listening", "reading", "speaking", "writing")
    }


def test_existing_beginner_daily_plan_is_normalized_without_deleting_events(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client)
    original = client.get("/api/daily-plan", headers=headers).json()
    con = sqlite3.connect(database)
    user_id = con.execute("SELECT id FROM users WHERE email='lan@example.com'").fetchone()[0]
    items = original["items"] + [
        {"key": "speaking", "label": "AI Speaking", "target": 1, "view": "skills", "lesson_id": 3001},
        {"key": "writing", "label": "Luyện viết", "target": 1, "view": "skills", "lesson_id": 4001},
    ]
    con.execute("UPDATE daily_plans SET items_json=? WHERE user_id=?", (json.dumps(items), user_id))
    con.execute("""INSERT INTO learning_events(user_id,event_type,skill,occurred_at)
        VALUES(?,'speaking_turn','speaking',datetime('now'))""", (user_id,))
    con.commit(); con.close()
    normalized = client.get("/api/daily-plan", headers=headers).json()
    assert "speaking" not in {item["key"] for item in normalized["items"]}
    assert "writing" not in {item["key"] for item in normalized["items"]}
    with sqlite3.connect(database) as check:
        assert check.execute("SELECT COUNT(*) FROM learning_events WHERE user_id=?", (user_id,)).fetchone()[0] == 1
