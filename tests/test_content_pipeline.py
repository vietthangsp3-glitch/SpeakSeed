import json
import sqlite3
from pathlib import Path

import pytest

from import_data import main as legacy_import_main
from migrations import run_migrations
from tools.content_pipeline import (
    PipelineError,
    file_sha256,
    license_gate,
    load_registry,
    rollback_batch,
    scan,
    stage_streaming,
    stage_records,
    write_report,
)
from tools.content_review import edit_draft, materialize_question_drafts, review
from tools.enrich_vocabulary import enrich
from tools.question_bank_phase3 import audit_bank


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "source_registry.json"


def cefr_fixture(path: Path) -> None:
    path.write_text(
        "headword,pos,CEFR,CoreInventory 1,CoreInventory 2,Threshold\n"
        "apple,noun,A1,,,\n"
        "look after,verb,A2,,,\n"
        "apple,noun,A1,,,\n"
        "invalid!,noun,A1,,,\n",
        encoding="utf-8",
    )


def test_dry_run_reads_real_format_without_touching_database(tmp_path):
    source_file = tmp_path / "cefr.csv"
    database = tmp_path / "must-not-exist.db"
    cefr_fixture(source_file)
    rows, report = scan(source_file, "cefr-j-1.5", limit=100)
    assert report == {
        "source": "cefr-j-1.5", "input": str(source_file.resolve()),
        "processed": 4, "valid": 2, "rejected": 2, "duplicates": 1,
        "rejection_reasons": {"duplicate_stable_key": 1, "invalid_headword": 1},
        "publishes_content": False, "human_reviewed": 0,
    }
    assert len(rows) == 4
    assert not database.exists()


def test_staging_is_idempotent_and_never_publishes(tmp_path):
    source_file = tmp_path / "cefr.csv"
    database = tmp_path / "app.db"
    cefr_fixture(source_file)
    registry = load_registry(REGISTRY)
    rows, report = scan(source_file, "cefr-j-1.5", limit=100)
    source_hash = file_sha256(source_file)
    first = stage_records(database, ROOT / "migrations", "cefr-j-1.5",
                          registry["cefr-j-1.5"], source_hash, rows, report)
    second = stage_records(database, ROOT / "migrations", "cefr-j-1.5",
                           registry["cefr-j-1.5"], source_hash, rows, report)
    assert first["idempotent_reuse"] is False
    assert second["idempotent_reuse"] is True
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM content_import_batches").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM content_staging_records").fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE published=1").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM library_words").fetchone()[0] == 0
    con.close()


def test_rejected_and_conditional_sources_are_license_gated():
    registry = load_registry(REGISTRY)
    with pytest.raises(PipelineError, match="blocked"):
        license_gate("words-cefr-dataset", registry["words-cefr-dataset"], False)
    with pytest.raises(PipelineError, match="conditional"):
        license_gate("tatoeba-text", registry["tatoeba-text"], False)
    license_gate("tatoeba-text", registry["tatoeba-text"], True)


