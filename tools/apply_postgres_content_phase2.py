"""Explicit PostgreSQL Phase-2 migrator; never runs during application startup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ["011_content_import_pipeline.sql", "012_content_pipeline_phase2.sql", "013_content_question_payload.sql", "014_content_review_hardening.sql", "015_question_bank_integration.sql", "016_question_publication_license_gate.sql", "017_vocabulary_topics.sql", "018_vocabulary_release_workflow.sql", "019_content_license_decisions.sql", "020_automated_vocabulary_release.sql", "021_automated_topic_classification.sql"]


def apply(target_url: str) -> dict:
    import psycopg
    directory = ROOT / "deploy" / "postgres"
    with psycopg.connect(target_url) as con:
        with con.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (8133713,))
            cursor.execute("SELECT to_regclass('public.schema_migrations'),to_regclass('public.users'),to_regclass('public.library_words')")
            if any(value is None for value in cursor.fetchone()):
                raise RuntimeError("Target is not an initialized SpeakSeed database")
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            before = cursor.fetchone()[0]
            if before < "010_placement_order_drafts.sql":
                raise RuntimeError(f"Apply migrations through 010 first; target is {before}")
            applied = []
            for version in VERSIONS:
                cursor.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,))
                if cursor.fetchone():
                    continue
                cursor.execute((directory / version).read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO schema_migrations(version) VALUES(%s)", (version,))
                applied.append(version)
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
            tables = cursor.fetchone()[0]
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            after = cursor.fetchone()[0]
        con.commit()
    return {"before": before, "after": after, "applied": applied, "tables": tables}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-url")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"mode": "plan", "versions": VERSIONS, "writes": False}))
        return
    url = args.target_url or os.getenv("DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL to an explicitly authorized PostgreSQL staging database")
    print(json.dumps(apply(url), ensure_ascii=True))


if __name__ == "__main__":
    main()
