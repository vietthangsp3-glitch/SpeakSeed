"""Create and verify a complete portable PostgreSQL data backup.

The ZIP contains one CSV per public table plus a manifest with row counts and
SHA-256 hashes. Restore is intentionally limited to an empty, initialized target
and requires exact host/database confirmation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def qi(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def verify(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for table in manifest["tables"]:
            payload = archive.read(table["file"])
            if hashlib.sha256(payload).hexdigest() != table["sha256"]:
                raise RuntimeError(f"Hash mismatch: {table['name']}")
            rows = sum(1 for _ in csv.reader(io.StringIO(payload.decode("utf-8")))) - 1
            if rows != table["rows"]:
                raise RuntimeError(f"Row count mismatch: {table['name']}")
    return {"status": "verified", "archive": str(path.resolve()),
            "tables": len(manifest["tables"]),
            "rows": sum(item["rows"] for item in manifest["tables"]),
            "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "target": manifest["target"]}


def backup(url: str, output: Path) -> dict:
    import psycopg
    output.parent.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(url) as con, con.cursor() as cur:
        cur.execute("SELECT current_database(),current_user")
        database, user = cur.fetchone()
        cur.execute("""SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name""")
        names = [row[0] for row in cur.fetchall()]
        tables = []
        payloads = {}
        for name in names:
            chunks = []
            with cur.copy(f"COPY {qi(name)} TO STDOUT WITH (FORMAT CSV, HEADER TRUE)") as copy:
                for chunk in copy:
                    chunks.append(bytes(chunk))
            payload = b"".join(chunks)
            rows = sum(1 for _ in csv.reader(io.StringIO(payload.decode("utf-8")))) - 1
            filename = f"tables/{name}.csv"
            payloads[filename] = payload
            tables.append({"name": name, "file": filename, "rows": rows,
                           "sha256": hashlib.sha256(payload).hexdigest()})
        manifest = {"format": "speakseed-postgres-csv-v1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "target": {"host": urlparse(url).hostname, "database": database, "user": user},
                    "tables": tables}
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for filename, payload in payloads.items():
                archive.writestr(filename, payload)
    return verify(output)


def restore(url: str, archive_path: Path, confirm_host: str, confirm_database: str) -> dict:
    import psycopg
    parsed = urlparse(url)
    checked = verify(archive_path)
    with zipfile.ZipFile(archive_path) as archive, psycopg.connect(url) as con, con.cursor() as cur:
        cur.execute("SELECT current_database()")
        database = cur.fetchone()[0]
        if parsed.hostname != confirm_host or database != confirm_database:
            raise RuntimeError("Exact --confirm-host and --confirm-database are required")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["target"]["database"] != database:
            raise RuntimeError("Backup database identity does not match restore target")
        for table in manifest["tables"]:
            cur.execute(f"SELECT COUNT(*) FROM {qi(table['name'])}")
            if cur.fetchone()[0] != 0:
                raise RuntimeError("Restore target must have empty public tables")
        cur.execute("SET LOCAL session_replication_role=replica")
        for table in manifest["tables"]:
            payload = archive.read(table["file"])
            with cur.copy(f"COPY {qi(table['name'])} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
                copy.write(payload)
        cur.execute("SET LOCAL session_replication_role=origin")
        for table in manifest["tables"]:
            cur.execute("SELECT pg_get_serial_sequence(%s,'id')", (table["name"],))
            sequence = cur.fetchone()[0]
            if sequence:
                cur.execute(f"SELECT setval(%s,COALESCE((SELECT MAX(id) FROM {qi(table['name'])}),1),true)", (sequence,))
        con.commit()
    return {**checked, "status": "restored"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "verify", "restore"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target-url")
    parser.add_argument("--confirm-host", default="")
    parser.add_argument("--confirm-database", default="")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify(args.archive)
    else:
        url = args.target_url or os.getenv("DATABASE_URL", "").strip()
        if not url.startswith(("postgresql://", "postgres://")):
            raise SystemExit("Set DATABASE_URL to the authorized PostgreSQL target")
        result = backup(url, args.archive) if args.command == "backup" else restore(
            url, args.archive, args.confirm_host, args.confirm_database)
    # Windows consoles may use a legacy code page; ASCII-safe JSON keeps a
    # successful backup from being reported as failed solely because its path
    # contains Vietnamese characters.
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
