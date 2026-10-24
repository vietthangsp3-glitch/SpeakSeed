from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations


def test_account_scoped_srs_review_flow(tmp_path, monkeypatch):
    database = tmp_path / "api.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    with application.connect() as con:
        con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at)
            VALUES('apple','quả táo','/ˈæp.əl/','I have an apple.','Food','🍎','A1','noun','test','apple','test',1,'apple','Tôi có một quả táo.',100,'now')""")
    client = TestClient(application.app)
    registered = client.post("/api/register", json={"name":"Lan","email":"lan@example.com","password":"correct-horse"})
    assert registered.status_code == 200
    headers = {"Authorization": "Bearer " + registered.json()["token"]}
    word_id = client.get("/api/words").json()[0]["id"]
    result = client.post("/api/progress", headers=headers, json={"word_id":word_id,"correct":True})
    assert result.status_code == 200
    assert result.json()["repetitions"] == 1 and result.json()["interval_days"] == 1
    saved = client.get("/api/progress", headers=headers).json()
    assert len(saved) == 1 and saved[0]["word_id"] == word_id
    assert client.get("/api/progress").status_code == 401

    second = client.post("/api/progress", headers=headers, json={"word_id":word_id,"correct":True}).json()
    assert second["repetitions"] == 2 and second["interval_days"] == 3
    third = client.post("/api/progress", headers=headers, json={"word_id":word_id,"correct":True}).json()
    assert third["repetitions"] == 3 and third["interval_days"] >= 4
    failed = client.post("/api/progress", headers=headers, json={"word_id":word_id,"correct":False}).json()
    assert failed["repetitions"] == 0 and failed["interval_days"] == 0 and failed["lapses"] == 1


def test_frontend_does_not_contain_provider_key_name():
    javascript = (application.ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=" not in javascript
    assert "localStorage.setItem('ss_token'" not in javascript
    assert "Authorization:'Bearer '+state.token" not in javascript
    assert "X-CSRF-Token" in javascript
    assert "fetch('/api/tts'" not in javascript
    assert "speechSynthesis" in javascript
    assert 'min="0.75" max="1.25"' in javascript
    assert "Gemini Live sử dụng quota API" not in javascript
    assert "Hội thoại trực tiếp hiện chưa khả dụng" in javascript
    assert "window.confirm" in javascript
    assert "pagehide" in javascript and "beforeunload" in javascript
