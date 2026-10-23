import sqlite3

import pytest
from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations
from tools.vocabulary_topics import propose, publish, review


ROOT = application.ROOT


def setup_database(tmp_path, monkeypatch):
    database = tmp_path / "topics.db"
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database)
    con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,
        license,reviewed,normalized_word,example_vi,quality_score,updated_at)
        VALUES('apple','quả táo','/apple/','I eat an apple.','Food','🍎','A1','noun','test','apple',
        'test',1,'apple','Tôi ăn một quả táo.',100,'now')""")
    con.commit(); con.close()
    monkeypatch.setattr(application, "DB", database)
    return database, TestClient(application.app)


def register(client, email):
    response = client.post("/api/register", json={"name":"QA","email":email,"password":"correct-horse"})
    assert response.status_code == 200
    return {"Authorization":"Bearer " + response.json()["token"]}, response.json()["user"]["id"]


def test_one_word_can_have_multiple_topics_without_duplicate_progress(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    for topic in ("food-drinks", "daily-life"):
        propose(database, 1, topic, "", "reviewer-research", "The reviewed sense fits this topic", 90)
        review(database, 1, topic, "", "Human Reviewer", "approve", "Checked the word sense")
        publish(database, 1, topic, "", True)
    headers, _ = register(client, "topics@example.com")
    words = client.get("/api/words").json()
    assert set(words[0]["topic_slugs"]) == {"food-drinks", "daily-life"}
    assert client.post("/api/progress", headers=headers, json={"word_id":1,"correct":True}).status_code == 200
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM progress WHERE word_id=1").fetchone()[0] == 1


def test_pending_topic_mapping_is_not_visible_and_direct_publish_is_blocked(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    propose(database, 1, "food-drinks", "", "automated-rule", "Candidate only", 70)
    con = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="Human review or immutable automated evidence"):
        con.execute("UPDATE vocabulary_topic_words SET published=1 WHERE word_id=1")
    con.close()
    words = client.get("/api/words").json()
    assert words[0]["topic_slugs"] == []
    catalog = client.get("/api/vocabulary/topics").json()
    food = next(topic for topic in catalog["topics"] if topic["slug"] == "food-drinks")
    assert food["published_words"] == 0 and catalog["unclassified_words"] == 1


def test_topic_progress_is_authenticated_and_account_scoped(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    propose(database, 1, "food-drinks", "", "reviewer-research", "Checked sense", 95)
    review(database, 1, "food-drinks", "", "Human Reviewer", "approve", "Checked")
    publish(database, 1, "food-drinks", "", True)
    first, _ = register(client, "first-topic@example.com")
    second, _ = register(client, "second-topic@example.com")
    assert client.get("/api/vocabulary/topic-progress").status_code == 401
    client.post("/api/progress", headers=first, json={"word_id":1,"correct":True})
    first_food = next(x for x in client.get("/api/vocabulary/topic-progress", headers=first).json() if x["slug"] == "food-drinks")
    second_food = next(x for x in client.get("/api/vocabulary/topic-progress", headers=second).json() if x["slug"] == "food-drinks")
    assert first_food["started"] == 1 and second_food["started"] == 0


def test_topic_review_audit_is_immutable(tmp_path, monkeypatch):
    database, _ = setup_database(tmp_path, monkeypatch)
    propose(database, 1, "food-drinks", "", "research", "Checked source", 90)
    review(database, 1, "food-drinks", "", "Human Reviewer", "approve", "Checked")
    con = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        con.execute("UPDATE vocabulary_topic_reviews SET reason='changed'")
    con.close()


def test_postgres_topic_migration_is_native_sql():
    sql = (ROOT / "deploy" / "postgres" / "017_vocabulary_topics.sql").read_text(encoding="utf-8")
    assert "LANGUAGE plpgsql" in sql
    assert "ON CONFLICT" in sql
    assert "RAISE(ABORT" not in sql and "INSERT OR IGNORE" not in sql
