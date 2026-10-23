"""Safely apply the additive Placement Test v2 schema to an existing PostgreSQL DB.

Dry-run is the default. The tool never copies or deletes user/content records.
"""
from __future__ import annotations

import argparse
import json
import os


VERSIONS = ("009_placement_test_v2.sql", "010_placement_order_drafts.sql")
VERSION = VERSIONS[-1]
REQUIRED_PREVIOUS_VERSION = "008_beta_hardening.sql"

DDL_STATEMENTS = ("""CREATE TABLE placement_responses(
  attempt_id BIGINT NOT NULL REFERENCES placement_attempts(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_key TEXT NOT NULL,
  answer TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'answered'
    CHECK(state IN ('in_progress','answered','skipped','audio_unavailable')),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(attempt_id,question_key)
)""", """CREATE INDEX idx_placement_responses_owner
  ON placement_responses(user_id,attempt_id,updated_at)""")


def inspect_target(connection) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        versions = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT to_regclass('public.placement_responses')")
        table_exists = cursor.fetchone()[0] is not None
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM placement_attempts")
        attempts = cursor.fetchone()[0]
    return {"versions": versions, "table_exists": table_exists,
            "users": users, "placement_attempts": attempts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply SpeakSeed Placement Test v2 PostgreSQL schema")
    parser.add_argument("--target-url", help="Defaults to DATABASE_URL")
    parser.add_argument("--apply", action="store_true", help="Apply in one transaction; default is dry-run")
    args = parser.parse_args()
    target = args.target_url or os.getenv("DATABASE_URL", "").strip()
    if not target.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL or pass a PostgreSQL --target-url")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Install psycopg[binary] before running this tool") from exc

    with psycopg.connect(target) as connection:
        before = inspect_target(connection)
        if VERSION in before["versions"]:
            if not before["table_exists"]:
                raise SystemExit(f"{VERSION} is recorded but placement_responses is missing")
            print(json.dumps({"status": "already_applied", "version": VERSION,
                              "users_preserved": before["users"],
                              "placement_attempts_preserved": before["placement_attempts"]}))
            return
        if REQUIRED_PREVIOUS_VERSION not in before["versions"]:
            raise SystemExit(f"Target must already contain {REQUIRED_PREVIOUS_VERSION}")
        if before["table_exists"]:
            raise SystemExit("placement_responses exists without a migration record; refusing schema drift")
        if not args.apply:
            print(json.dumps({"status": "dry_run", "will_apply": VERSION,
                              "users_to_preserve": before["users"],
                              "placement_attempts_to_preserve": before["placement_attempts"]}))
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("LOCK TABLE schema_migrations IN SHARE ROW EXCLUSIVE MODE")
                for statement in DDL_STATEMENTS:
                    cursor.execute(statement)
                for version in VERSIONS:
                    cursor.execute("INSERT INTO schema_migrations(version) VALUES(%s) ON CONFLICT DO NOTHING", (version,))
            after = inspect_target(connection)
            if after["users"] != before["users"] or after["placement_attempts"] != before["placement_attempts"]:
                raise RuntimeError("Record counts changed unexpectedly; rolling back")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    print(json.dumps({"status": "applied", "version": VERSION,
                      "users_preserved": before["users"],
                      "placement_attempts_preserved": before["placement_attempts"]}))


if __name__ == "__main__":
    main()