def test_unreviewed_or_incomplete_question_cannot_be_published(tmp_path):
    database = tmp_path / "app.db"
    run_migrations(database, ROOT / "migrations")
    registry = load_registry(REGISTRY)["elispeak-common-mistakes"]
    con = sqlite3.connect(database)
    columns = (
        "display_name", "owner_name", "source_url", "dataset_version", "license_name",
        "license_url", "commercial_use", "attribution", "obligations", "audit_status",
        "evidence_url", "audited_at", "notes",
    )
    con.execute(
        f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(len(columns)+1))})",
        ["elispeak-common-mistakes", *(registry[column] for column in columns)],
    )
    batch_id = con.execute(
        """INSERT INTO content_import_batches(source_key,source_version,source_sha256,
        importer_version,status,started_at) VALUES(?,?,?,?,?,?)""",
        ("elispeak-common-mistakes", "test", "abc", "test", "staged", "now"),
    ).lastrowid
    staging_id = con.execute(
        """INSERT INTO content_staging_records(batch_id,content_type,source_record_id,
        stable_key,normalized_hash,payload_json,validation_status,quality_status,created_at)
        VALUES(?,?,?,?,?,?,?,?,'now')""",
        (batch_id, "question", "q1", "q1", "hash", "{}", "valid", "needs_review"),
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError, match="not publishable"):
        con.execute(
            """INSERT INTO question_bank_drafts(staging_record_id,stable_id,question_type,
            cefr_level,skill,topic,difficulty,prompt,answer_key_json,explanation_vi,source_key,
            source_record_id,license_name,quality_status,review_status,published,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (staging_id, "q1", "error_correction", "A2", "grammar", "verbs", 2,
             "She go.", '["She goes."]', "", "elispeak-common-mistakes", "q1", "MIT",
             "needs_review", "pending", 1, "now", "now"),
        )
    con.close()


def test_staging_batch_can_be_rolled_back_without_learning_data_loss(tmp_path):
    source_file = tmp_path / "cefr.csv"
    database = tmp_path / "app.db"
    cefr_fixture(source_file)
    registry = load_registry(REGISTRY)
    rows, report = scan(source_file, "cefr-j-1.5", limit=100)
    staged = stage_records(database, ROOT / "migrations", "cefr-j-1.5",
                           registry["cefr-j-1.5"], file_sha256(source_file), rows, report)
    result = rollback_batch(database, staged["batch_id"])
    assert result["removed"] == 4
    con = sqlite3.connect(database)
    assert con.execute("SELECT status FROM content_import_batches WHERE id=?", (staged["batch_id"],)).fetchone()[0] == "rolled_back"
    assert con.execute("SELECT COUNT(*) FROM content_staging_records").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM progress").fetchone()[0] == 0
    con.close()


def test_report_falls_back_on_legacy_windows_console(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    calls = []

    def legacy_print(value):
        calls.append(value)
        if "luyện" in value:
            raise UnicodeEncodeError("cp1252", value, 0, 1, "unsupported")

    monkeypatch.setattr("builtins.print", legacy_print)
    write_report(output, {"path": "E:/luyện tiếng Anh"})
    assert len(calls) == 2
    assert "\\u1ec7" in calls[1]
    assert "luyện" in output.read_text(encoding="utf-8")


def test_legacy_importer_cannot_publish_directly(tmp_path, monkeypatch):
    sample = tmp_path / "sample.csv"
    sample.write_text("headword,pos,CEFR\napple,noun,A1\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["import_data.py", "cefrj-vocab", str(sample), "--publish"])
    with pytest.raises(SystemExit) as error:
        legacy_import_main()
    assert error.value.code == 2


def test_streaming_checkpoint_resume_and_idempotency(tmp_path):
    source_file = tmp_path / "cefr.csv"
    database = tmp_path / "app.db"
    cefr_fixture(source_file)
    source = load_registry(REGISTRY)["cefr-j-1.5"]
    interrupted = stage_streaming(database, ROOT / "migrations", "cefr-j-1.5", source,
                                  source_file, limit=100, batch_size=2, resume=False, stop_after=2)
    assert interrupted["status"] == "running"
    assert interrupted["checkpoint"] == 2
    with pytest.raises(PipelineError, match="--resume"):
        stage_streaming(database, ROOT / "migrations", "cefr-j-1.5", source,
                        source_file, limit=100, batch_size=2, resume=False)
    resumed = stage_streaming(database, ROOT / "migrations", "cefr-j-1.5", source,
                              source_file, limit=100, batch_size=2, resume=True)
    reused = stage_streaming(database, ROOT / "migrations", "cefr-j-1.5", source,
                             source_file, limit=100, batch_size=2, resume=False)
    assert resumed["processed"] == 4
    assert resumed["valid"] == 2
    assert resumed["rejected"] == 2
    assert reused["idempotent_reuse"] is True


def test_field_enrichment_does_not_overwrite_base_word(tmp_path):
    database = tmp_path / "app.db"
    source_file = tmp_path / "cefr.csv"
    cefr_fixture(source_file)
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database)
    con.execute("""INSERT INTO library_words(
                   id,word,meaning,ipa,example,example_vi,topic,stage,pos,normalized_word,
                   source,source_id,license,reviewed,quality_score,updated_at)
                   VALUES(1,'apple','quả táo','/ˈæpəl/','I eat an apple.','Tôi ăn một quả táo.',
                   'Food','A1','noun','apple','test','apple','test',1,100,'now')""")
    con.commit(); con.close()
    source = load_registry(REGISTRY)["cefr-j-1.5"]
    stage_streaming(database, ROOT / "migrations", "cefr-j-1.5", source,
                    source_file, limit=100, batch_size=2, resume=False)
    result = enrich(database)
    con = sqlite3.connect(database)
    word = con.execute("SELECT id,meaning,stage,pos FROM library_words WHERE id=1").fetchone()
    con.close()
    assert word == (1, "quả táo", "A1", "noun")
    assert result["base_rows_modified"] == 0
    assert result["human_reviewed"] == 0


def test_reviewer_identity_audit_and_publish_gate(tmp_path):
    database = tmp_path / "app.db"
    source_file = tmp_path / "elispeak.jsonl"
    source_file.write_text(json.dumps({
        "id": "q1", "cefr": "A2", "learner_sentence": "She go home.",
        "corrected_sentence": "She goes home.", "explanation": "Third-person singular takes -s.",
        "category": "subject verb agreement",
    }) + "\n", encoding="utf-8")
    source = load_registry(REGISTRY)["elispeak-common-mistakes"]
    stage_streaming(database, ROOT / "migrations", "elispeak-common-mistakes", source,
                    source_file, limit=100, batch_size=10, resume=False)
    assert materialize_question_drafts(database)["created"] == 1
    with pytest.raises(ValueError, match="identity"):
        review(database, 1, "", "approve", "checked", "Chủ ngữ ngôi thứ ba cần thêm -s.")
    with pytest.raises(ValueError, match="Vietnamese"):
        review(database, 1, "Reviewer A", "approve", "checked")
    edit_draft(database, 1, "Reviewer A", "Bổ sung giải thích",
               explanation_vi="Chủ ngữ ngôi thứ ba số ít cần động từ thêm -s.")
    audit_bank(database)
    result = review(database, 1, "Reviewer A", "approve", "checked")
    assert result["published"] is False
    con = sqlite3.connect(database)
    assert con.execute("SELECT COUNT(*) FROM content_review_events WHERE reviewer_name='Reviewer A'").fetchone()[0] == 1
    assert con.execute("SELECT review_status,published FROM question_bank_drafts").fetchone() == ("human_reviewed", 0)
    con.close()


def test_human_reviewed_cannot_be_inserted_without_audit_evidence(tmp_path):
    database = tmp_path / "app.db"
    run_migrations(database, ROOT / "migrations")
    source = load_registry(REGISTRY)["cefr-j-1.5"]
    con = sqlite3.connect(database)
    columns = ("display_name", "owner_name", "source_url", "dataset_version", "license_name",
               "license_url", "commercial_use", "attribution", "obligations", "audit_status",
               "evidence_url", "audited_at", "notes")
    con.execute(
        f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(len(columns)+1))})",
        ["cefr-j-1.5", *(source[column] for column in columns)],
    )
    batch = con.execute("""INSERT INTO content_import_batches(source_key,source_version,source_sha256,
        importer_version,status,started_at) VALUES('cefr-j-1.5','x','x','x','staged','now')""").lastrowid
    with pytest.raises(sqlite3.IntegrityError, match="human review evidence"):
        con.execute("""INSERT INTO content_staging_records(batch_id,content_type,source_record_id,
          stable_key,normalized_hash,payload_json,validation_status,quality_status,review_status,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""", (batch, "vocabulary", "x", "x", "x", "{}",
          "valid", "automated_checked", "human_reviewed", "now"))
    con.close()
