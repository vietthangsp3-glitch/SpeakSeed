"""Verified, online-safe SQLite backup and restore for SpeakSeed.

Restore writes to a new file by default. The source database is never removed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(con: sqlite3.Connection) -> dict[str, int]:
    names = [row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    return {name: con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def validate(con: sqlite3.Connection) -> dict[str, int]:
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity_check thất bại: {integrity}")
    foreign_keys = con.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        raise RuntimeError(f"Phát hiện {len(foreign_keys)} lỗi foreign key")
    return snapshot(con)


def backup(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(f"Không ghi đè backup hiện có: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(destination, timeout=30)
    try:
        expected = validate(src)
        src.backup(dst)
        actual = validate(dst)
        if actual != expected:
            raise RuntimeError("Số bản ghi của backup không khớp nguồn")
    finally:
        dst.close(); src.close()
    manifest = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest.write_text(json.dumps({
        "format": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_name": source.name,
        "backup_name": destination.name,
        "sha256": sha256(destination),
        "table_counts": actual,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def restore(backup_path: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Đích đã tồn tại; không ghi đè: {destination}")
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(backup_path) != manifest["sha256"]:
        raise RuntimeError("Checksum backup không hợp lệ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{backup_path.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(destination, timeout=30)
    try:
        src.backup(dst)
        counts = validate(dst)
        if counts != manifest["table_counts"]:
            raise RuntimeError("Restore không khớp manifest")
    except Exception:
        dst.close()
        destination.unlink(missing_ok=True)
        raise
    finally:
        try: dst.close()
        except Exception: pass
        src.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup/restore SQLite có checksum và kiểm tra dữ liệu")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create"); create.add_argument("source", type=Path); create.add_argument("destination", type=Path)
    recover = sub.add_parser("restore"); recover.add_argument("backup", type=Path); recover.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        manifest = backup(args.source, args.destination)
        print(json.dumps({"backup": str(args.destination), "manifest": str(manifest)}, ensure_ascii=True))
    else:
        restore(args.backup, args.destination)
        print(json.dumps({"restored": str(args.destination)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
