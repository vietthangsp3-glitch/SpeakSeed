"""Compare every SpeakSeed SQLite table with a PostgreSQL migration target."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import psycopg

from migrate_to_postgres import (
    MINIMUM_SCHEMA_VERSION,
    REQUIRED_PUBLISHED_CONTENT,
    REQUIRED_TABLE_COUNT,
    inspect,
    qi,
    validate_release_source,
)


def normalize(value):
    if isinstance(value, memoryview): return bytes(value).hex()
    if isinstance(value, bytes): return value.hex()
    return value


def digest_rows(rows) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps([normalize(value) for value in row], ensure_ascii=False,
                                 separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify(source: Path, target_url: str) -> dict:
    plan = inspect(source)
    validate_release_source(plan)
    sqlite_con = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    failures = []
    with psycopg.connect(target_url) as pg:
        with pg.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            pg_tables = {row[0] for row in cursor.fetchall()}
            expected_tables = {table["name"] for table in plan["tables"]}
            if pg_tables != expected_tables: failures.append({"table_set": {"expected": sorted(expected_tables), "actual": sorted(pg_tables)}})
            table_results = []
            for table in plan["tables"]:
                name = table["name"]; columns = [column["name"] for column in table["columns"]]
                primary = [column["name"] for column in sorted(table["columns"], key=lambda item: item["pk"]) if column["pk"]]
                order = primary or columns
                sqlite_rows = sqlite_con.execute(f'SELECT * FROM {qi(name)} ORDER BY ' + ",".join(qi(x) for x in order)).fetchall()
                cursor.execute(f'SELECT * FROM {qi(name)} ORDER BY ' + ",".join(qi(x) for x in order))
                pg_rows = cursor.fetchall()
                source_digest = digest_rows(sqlite_rows); target_digest = digest_rows(pg_rows)
                ok = len(sqlite_rows) == len(pg_rows) and source_digest == target_digest
                table_results.append({"table": name, "rows": len(sqlite_rows), "digest_match": ok})
                if not ok: failures.append({"table": name, "source_rows": len(sqlite_rows), "target_rows": len(pg_rows),
                                             "source_digest": source_digest, "target_digest": target_digest})
            cursor.execute("""SELECT COUNT(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
                WHERE n.nspname='public' AND c.contype='f' AND c.convalidated""")
            pg_foreign_keys = cursor.fetchone()[0]
            planned_foreign_keys = sum(len({item["id"] for item in table["foreign_keys"]}) for table in plan["tables"])
            if pg_foreign_keys != planned_foreign_keys:
                failures.append({"foreign_keys": {"expected": planned_foreign_keys, "actual": pg_foreign_keys}})
            cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            pg_indexes = {row[0] for row in cursor.fetchall()}
            expected_indexes = set()
            for table in plan["tables"]:
                for index in table["indexes"]:
                    expected_indexes.add(index["name"] if not index["name"].startswith("sqlite_autoindex")
                                         else f'uq_{table["name"]}_' + "_".join(index["columns"]))
            missing_indexes = sorted(expected_indexes - pg_indexes)
            if missing_indexes: failures.append({"missing_indexes": missing_indexes})
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
            latest_schema = cursor.fetchone()
            target_content = {}
            for key, query in {
                "published_words": "SELECT COUNT(*) FROM library_words WHERE reviewed=1",
                "published_grammar_lessons": "SELECT COUNT(*) FROM grammar_lessons WHERE published=1",
                "published_grammar_exercises": "SELECT COUNT(*) FROM grammar_exercises WHERE published=1",
            }.items():
                cursor.execute(query); target_content[key] = cursor.fetchone()[0]
            if len(pg_tables) < REQUIRED_TABLE_COUNT:
                failures.append({"table_count": {"minimum": REQUIRED_TABLE_COUNT, "actual": len(pg_tables)}})
            if not latest_schema or latest_schema[0] < MINIMUM_SCHEMA_VERSION:
                failures.append({"schema_version": {"minimum": MINIMUM_SCHEMA_VERSION,
                                                     "actual": latest_schema[0] if latest_schema else None}})
            if target_content != REQUIRED_PUBLISHED_CONTENT:
                failures.append({"published_content": {"expected": REQUIRED_PUBLISHED_CONTENT,
                                                        "actual": target_content}})
    sqlite_con.close()
    return {"ok": not failures, "tables": len(plan["tables"]), "rows": plan["total_rows"],
            "foreign_keys": planned_foreign_keys, "expected_indexes": len(expected_indexes),
            "latest_schema_version": latest_schema[0] if latest_schema else None,
            "published_content": target_content,
            "table_results": table_results, "failures": failures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-url", help="Defaults to DATABASE_URL"); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); target_url=args.target_url or os.getenv("DATABASE_URL", "").strip()
    if not target_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Set DATABASE_URL or pass a valid PostgreSQL --target-url")
    result = verify(args.source, target_url)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text, encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "ok", "tables", "rows", "foreign_keys", "expected_indexes",
        "latest_schema_version", "published_content"
    )}, ensure_ascii=True))
    if not result["ok"]: raise SystemExit(1)
