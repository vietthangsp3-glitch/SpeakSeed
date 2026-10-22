import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import app as application
from tools.build_grammar import import_curriculum
from tools.build_skills import import_skills


def setup_client(tmp_path, monkeypatch):
    database = tmp_path / "four-skills.db"
    import_curriculum(database, application.ROOT / "migrations")
    con = sqlite3.connect(database)
    con.execute("ATTACH DATABASE ? AS bundled", (str(application.ROOT / "speakseed.db"),))
    columns = "word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at"
    con.execute(f"INSERT INTO library_words({columns}) SELECT {columns} FROM bundled.library_words WHERE reviewed=1")
    con.commit();con.execute("DETACH DATABASE bundled");con.close()
    import_skills(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    application._rate.clear()
    return TestClient(application.app), database


def register(client, email="lan-skills@example.com"):
    response = client.post("/api/register", json={"name":"Lan","email":email,"password":"correct-horse"})
    assert response.status_code == 200
    return {"Authorization":"Bearer " + response.json()["token"]}


def test_listening_catalog_checking_and_account_isolation(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    first = register(client);second = register(client, "minh-skills@example.com")
    catalog = client.get("/api/skills/catalog", params={"skill":"listening"})
    assert catalog.status_code == 200 and catalog.json()["counts"]["listening"] == 15
    assert {x["level"] for x in catalog.json()["lessons"]} == {"A0","A1","A2","B1","B2"}
    lesson_id = catalog.json()["lessons"][0]["id"]
    assert client.get(f"/api/skills/lessons/{lesson_id}").status_code == 401
    detail = client.get(f"/api/skills/lessons/{lesson_id}", headers=first).json()
    assert len(detail["questions"]) == 3 and all("answers" not in x for x in detail["questions"])
    con = sqlite3.connect(database)
    qid, answers = con.execute("SELECT id,answers_json FROM skill_questions WHERE lesson_id=? ORDER BY sequence LIMIT 1", (lesson_id,)).fetchone()
    result = client.post("/api/skills/check", headers=first, json={"question_id":qid,"answer":json.loads(answers)[0]})
    assert result.status_code == 200 and result.json()["correct"] is True
    assert client.get(f"/api/skills/lessons/{lesson_id}", headers=second).json()["progress"]["attempted"] == 0
    events = con.execute("SELECT COUNT(*) FROM learning_events WHERE event_type='skill_listening_answer'").fetchone()[0]
    con.close();assert events == 1


def test_reading_answers_and_saves_only_linked_word_to_review(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch);headers = register(client)
    lesson = client.get("/api/skills/catalog", params={"skill":"reading","level":"A0"}).json()["lessons"][0]
    detail = client.get(f"/api/skills/lessons/{lesson['id']}", headers=headers).json()
    assert detail["content_en"] and len(detail["questions"]) == 3
    assert detail["vocabulary"]
    word_id = detail["vocabulary"][0]["id"]
    saved = client.post("/api/reading/save-word", headers=headers, json={"lesson_id":lesson["id"],"word_id":word_id})
    assert saved.status_code == 200 and saved.json()["added"] is True
    duplicate = client.post("/api/reading/save-word", headers=headers, json={"lesson_id":lesson["id"],"word_id":word_id})
    assert duplicate.json()["added"] is False
    progress = client.get("/api/progress", headers=headers).json()
    stored = next(x for x in progress if x["word_id"] == word_id)
    assert stored["correct"] == stored["wrong"] == stored["repetitions"] == 0
    assert client.post("/api/reading/save-word", headers=headers, json={"lesson_id":lesson["id"],"word_id":999999}).status_code == 404


def test_speaking_session_records_real_turns_and_evaluates_without_pronunciation(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch);headers = register(client)
    other = register(client, "other-speaker@example.com")
    monkeypatch.setattr(application, "gemini_key", lambda: "server-only-test-key")
    def fake_gemini(system, contents, key):
        if "giám khảo" in system:
            return json.dumps({"scores":{"grammar":76,"vocabulary":72,"naturalness":70,"task_completion":82},
                               "feedback_vi":"Bạn đã hoàn thành nhiệm vụ.","suggestions":["Dùng thì hiện tại nhất quán."]})
        return "Nice to meet you. Where do you live?"
    monkeypatch.setattr(application, "await_gemini_sync", fake_gemini)
    lesson_id = client.get("/api/skills/catalog", params={"skill":"speaking","level":"A0"}).json()["lessons"][0]["id"]
    started = client.post("/api/skills/speaking/start", headers=headers, json={"lesson_id":lesson_id,"mode":"turn"}).json()
    session_id = started["session_id"]
    assert client.post("/api/skills/speaking/evaluate", headers=other, json={"session_id":session_id}).status_code == 404
    for message in ("Hello, my name is Lan.", "I live in Hanoi and I like music."):
        response = client.post("/api/speaking/turn", headers=headers, json={"message":message,"session_id":session_id})
        assert response.status_code == 200 and response.json()["session_id"] == session_id
    evaluated = client.post("/api/skills/speaking/evaluate", headers=headers, json={"session_id":session_id})
    assert evaluated.status_code == 200
    assert set(evaluated.json()["scores"]) == {"grammar","vocabulary","naturalness","task_completion"}
    assert evaluated.json()["feedback"]["pronunciation"] is None
    assert "không tương đương chứng chỉ CEFR" in evaluated.json()["disclaimer"]
    con = sqlite3.connect(database)
    row = con.execute("SELECT turns,status,audio_evidence FROM speaking_sessions WHERE id=?", (session_id,)).fetchone()
    assert row == (2,"evaluated",0)


def test_writing_draft_limits_feedback_and_account_scope(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch);first = register(client);second = register(client,"other-writer@example.com")
    monkeypatch.setattr(application, "gemini_key", lambda: "server-only-test-key")
    monkeypatch.setattr(application, "await_gemini_sync", lambda system, contents, key: json.dumps({
        "dimensions":{name:{"score":80,"comment_vi":"Rõ ràng."} for name in ("grammar","vocabulary","coherence","naturalness")},
        "errors":[],"summary_vi":"Bài đáp ứng yêu cầu luyện tập."}))
    lesson_id = client.get("/api/skills/catalog", params={"skill":"writing","level":"A0"}).json()["lessons"][0]["id"]
    short = client.post("/api/skills/writing/drafts", headers=first, json={"lesson_id":lesson_id,"content":"Too short"}).json()
    assert client.post("/api/skills/writing/submit", headers=first, json={"draft_id":short["draft_id"]}).status_code == 400
    assert client.post("/api/skills/writing/submit", headers=second, json={"draft_id":short["draft_id"]}).status_code == 404
    content = "My name is Lan and I live in Hanoi. I like music, books, tea, and learning English every day."
    saved = client.post("/api/skills/writing/drafts", headers=first, json={"lesson_id":lesson_id,"content":content}).json()
    submitted = client.post("/api/skills/writing/submit", headers=first, json={"draft_id":saved["draft_id"]})
    assert submitted.status_code == 200 and submitted.json()["feedback"]["word_count"] >= 15
    drafts = client.get("/api/skills/writing/drafts", headers=first).json()
    assert any(x["id"] == saved["draft_id"] and x["status"] == "submitted" for x in drafts)
    assert client.get("/api/skills/writing/drafts", headers=second).json() == []


def test_concurrent_skill_progress_writes_are_isolated_by_account(tmp_path, monkeypatch):
    client, database = setup_client(tmp_path, monkeypatch)
    headers = [register(client, f"skill-user-{index}@example.com") for index in range(8)]
    con = sqlite3.connect(database)
    question_id, answers_json = con.execute(
        "SELECT id,answers_json FROM skill_questions ORDER BY id LIMIT 1"
    ).fetchone();con.close()
    answer = json.loads(answers_json)[0]

    def submit(account_headers):
        local = TestClient(application.app)
        return local.post("/api/skills/check", headers=account_headers,
                          json={"question_id":question_id,"answer":answer})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, headers))
    assert all(response.status_code == 200 and response.json()["correct"] for response in responses)
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM skill_question_attempts WHERE question_id=?", (question_id,)).fetchone()[0] == 8
    assert con.execute("SELECT COUNT(DISTINCT user_id) FROM skill_progress").fetchone()[0] == 8
