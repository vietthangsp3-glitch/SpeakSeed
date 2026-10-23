import json
import sqlite3
from collections import Counter

import pytest
from fastapi.testclient import TestClient

import app as application
import question_bank
from migrations import run_migrations
from tools.content_pipeline import load_registry
from tools.content_review import edit_draft, preview, publish_batch, review
from tools.question_bank_phase3 import audit_bank


ROOT = application.ROOT


def add_draft(database, stable_id="q-published", *, linked=True):
    source = load_registry(ROOT / "data" / "source_registry.json")["cefr-j-1.5"]
    con = sqlite3.connect(database)
    columns = ("display_name","owner_name","source_url","dataset_version","license_name",
               "license_url","commercial_use","attribution","obligations","audit_status",
               "evidence_url","audited_at","notes")
    con.execute(
        f"INSERT OR IGNORE INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(14))})",
        ["cefr-j-1.5", *(source[key] for key in columns)],
    )
    batch = con.execute("SELECT id FROM content_import_batches WHERE source_sha256='phase3-test'").fetchone()
    if not batch:
        batch = (con.execute("""INSERT INTO content_import_batches(source_key,source_version,source_sha256,
            importer_version,status,started_at) VALUES('cefr-j-1.5','test','phase3-test','test','staged','now')""").lastrowid,)
    staging = con.execute("""INSERT INTO content_staging_records(batch_id,content_type,source_record_id,
        stable_key,normalized_hash,payload_json,validation_status,quality_status,created_at)
        VALUES(?,'question',?,?,?,?, 'valid','automated_checked','now')""",
        (batch[0], stable_id, stable_id, stable_id, "{}"),).lastrowid
    draft = con.execute("""INSERT INTO question_bank_drafts(staging_record_id,stable_id,question_type,
        cefr_level,skill,topic,difficulty,prompt,answer_key_json,accepted_answers_json,explanation_vi,
        source_key,source_record_id,license_name,quality_status,created_at,updated_at,payload_json,placement_eligible)
        VALUES(?,?,'multiple_choice','A2','grammar','present simple',2,'Choose the correct answer.',
        '["does"]','["does","Does"]','Ngôi thứ ba số ít dùng does.','cefr-j-1.5',?,?,'automated_checked',
        '2020-01-01T00:00:00+00:00','2020-01-01T00:00:00+00:00',?,1)""",
        (staging, stable_id, stable_id, source["license_name"], json.dumps({"options":["do","does","did"]})),).lastrowid
    if linked:
        con.execute("INSERT INTO question_bank_links(question_id,learning_context,ref_type,ref_id) VALUES(?,'grammar','test',1)", (draft,))
    con.commit(); con.close()
    return draft


