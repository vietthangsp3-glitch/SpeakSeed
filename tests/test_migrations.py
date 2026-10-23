import sqlite3
from pathlib import Path

from migrations import run_migrations


ROOT = Path(__file__).resolve().parents[1]


def test_migrations_are_repeatable_on_fresh_database(tmp_path):
    database = tmp_path / "fresh.db"
    run_migrations(database, ROOT / "migrations")
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database)
    versions = con.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert len(versions) == len(list((ROOT / "migrations").glob("*.sql")))
    columns = {row[1] for row in con.execute("PRAGMA table_info(progress)")}
    assert {"due_at", "interval_days", "ease_factor", "repetitions", "lapses"} <= columns
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"grammar_units", "grammar_lessons", "grammar_exercises", "grammar_attempts",
            "grammar_lesson_progress", "grammar_unit_progress", "auth_rate_limits", "ai_usage",
            "placement_responses", "content_sources", "content_import_batches",
            "content_staging_records", "content_review_events", "question_bank_drafts",
            "content_import_rejections", "word_enrichment_candidates",
            "word_enrichment_values", "word_enrichment_events", "question_qa_results",
            "question_draft_revisions", "question_publication_batches",
            "question_publication_items", "question_bank_attempts", "question_bank_links"} <= tables
    assert {"vocabulary_topics", "vocabulary_topic_words", "vocabulary_topic_reviews"} <= tables
    assert {"content_reviewer_roles", "vocabulary_quality_policies", "vocabulary_candidates",
            "vocabulary_candidate_topics", "vocabulary_candidate_events",
            "vocabulary_publish_batches", "vocabulary_publish_items"} <= tables
    assert "content_license_decisions" in tables
    draft_columns = {row[1] for row in con.execute("PRAGMA table_info(question_bank_drafts)")}
    assert {"payload_json", "attribution", "placement_eligible", "lesson_contexts_json",
            "published_at", "published_by"} <= draft_columns
    publication_columns = {row[1] for row in con.execute("PRAGMA table_info(question_publication_batches)")}
    assert "license_conditions_confirmed" in publication_columns
    session_columns = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    assert {"csrf_hash", "ip_hash", "user_agent_hash"} <= session_columns
