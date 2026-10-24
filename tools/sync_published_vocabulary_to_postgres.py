"""Non-destructive, idempotent published-vocabulary sync for an existing PostgreSQL site.

The command is read-only unless --apply is supplied with exact host/database
confirmations. It never touches account, session, progress, SRS or skill tables.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "data_sources", "library_words", "word_attributions", "vocabulary_topics",
    "vocabulary_automated_releases", "vocabulary_automated_topic_releases",
    "vocabulary_topic_corrections", "vocabulary_topic_words",
)


def _rows(source: sqlite3.Connection, table: str) -> list[dict]:
    if table == "library_words":
        query = "SELECT * FROM library_words WHERE reviewed=1 ORDER BY id"
    elif table == "word_attributions":
        query = "SELECT a.* FROM word_attributions a JOIN library_words w ON w.id=a.word_id WHERE w.reviewed=1 ORDER BY a.word_id,a.field_name,a.source_name"
    elif table == "vocabulary_topic_words":
        query = "SELECT * FROM vocabulary_topic_words WHERE published=1 ORDER BY word_id,topic_id,sense_key"
    else:
        query = f'SELECT * FROM "{table}" ORDER BY 1'
    return [dict(row) for row in source.execute(query)]


def _target_identity(cursor) -> dict:
    cursor.execute("SELECT current_database(),current_user,inet_server_addr()::text")
    database, user, address = cursor.fetchone()
    return {"database": database, "user": user, "server_address": address}


def _backup(cursor, directory: Path, identity: dict) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"postgres-vocabulary-before-sync-{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"kind": "manifest", "created_at": stamp, "target": identity,
                                 "tables": list(TABLES)}, ensure_ascii=False) + "\n")
        for table in TABLES:
            cursor.execute(f'SELECT * FROM "{table}" ORDER BY 1')
            columns = [item.name for item in cursor.description]
            for values in cursor.fetchall():
                stream.write(json.dumps({"table": table, "row": dict(zip(columns, values))},
                                        ensure_ascii=False, default=str) + "\n")
    return path


def sync(source_path: Path, target_url: str, apply: bool, confirm_host: str = "",
         confirm_database: str = "", backup_dir: Path | None = None) -> dict:
    import psycopg
    source = sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("SQLite source integrity_check failed")
    source_count = source.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0]
    if source_count < 6280:
        raise RuntimeError(f"SQLite source has only {source_count} published words")
    parsed = urlparse(target_url)
    with psycopg.connect(target_url) as target:
        with target.cursor() as cursor:
            identity = _target_identity(cursor)
            cursor.execute("SELECT to_regclass('public.schema_migrations'),to_regclass('public.library_words')")
            if any(value is None for value in cursor.fetchone()):
                raise RuntimeError("Target is not an initialized SpeakSeed database")
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            schema = cursor.fetchone()[0]
            if schema < "022_wordnet_topic_classification.sql":
                raise RuntimeError(f"Apply PostgreSQL migrations through 022 first; target is {schema}")
            cursor.execute("SELECT id,normalized_word FROM library_words WHERE reviewed=1")
            target_words = {row[1]: row[0] for row in cursor.fetchall()}
            local_words = _rows(source, "library_words")
            missing = [row for row in local_words if row["normalized_word"] not in target_words]
            conflicts = [row for row in missing if any(tid == row["id"] for tid in target_words.values())]
            if conflicts:
                raise RuntimeError(f"Target ID collision for {len(conflicts)} new words; refusing sync")
            result = {"mode": "apply" if apply else "dry-run", "target": identity, "schema": schema,
                      "source_published": source_count, "target_published_before": len(target_words),
                      "new_words": len(missing), "writes": False}
            if not apply:
                source.close()
                return result
            if parsed.hostname != confirm_host or identity["database"] != confirm_database:
                raise RuntimeError("--confirm-host and --confirm-database must exactly match the authorized target")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (6280021,))
            backup_path = _backup(cursor, backup_dir or ROOT / "qa_artifacts", identity)
            local_by_id = {row["id"]: row for row in local_words}
            # Existing published words are immutable in this sync. Verify the
            # original catalog rather than overwriting it.
            for normalized, target_id in target_words.items():
                local = next((r for r in local_words if r["normalized_word"] == normalized), None)
                if local and local["id"] != target_id:
                    raise RuntimeError(f"Original word ID mismatch for {normalized}")
            for row in missing:
                cols = list(row)
                cursor.execute('INSERT INTO library_words (' + ','.join(f'"{c}"' for c in cols) +
                               ') VALUES (' + ','.join(['%s'] * len(cols)) + ')', [row[c] for c in cols])
                target_words[row["normalized_word"]] = row["id"]
            # These rows are either immutable evidence or static catalog data.
            # ON CONFLICT DO NOTHING makes retries safe without changing users.
            sync_tables = ["data_sources", "vocabulary_topics", "vocabulary_automated_topic_releases",
                           "vocabulary_topic_corrections", "vocabulary_topic_words"]
            # Attribution and word-release rows are immutable and already
            # present when this is a taxonomy-only sync. Avoid thousands of
            # needless serverless round-trips; include them only for new words.
            if missing:
                sync_tables[2:2] = ["vocabulary_automated_releases", "word_attributions"]
            unique_columns = {
                "data_sources": ("name",), "vocabulary_topics": ("slug",),
                "vocabulary_automated_releases": ("word_id", "rule_version"),
                "vocabulary_automated_topic_releases": ("word_id", "topic_id", "rule_version"),
                "vocabulary_topic_corrections": ("word_id", "old_topic_id", "new_topic_id", "rule_version"),
                "word_attributions": ("word_id", "field_name", "source_name", "source_record_id"),
                "vocabulary_topic_words": ("word_id", "topic_id", "sense_key"),
            }
            for table in sync_tables:
                key_cols = unique_columns[table]
                cursor.execute(f'SELECT ' + ','.join(f'"{c}"' for c in key_cols) + f' FROM "{table}"')
                existing_keys = {tuple(row) for row in cursor.fetchall()}
                for row in _rows(source, table):
                    if "word_id" in row and row["word_id"] not in local_by_id:
                        continue
                    if tuple(row[col] for col in key_cols) in existing_keys:
                        continue
                    cols = list(row)
                    cursor.execute(f'INSERT INTO "{table}" (' + ','.join(f'"{c}"' for c in cols) +
                                   ') VALUES (' + ','.join(['%s'] * len(cols)) + ') ON CONFLICT DO NOTHING',
                                   [row[c] for c in cols])
            # Synchronize only explicitly evidenced automated withdrawals of
            # legacy topic labels. No user-owned table is updated.
            for row in _rows(source, "vocabulary_topic_corrections"):
                cursor.execute("""UPDATE vocabulary_topic_words SET published=0,review_status='rejected',rationale=%s
                  WHERE word_id=%s AND topic_id=%s AND source_key='library_words.topic' AND published=1""",
                  (row["rationale"], row["word_id"], row["old_topic_id"]))
                cursor.execute("""UPDATE library_words SET topic=(SELECT name_en FROM vocabulary_topics WHERE id=%s)
                  WHERE id=%s AND topic=(SELECT name_en FROM vocabulary_topics WHERE id=%s)""",
                  (row["new_topic_id"], row["word_id"], row["old_topic_id"]))
            cursor.execute("SELECT setval(pg_get_serial_sequence('library_words','id'),(SELECT MAX(id) FROM library_words))")
            cursor.execute("SELECT COUNT(*),COUNT(DISTINCT normalized_word) FROM library_words WHERE reviewed=1")
            total, unique = cursor.fetchone()
            if total != source_count or unique != total:
                raise RuntimeError(f"Post-sync vocabulary mismatch: total={total}, unique={unique}, expected={source_count}")
            cursor.execute("SELECT COUNT(*) FROM grammar_lessons WHERE published=1")
            lessons = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM grammar_exercises WHERE published=1")
            exercises = cursor.fetchone()[0]
            if (lessons, exercises) != (100, 1000):
                raise RuntimeError(f"Grammar preservation check failed: {lessons}/{exercises}")
            result.update({"writes": True, "backup": str(backup_path.resolve()),
                           "target_published_after": total, "unique_normalized_after": unique,
                           "grammar_lessons": lessons, "grammar_exercises": exercises})
        target.commit()
    source.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "speakseed.db")
    parser.add_argument("--target-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-host", default="")
    parser.add_argument("--confirm-database", default="")
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "qa_artifacts")
    args = parser.parse_args()
    url = args.target_url or os.getenv("DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL to the authorized Neon PostgreSQL connection URL")
    print(json.dumps(sync(args.source, url, args.apply, args.confirm_host,
                          args.confirm_database, args.backup_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