def setup_database(tmp_path, monkeypatch):
    database = tmp_path / "question-bank.db"
    run_migrations(database, ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    return database, TestClient(application.app)


def register(client, email):
    response = client.post("/api/register", json={"name":"QA","email":email,"password":"correct-horse"})
    assert response.status_code == 200
    return {"Authorization":"Bearer " + response.json()["token"]}, response.json()["user"]["id"]


def test_review_edit_audit_publish_gate_and_immutable_log(tmp_path, monkeypatch):
    database, _ = setup_database(tmp_path, monkeypatch)
    draft = add_draft(database)
    assert preview(database, draft)["answers_hidden"] is True
    with pytest.raises(ValueError, match="confirm"):
        publish_batch(database, [draft], "Publisher", "release", False)
    con = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="human review evidence"):
        con.execute("UPDATE question_bank_drafts SET review_status='human_reviewed' WHERE id=?", (draft,))
    con.close()
    audit_bank(database)
    review(database, draft, "Human Reviewer", "approve", "Checked prompt, answer and rationale")
    result = publish_batch(database, [draft], "Human Publisher", "Approved beta batch", True)
    assert result["published"] == 1
    con = sqlite3.connect(database)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        con.execute("UPDATE content_review_events SET notes='tampered'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        con.execute("UPDATE question_bank_drafts SET prompt='changed' WHERE id=?", (draft,))
    con.close()


def test_only_published_questions_are_visible_answers_are_hidden_and_attempts_are_scoped(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    published = add_draft(database, "visible")
    add_draft(database, "pending")
    audit_bank(database)
    review(database, published, "Human Reviewer", "approve", "Checked")
    publish_batch(database, [published], "Human Publisher", "Release", True)
    owner, owner_id = register(client, "bank-owner@example.com")
    other, other_id = register(client, "bank-other@example.com")
    assert client.get("/api/question-bank/questions?context=grammar").status_code == 401
    listing = client.get("/api/question-bank/questions?context=grammar", headers=owner)
    assert listing.status_code == 200 and listing.json()["count"] == 1
    public = listing.json()["questions"][0]
    assert public["question_bank_id"] == published
    assert "answers" not in public and "explanation_vi" not in public
    checked = client.post("/api/question-bank/check", headers=owner,
                          json={"question_id":published,"context":"grammar","answer":"Does"})
    assert checked.status_code == 200 and checked.json()["correct"] is True
    assert checked.json()["explanation_vi"]
    assert client.post("/api/question-bank/check", headers=other,
                       json={"question_id":published,"context":"grammar","answer":"do"}).status_code == 200
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM question_bank_attempts WHERE user_id=?", (owner_id,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM question_bank_attempts WHERE user_id=?", (other_id,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM question_bank_attempts").fetchone()[0] == 2
    con.close()


def test_edit_invalidates_review_and_qa(tmp_path, monkeypatch):
    database, _ = setup_database(tmp_path, monkeypatch)
    draft = add_draft(database)
    audit_bank(database)
    review(database, draft, "Reviewer", "approve", "Checked")
    result = edit_draft(database, draft, "Editor", "Clarify prompt", prompt="Choose the correct auxiliary.")
    assert result["qa_required"] is True
    con = sqlite3.connect(database)
    assert con.execute("SELECT review_status FROM question_bank_drafts WHERE id=?", (draft,)).fetchone()[0] == "pending"
    assert con.execute("SELECT COUNT(*) FROM question_qa_results WHERE question_id=?", (draft,)).fetchone()[0] == 0
    con.close()


def test_listening_audio_is_private_published_only_and_transcript_follows_submit(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    draft = add_draft(database, "listening-visible", linked=False)
    con = sqlite3.connect(database)
    con.execute("""UPDATE question_bank_drafts SET question_type='listening',skill='listening',
        context_text='Where is the station?',prompt='What does the speaker ask?',
        answer_key_json='[\"the station location\"]',accepted_answers_json='[\"the station location\"]',
        payload_json=? WHERE id=?""",
        (json.dumps({"transcript":"Where is the station?",
                     "options":["the station location","the ticket price","the train time"]}), draft))
    con.execute("INSERT INTO question_bank_links(question_id,learning_context,ref_type,ref_id) VALUES(?,'listening','test',1)", (draft,))
    con.commit(); con.close()
    audit_bank(database)
    review(database, draft, "Human Reviewer", "approve", "Checked listening prompt and transcript")
    publish_batch(database, [draft], "Human Publisher", "Release listening fixture", True)
    headers, _ = register(client, "bank-listening@example.com")

    listing = client.get("/api/question-bank/questions?context=listening", headers=headers).json()
    assert listing["count"] == 1
    assert "transcript_en" not in listing["questions"][0]
    audio = client.get(f"/api/question-bank/audio/{draft}?context=listening", headers=headers)
    assert audio.status_code == 200
    assert audio.json() == {"text":"Where is the station?","language":"en-US","engine":"web-speech"}
    assert audio.headers["cache-control"] == "private, no-store"
    checked = client.post("/api/question-bank/check", headers=headers,
                          json={"question_id":draft,"context":"listening","answer":"the station location"})
    assert checked.status_code == 200
    assert checked.json()["transcript_en"] == "Where is the station?"


def test_non_listening_question_has_no_audio_endpoint(tmp_path, monkeypatch):
    database, client = setup_database(tmp_path, monkeypatch)
    draft = add_draft(database)
    audit_bank(database)
    review(database, draft, "Human Reviewer", "approve", "Checked")
    publish_batch(database, [draft], "Human Publisher", "Release", True)
    headers, _ = register(client, "bank-no-audio@example.com")
    assert client.get(f"/api/question-bank/audio/{draft}?context=grammar", headers=headers).status_code == 404


def test_conditional_source_requires_explicit_license_confirmation(tmp_path, monkeypatch):
    database, _ = setup_database(tmp_path, monkeypatch)
    draft = add_draft(database)
    audit_bank(database)
    review(database, draft, "Human Reviewer", "approve", "Checked")
    con = sqlite3.connect(database)
    con.execute("UPDATE content_sources SET audit_status='conditional',commercial_use='conditional' WHERE source_key='cefr-j-1.5'")
    con.commit(); con.close()
    with pytest.raises(ValueError, match="confirm-license-conditions"):
        publish_batch(database, [draft], "Publisher", "License conditions checked", True)
    result = publish_batch(database, [draft], "Publisher", "License conditions checked", True, True)
    assert result["published"] == 1


def test_placement_adapter_requires_and_preserves_exact_legacy_matrix(monkeypatch):
    quotas = {
        "A0":{"grammar":3,"vocabulary":0,"listening":2,"fill_blank":1,"sentence_ordering":1,"reading":1},
        "A1":{"grammar":1,"vocabulary":2,"listening":2,"fill_blank":1,"sentence_ordering":1,"reading":1},
        "A2":{"grammar":1,"vocabulary":1,"listening":2,"fill_blank":2,"sentence_ordering":1,"reading":1},
        "B1":{"grammar":1,"vocabulary":1,"listening":1,"fill_blank":2,"sentence_ordering":1,"reading":2},
        "B2":{"grammar":1,"vocabulary":1,"listening":1,"fill_blank":2,"sentence_ordering":2,"reading":1},
    }
    rows = []
    for level, sections in quotas.items():
        for section, count in sections.items():
            for index in range(count):
                question_type = {"fill_blank":"fill_blank", "sentence_ordering":"sentence_ordering",
                                 "listening":"listening", "reading":"reading"}.get(section, "multiple_choice")
                skill = section if section in {"grammar","vocabulary","listening","reading"} else "grammar"
                payload = {"options":["yes","no"]}
                if section == "sentence_ordering": payload = {"tokens":["It","works"]}
                if section == "listening": payload["transcript"] = "It works."
                if section == "reading": payload["passage"] = "It works."
                rows.append({"id":len(rows)+1,"placement_eligible":1,"question_type":question_type,
                             "skill":skill,"cefr_level":level,"topic":"test","difficulty":1,
                             "prompt":"Test?","accepted_answers_json":'["yes"]',"answer_key_json":'["yes"]',
                             "explanation_vi":"Giải thích.","source_key":"test","license_name":"test",
                             "payload_json":json.dumps(payload),"context_text":"",
                             "review_status":"human_reviewed"})
    monkeypatch.setattr(question_bank, "published_rows", lambda con, context, limit=1000: rows)
    form = question_bank.placement_form(object())
    assert len(form) == 40
    assert Counter((item["level"], item["section"]) for item in form) == Counter(
        {(level, section): count for level, sections in quotas.items() for section, count in sections.items() if count}
    )
    monkeypatch.setattr(question_bank, "published_rows", lambda con, context, limit=1000: rows[:-1])
    assert question_bank.placement_form(object()) is None


def test_phase3_postgres_migrations_use_postgres_trigger_syntax():
    for name in ("015_question_bank_integration.sql", "016_question_publication_license_gate.sql"):
        sql = (ROOT / "deploy" / "postgres" / name).read_text(encoding="utf-8")
        assert "LANGUAGE plpgsql" in sql
        assert "RAISE(ABORT" not in sql
        assert "AUTOINCREMENT" not in sql
    assert "license_conditions_confirmed" in (
        ROOT / "deploy" / "postgres" / "016_question_publication_license_gate.sql"
    ).read_text(encoding="utf-8")
