import json
import sqlite3
from collections import Counter

from fastapi.testclient import TestClient

import app as application
from personalization import normalize
from tools.build_grammar import import_curriculum
from tools.build_skills import import_skills


def setup_client(tmp_path, monkeypatch):
    database = tmp_path / "placement-v2.db"
    import_curriculum(database, application.ROOT / "migrations")
    con = sqlite3.connect(database)
    con.execute("ATTACH DATABASE ? AS bundled", (str(application.ROOT / "speakseed.db"),))
    columns = "word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at"
    con.execute(f"INSERT INTO library_words({columns}) SELECT {columns} FROM bundled.library_words WHERE reviewed=1")
    con.commit(); con.execute("DETACH DATABASE bundled"); con.close()
    import_skills(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    return TestClient(application.app), database


def register(client, email):
    response = client.post("/api/register", json={"name": "Placement QA", "email": email, "password": "correct-horse"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def internal_questions(database, attempt_id):
    con = sqlite3.connect(database)
    row = con.execute("SELECT questions_json FROM placement_attempts WHERE id=?", (attempt_id,)).fetchone()
    con.close()
    return json.loads(row[0])


def test_distribution_and_each_question_has_auditable_metadata(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client, "placement-distribution@example.com")
    started = client.post("/api/placement/start", headers=headers).json()
    questions = internal_questions(database, started["attempt_id"])
    assert Counter(item["level"] for item in questions) == {level: 8 for level in ("A0", "A1", "A2", "B1", "B2")}
    assert Counter(item["section"] for item in questions) == {
        "grammar": 7, "vocabulary": 5, "listening": 8,
        "fill_blank": 8, "sentence_ordering": 6, "reading": 6,
    }
    assert Counter(item["kind"] for item in questions)["listening_fill_blank"] == 4
    assert all(item["answers"] and item["level"] and item["topic"] and
               item["explanation_vi"] and item["source"] for item in questions)
    assert len({item["key"] for item in questions}) == len({(item["section"], item["prompt"]) for item in questions}) == 40
    for item in questions:
        assert len(item["options"]) == len(set(item["options"]))
        if item["options"]:
            assert any(normalize(answer) == normalize(option)
                       for answer in item["answers"] for option in item["options"])
        if item["kind"] == "sentence_ordering":
            assert Counter(word for token in item["tokens"] for word in normalize(token).split()) == \
                   Counter(normalize(item["answers"][0]).split())


def test_answers_resume_after_reload_and_are_account_scoped(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    owner = register(client, "placement-owner@example.com")
    other = register(client, "placement-other@example.com")
    started = client.post("/api/placement/start", headers=owner).json()
    first = started["questions"][0]
    saved = client.post("/api/placement/answer", headers=owner, json={
        "attempt_id": started["attempt_id"], "question_key": first["key"], "answer": "saved answer"
    })
    assert saved.status_code == 200
    assert client.post("/api/placement/answer", headers=other, json={
        "attempt_id": started["attempt_id"], "question_key": first["key"], "answer": "tamper"
    }).status_code == 404
    resumed = client.post("/api/placement/start", headers=owner).json()
    assert resumed["resumed"] is True
    assert resumed["attempt_id"] == started["attempt_id"]
    assert resumed["responses"][first["key"]] == {"answer": "saved answer", "state": "answered"}
    assert client.get(f"/api/placement/audio/{started['attempt_id']}/{first['key']}", headers=owner).status_code == 404
    assert client.post("/api/placement/submit", headers=owner, json={"attempt_id": started["attempt_id"]}).status_code == 400


def test_listening_audio_is_on_demand_private_and_audio_failure_is_fair(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    owner = register(client, "placement-audio@example.com")
    other = register(client, "placement-audio-other@example.com")
    started = client.post("/api/placement/start", headers=owner).json()
    internal = internal_questions(database, started["attempt_id"])
    listening = next(item for item in internal if item["section"] == "listening")
    assert "audio_text" not in next(item for item in started["questions"] if item["key"] == listening["key"])
    audio = client.get(f"/api/placement/audio/{started['attempt_id']}/{listening['key']}", headers=owner)
    assert audio.status_code == 200 and audio.json()["text"] == listening["transcript_en"]
    assert audio.headers["cache-control"] == "private, no-store"
    assert client.get(f"/api/placement/audio/{started['attempt_id']}/{listening['key']}", headers=other).status_code == 404

    for item in internal:
        state = "audio_unavailable" if item["key"] == listening["key"] else "answered"
        answer = "" if state == "audio_unavailable" else item["answers"][0]
        response = client.post("/api/placement/answer", headers=owner, json={
            "attempt_id": started["attempt_id"], "question_key": item["key"],
            "answer": answer, "state": state,
        })
        assert response.status_code == 200
    result = client.post("/api/placement/submit", headers=owner,
                         json={"attempt_id": started["attempt_id"]})
    assert result.status_code == 200
    data = result.json()
    assert data["total_correct"] == data["total"] == 39
    assert data["question_count"] == 40 and data["audio_unavailable"] == 1
    assert data["confidence"] == "reduced"
    assert len(data["details"]) == 40


def test_equivalent_fill_and_ordering_answers_history_and_no_vocab_mastery(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = register(client, "placement-scoring@example.com")
    started = client.post("/api/placement/start", headers=headers).json()
    questions = internal_questions(database, started["attempt_id"])
    payload = []
    for item in questions:
        answer = item["answers"][0]
        if item["kind"] == "fill_blank": answer = "  " + answer.swapcase() + "  "
        if item["kind"] == "sentence_ordering": answer = " / ".join(item["answers"][0].rstrip(".").split())
        payload.append({"question_key": item["key"], "answer": answer})
    result = client.post("/api/placement/submit", headers=headers,
                         json={"attempt_id": started["attempt_id"], "answers": payload})
    assert result.status_code == 200 and result.json()["total_correct"] == 40
    history = client.get("/api/placement/history", headers=headers).json()["attempts"]
    assert history[0]["attempt_id"] == started["attempt_id"]
    review = client.get(f"/api/placement/review/{started['attempt_id']}", headers=headers)
    assert review.status_code == 200 and len(review.json()["details"]) == 40
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM progress").fetchone()[0] == 0
    con.close()
