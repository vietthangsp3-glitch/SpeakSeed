import json
import sqlite3

import pytest

from migrations import run_migrations
from tools.publish_vocabulary_automatic import candidate_is_eligible


def test_automated_release_evidence_allows_truthful_topic_publication(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    database = tmp_path / "automatic.db"
    run_migrations(database, root / "migrations")
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,
          license,reviewed,normalized_word,example_vi,quality_score,updated_at)
          VALUES('orchard','vườn cây','','','Nature','📘','A2','noun','test','record','CC BY-SA 4.0',1,
          'orchard','',90,'now')""")
        word_id = con.execute("SELECT id FROM library_words WHERE normalized_word='orchard'").fetchone()[0]
        con.execute("""INSERT INTO vocabulary_automated_releases(word_id,source_candidate_ids_json,source_key,
          source_snapshot_sha256,rule_version,checks_json,provenance_json,released_at)
          VALUES(?,?,?,?,?,?,?,?)""", (word_id, "[1]", "test", "sha", "auto-core-v1",
                                      json.dumps({"human_reviewed": False}), "{}", "now"))
        topic_id = con.execute("SELECT id FROM vocabulary_topics WHERE slug='nature-environment'").fetchone()[0]
        con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,
          confidence,source_key,rationale,created_at) VALUES(?,?,'','pending',1,90,
          'automated-release-v1','Automated evidence','now')""", (word_id, topic_id))
        status = con.execute("SELECT review_status,published FROM vocabulary_topic_words WHERE word_id=?",
                             (word_id,)).fetchone()
        assert status == ("pending", 1)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("UPDATE vocabulary_automated_releases SET checks_json='{}' WHERE word_id=?", (word_id,))


def test_automated_topic_publish_without_evidence_is_blocked(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    database = tmp_path / "blocked.db"
    run_migrations(database, root / "migrations")
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO library_words(word,meaning,topic,stage,pos,source,reviewed,normalized_word)
          VALUES('orchard','vườn cây','Nature','A2','noun','test',1,'orchard')""")
        word_id = con.execute("SELECT id FROM library_words WHERE normalized_word='orchard'").fetchone()[0]
        topic_id = con.execute("SELECT id FROM vocabulary_topics WHERE slug='nature-environment'").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="automated evidence"):
            con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,
              confidence,source_key,rationale,created_at) VALUES(?,?,'','pending',1,90,
              'automated-release-v1','Missing evidence','now')""", (word_id, topic_id))


def test_candidate_gate_requires_exact_source_and_corroborated_meaning(tmp_path):
    database = tmp_path / "row.db"
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        con.execute("""CREATE TABLE candidate(normalized_word TEXT,pos TEXT,cefr_level TEXT,meaning_vi TEXT,
          source_key TEXT,source_record_id TEXT,provenance_json TEXT)""")
        con.execute("INSERT INTO candidate VALUES(?,?,?,?,?,?,?)", (
            "orchard", "noun", "A2", "vườn cây ăn quả", "legacy", "old", "{}"))
        row = con.execute("SELECT * FROM candidate").fetchone()
        evidence = {"meaning_vi": "Vườn cây.", "source_record_id": "line:1", "ipa": "",
                    "page_url": "https://vi.wiktionary.org/wiki/orchard"}
        assert candidate_is_eligible(row, evidence) == (True, "eligible")
        mismatch = dict(evidence, meaning_vi="Thiết bị điện tử.")
        assert candidate_is_eligible(row, mismatch)[1] == "meaning_not_independently_corroborated"
        assert candidate_is_eligible(row, None)[1] == "no_clean_exact_licensed_record"


def test_published_normalized_word_is_unique(tmp_path):
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    database = tmp_path / "dedupe.db"
    run_migrations(database, root / "migrations")
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO library_words(word,meaning,topic,stage,pos,source,reviewed,normalized_word)
          VALUES('orchard','vườn cây','Nature','A2','noun','test',1,'orchard')""")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("""INSERT INTO library_words(word,meaning,topic,stage,pos,source,reviewed,normalized_word)
              VALUES('Orchard','vườn cây ăn quả','Nature','A2','noun','test',1,'orchard')""")


def test_postgres_automatic_release_migration_is_native_sql():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    sql = (root / "deploy/postgres/020_automated_vocabulary_release.sql").read_text(encoding="utf-8")
    assert "LANGUAGE plpgsql" in sql and "GENERATED BY DEFAULT AS IDENTITY" in sql
    assert "RAISE(ABORT" not in sql and "INSERT OR IGNORE" not in sql
