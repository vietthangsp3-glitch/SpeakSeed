import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import app as application
from tools.build_grammar import import_curriculum


def setup_database(tmp_path, monkeypatch):
    database = tmp_path / "concurrency.db"
    import_curriculum(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    return database


def test_login_duplicate_registration_and_logout(tmp_path, monkeypatch):
    setup_database(tmp_path, monkeypatch)
    client = TestClient(application.app)
    credentials = {"name": "Lan", "email": "lan@example.com", "password": "correct-horse"}
    registered = client.post("/api/register", json=credentials)
    assert registered.status_code == 200
    assert client.post("/api/register", json=credentials).status_code == 409
    assert client.post(
        "/api/login", json={"email": credentials["email"], "password": "wrong-password"}
    ).status_code == 401
    logged_in = client.post(
        "/api/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    assert logged_in.status_code == 200
    headers = {"Authorization": "Bearer " + logged_in.json()["token"]}
    assert client.post("/api/logout", headers=headers).status_code == 200
    assert client.get("/api/grammar/progress", headers=headers).status_code == 401


def test_multiple_users_can_write_progress_concurrently(tmp_path, monkeypatch):
    database = setup_database(tmp_path, monkeypatch)
    client = TestClient(application.app)
    user_count = 6
    tokens = []
    for index in range(user_count):
        response = client.post(
            "/api/register",
            json={"name": f"User {index}", "email": f"user{index}@example.com", "password": "correct-horse"},
        )
        assert response.status_code == 200
        tokens.append(response.json()["token"])
    con = sqlite3.connect(database)
    questions = [
        (row[0], json.loads(row[1])[0])
        for row in con.execute(
            "SELECT id,answers_json FROM grammar_exercises ORDER BY id LIMIT 10"
        ).fetchall()
    ]
    con.close()

    def submit_user(token):
        local_client = TestClient(application.app)
        headers = {"Authorization": "Bearer " + token}
        return [
            local_client.post(
                "/api/grammar/check", headers=headers,
                json={"exercise_id": exercise_id, "answer": answer},
            ).status_code
            for exercise_id, answer in questions
        ]

    with ThreadPoolExecutor(max_workers=user_count) as pool:
        statuses = list(pool.map(submit_user, tokens))
    assert all(status == 200 for group in statuses for status in group)

    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM grammar_attempts").fetchone()[0] == user_count * 10
    per_user = con.execute(
        "SELECT user_id,COUNT(*) FROM grammar_attempts GROUP BY user_id"
    ).fetchall()
    assert len(per_user) == user_count and all(count == 10 for _, count in per_user)
