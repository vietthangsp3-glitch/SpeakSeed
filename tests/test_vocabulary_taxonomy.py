import sqlite3
from fastapi.testclient import TestClient
import app as application

from tools.audit_vocabulary_taxonomy import audit
from tools.classify_vocabulary_wordnet import proposed_topics


def test_wordnet_topics_require_vietnamese_sense_confirmation():
    assert proposed_topics([{"lexname": "noun.person", "gloss": "a person employed to serve"}], "Máy chủ, server.") == {}
    assert "health-body" in proposed_topics(
        [{"lexname": "noun.body", "gloss": "the organ of sight"}], "Mắt: cơ quan thị giác."
    )


def test_taxonomy_audit_covers_every_published_word():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = audit(root / "speakseed.db")
    assert result["published_words"] == 6280
    assert sum(result["levels"].values()) == 6280
    assert result["cefr_reference_matches"] == 6280
    assert result["cefr_mismatches"] == []
    assert result["cefr_unmatched"] == []
    assert len(result["topics"]) == 24
    assert result["integrity"] == "ok" and result["foreign_key_errors"] == 0


def test_topic_correction_evidence_is_immutable(tmp_path):
    from pathlib import Path
    from migrations import run_migrations
    root = Path(__file__).resolve().parents[1]
    db = tmp_path / "taxonomy.db"; run_migrations(db, root / "migrations")
    con = sqlite3.connect(db)
    # The immutability triggers exist even in a fresh database.
    names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "immutable_vocabulary_topic_correction_update" in names
    assert "immutable_vocabulary_topic_correction_delete" in names


def test_combined_level_and_topic_filter():
    client = TestClient(application.app)
    response = client.get("/api/words", params={"level": "A1", "topic": "food-drinks"})
    assert response.status_code == 200
    rows = response.json()
    assert rows and all(row["stage"] == "A1" and "food-drinks" in row["topic_slugs"] for row in rows)
    assert client.get("/api/words", params={"level": "A1", "topic": "not-a-topic"}).json() == []
    assert client.get("/api/words", params={"level": "C1"}).status_code == 400
