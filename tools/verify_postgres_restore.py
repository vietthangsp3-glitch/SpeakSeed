"""Compare a PostgreSQL database with a restored copy, without modifying either."""
from __future__ import annotations

import argparse
import hashlib
import json

import psycopg
from psycopg import sql


def inventory(dsn: str) -> dict:
    result = {"tables": {}, "foreign_keys": [], "indexes": []}
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            columns = [row[0] for row in cursor.fetchall()]
            cursor.execute(sql.SQL("SELECT {} FROM {}")
                           .format(sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table)))
            encoded = [json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":"))
                       for row in cursor.fetchall()]
            digest = hashlib.sha256("\n".join(sorted(encoded)).encode("utf-8")).hexdigest()
            result["tables"][table] = {"columns": columns, "rows": len(encoded), "sha256": digest}
        cursor.execute("""
            SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name=ccu.constraint_name AND tc.constraint_schema=ccu.constraint_schema
            WHERE tc.constraint_schema='public' AND tc.constraint_type='FOREIGN KEY'
            ORDER BY 1,2,3,4
        """)
        result["foreign_keys"] = cursor.fetchall()
        cursor.execute("""
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname='public' ORDER BY tablename,indexname
        """)
        result["indexes"] = cursor.fetchall()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--restored", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    source = inventory(args.source)
    restored = inventory(args.restored)
    report = {
        "ok": source == restored,
        "tables": len(source["tables"]),
        "rows": sum(item["rows"] for item in source["tables"].values()),
        "foreign_keys": len(source["foreign_keys"]),
        "indexes": len(source["indexes"]),
        "source_equals_restored": source == restored,
    }
    if not report["ok"]:
        report["source"] = source
        report["restored"] = restored
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
