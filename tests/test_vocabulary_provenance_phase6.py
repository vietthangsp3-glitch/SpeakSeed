import gzip
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations
from tools import recover_vocabulary_phase6 as phase6
from tools.vocabulary_topics import list_mappings
from vocabulary_release import core_errors


def make_snapshot(path):
    rows = [
        {"word": "orchard", "lang_code": "en", "pos": "noun",
         "senses": [{"glosses": ["Vườn cây ăn quả. [từ thế kỷ XV]"]}]},
        {"word": "datedword", "lang_code": "en", "pos": "noun",
         "senses": [{"glosses": ["Một nghĩa cũ."], "tags": ["obsolete"]}]},
    ]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_candidate(database):
    run_migrations(database, application.ROOT / "migrations")
    with sqlite3.connect(database) as con:
        source = json.loads((application.ROOT / "data/source_registry.json").read_text(encoding="utf-8"))["sources"]["cefr-j-1.5"]
        columns = ("display_name", "owner_name", "source_url", "dataset_version", "license_name", "license_url",
                   "commercial_use", "attribution", "obligations", "audit_status", "evidence_url", "audited_at", "notes")
        con.execute(f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(14))})",
                    ("cefr-j-1.5", *(source[column] for column in columns)))
        provenance = json.dumps({
            "headword_pos_cefr": {"source": "cefr-j-1.5", "record": "line:1"},
            "meaning_vi_ipa": {"source": "skypedia-en-vi", "status": "conditional_unresolved"},
        })
        con.execute("""INSERT INTO vocabulary_candidates(stable_key,normalized_word,word,pos,meaning_vi,ipa,cefr_level,
          source_key,source_record_id,provenance_json,license_status,qa_status,core_status,policy_version,created_at,updated_at)
          VALUES('orchard|noun|A2','orchard','orchard','noun','vườn cây','/old/','A2','cefr-j-1.5','line:1',?,
          'blocked','pass','license_blocked','core-v1','now','now')""", (provenance,))
        candidate_id = con.execute("SELECT id FROM vocabulary_candidates").fetchone()[0]
        topic_id = con.execute("SELECT id FROM vocabulary_topics WHERE slug='nature-environment'").fetchone()[0]
        con.execute("INSERT INTO vocabulary_candidate_topics VALUES(?,?,95,'princeton-wordnet-3.0','exact token','pending')",
                    (candidate_id, topic_id))
    return candidate_id


def test_phase6_recovery_is_traceable_idempotent_and_never_publishes(tmp_path, monkeypatch):
    database = tmp_path / "staging.db"
    candidate_id = seed_candidate(database)
    snapshot = tmp_path / "vi.jsonl.gz"
    monkeypatch.setattr(phase6, "SNAPSHOT_SHA256", make_snapshot(snapshot))
    monkeypatch.setattr(phase6, "wordnet_sense_counts", lambda con: {("orchard", "noun"): 1})
    output = tmp_path / "batch.json"
    first = phase6.recover(database, snapshot, application.ROOT / "data/source_registry.json", 1, output)
    second = phase6.recover(database, snapshot, application.ROOT / "data/source_registry.json", 1, output)
    assert first["first_review_batch"]["count"] == second["first_review_batch"]["count"] == 1
    assert first["legacy_field_audit"]["ipa_unverified"] == second["legacy_field_audit"]["ipa_unverified"] == 1
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()
        provenance = json.loads(row["provenance_json"])
        assert row["meaning_vi"] == "Vườn cây ăn quả."
        assert row["ipa"] == "" and row["core_status"] == "review_ready"
        assert row["license_status"] == row["qa_status"] == "pass"
        assert row["review_status"] == "pending" and row["published_word_id"] is None
        assert provenance["meaning_vi"]["classification"] == "CONDITIONAL"
        assert provenance["ipa"]["classification"] == "UNVERIFIED"
        assert con.execute("SELECT COUNT(*) FROM content_reviewer_roles").fetchone()[0] == 0
        assert core_errors(con, candidate_id) == []


def test_phase6_rejects_non_primary_or_restricted_glosses():
    assert phase6.clean_gloss({"senses": [{"glosses": ["Một nghĩa."], "tags": ["slang"]}]}) is None
    assert phase6.clean_gloss({"senses": [{"glosses": ["Một dạng."], "form_of": [{"word": "x"}]}]}) is None
    assert phase6.clean_gloss({"senses": [{"glosses": ["Nhuấy & 120 iat."]}]}) is None
    assert phase6.independent_meaning_agreement("Tạp dề.", "Cái tạp dề dùng khi nấu ăn.")
    assert not phase6.independent_meaning_agreement("Áo giáp.", "Thư, bưu phẩm.")


def test_topic_review_batch_is_separate_and_confidence_sorted(tmp_path):
    database = tmp_path / "topics.db"
    run_migrations(database, application.ROOT / "migrations")
    with sqlite3.connect(database) as con:
        columns = "word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at"
        con.execute(f"INSERT INTO library_words({columns}) VALUES('river','sông','','','Nature','x','A1','noun','x','x','x',1,'river','',100,'now')")
        word_id = con.execute("SELECT id FROM library_words").fetchone()[0]
        topics = con.execute("SELECT id FROM vocabulary_topics ORDER BY id LIMIT 2").fetchall()
        con.execute("INSERT INTO vocabulary_topic_words VALUES(?,?,'','pending',0,49,'wordnet','evidence','now',NULL,'')", (word_id, topics[0][0]))
        con.execute("INSERT INTO vocabulary_topic_words VALUES(?,?,'','pending',0,95,'wordnet','evidence','now',NULL,'')", (word_id, topics[1][0]))
    rows = list_mappings(database, "pending", 10, 45)
    assert [row["confidence"] for row in rows] == [95, 49]
    assert all(row["published"] == 0 and row["review_status"] == "pending" for row in rows)


def test_public_attribution_page_is_available():
    response = TestClient(application.app).get("/data-attribution")
    assert response.status_code == 200
    assert "CC BY-SA 4.0" in response.text and "Kaikki" in response.text
