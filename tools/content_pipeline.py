"""Offline, license-gated staging importer for SpeakSeed content.

This command never publishes learning content and never connects to PostgreSQL.
It is deliberately limited to a local SQLite path.  Production publication is a
separate, human-authorized step that is not implemented here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import tarfile
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations import run_migrations


IMPORTER_VERSION = "2.0.0"
LEVELS = {"A0", "A1", "A2", "B1", "B2"}
WORD_PATTERN = re.compile(r"[a-z]+(?:['-][a-z]+)*(?: [a-z]+(?:['-][a-z]+)*){0,4}")


class PipelineError(RuntimeError):
    pass


class PipelineInterrupted(PipelineError):
    """Controlled interruption used to verify checkpoint/resume behavior."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalized_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_word(value: object) -> str:
    return " ".join(str(value or "").casefold().replace("’", "'").split())


def load_registry(path: Path) -> dict[str, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    sources = document.get("sources")
    if not isinstance(sources, dict):
        raise PipelineError("Source registry must contain an object named 'sources'")
    required = {
        "display_name", "owner_name", "source_url", "dataset_version",
        "license_name", "license_url", "commercial_use", "attribution",
        "obligations", "audit_status", "evidence_url", "audited_at", "notes",
    }
    for key, source in sources.items():
        missing = sorted(required - set(source))
        if missing:
            raise PipelineError(f"Source {key!r} is missing registry fields: {', '.join(missing)}")
    return sources


def license_gate(source_key: str, source: dict, accept_conditions: bool) -> None:
    status = source["audit_status"]
    if status == "rejected" or source["commercial_use"] in {"prohibited", "unverified"}:
        raise PipelineError(f"Source {source_key!r} is blocked by the license audit")
    if status == "conditional" and not accept_conditions:
        raise PipelineError(
            f"Source {source_key!r} is conditional; inspect DATA_SOURCE_AUDIT.md and pass "
            "--accept-conditions to stage (this never authorizes publication)"
        )


def find_value(row: dict, *names: str) -> str:
    lowered = {str(key).strip().casefold(): str(value or "").strip() for key, value in row.items()}
    return next((lowered[name.casefold()] for name in names if lowered.get(name.casefold())), "")


def iter_cefr_j(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            word = normalize_word(find_value(row, "headword", "word", "lemma"))
            pos = find_value(row, "pos", "part of speech").casefold()
            level = find_value(row, "CEFR", "CEFR-J level", "level").upper()
            payload = {
                "word": word,
                "lemma": word,
                "pos": pos,
                "cefr_level": level,
                "cefr_method": "CEFR-J Vocabulary Profile 1.5",
            }
            errors = []
            if not word or not WORD_PATTERN.fullmatch(word):
                errors.append("invalid_headword")
            if not pos:
                errors.append("missing_pos")
            if level not in LEVELS - {"A0"}:
                errors.append("invalid_cefr_level")
            yield {
                "content_type": "vocabulary",
                "source_record_id": f"line:{line_number}",
                "stable_key": f"{word}|{pos}",
                "payload": payload,
                "errors": errors,
                "quality_status": "automated_checked" if not errors else "unverified",
            }


def iter_elispeak(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                yield {
                    "content_type": "question", "source_record_id": f"line:{line_number}",
                    "stable_key": f"invalid:{line_number}", "payload": {},
                    "errors": ["invalid_json"], "quality_status": "unverified",
                }
                continue
            source_id = str(row.get("id") or f"line:{line_number}").strip()
            level = str(row.get("cefr") or "").upper().strip()
            learner = str(row.get("learner_sentence") or "").strip()
            corrected = str(row.get("corrected_sentence") or "").strip()
            explanation = str(row.get("explanation") or "").strip()
            prompt = str(row.get("practice_prompt") or "").strip()
            payload = {
                "stable_id": source_id,
                "question_type": "error_correction",
                "cefr_level": level,
                "skill": "grammar",
                "topic": str(row.get("category") or "Common mistakes").strip(),
                "prompt": learner,
                "answer_key": [corrected] if corrected else [],
                "accepted_answers": [corrected] if corrected else [],
                "explanation_en": explanation,
                "explanation_vi": "",
                "practice_prompt": prompt,
                "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
            }
            errors = []
            for field in ("stable_id", "prompt", "explanation_en"):
                if not payload[field]:
                    errors.append(f"missing_{field}")
            if not payload["answer_key"]:
                errors.append("missing_answer")
            if level not in LEVELS:
                errors.append("invalid_cefr_level")
            # English-only explanations are valid staging data, but cannot be published.
            yield {
                "content_type": "question", "source_record_id": source_id,
                "stable_key": source_id.casefold(), "payload": payload, "errors": errors,
                "quality_status": "needs_review" if not errors else "unverified",
            }


def iter_tatoeba(path: Path) -> Iterator[dict]:
    """Read the ManyThings Vietnamese-English selection line by line.

    The third TSV field carries the license and both Tatoeba attributions in
    the audited local snapshot. Records without that evidence are rejected.
    """
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            parts = raw.rstrip("\r\n").split("\t")
            english = parts[0].strip() if parts else ""
            vietnamese = parts[1].strip() if len(parts) > 1 else ""
            attribution = parts[2].strip() if len(parts) > 2 else ""
            ids = re.findall(r"#(\d+)", attribution)
            source_id = "-".join(ids) if ids else f"line:{line_number}"
            payload = {
                "english": english,
                "vietnamese": vietnamese,
                "cefr_level": "unverified",
                "attribution": attribution,
                "license": "CC BY 2.0 FR",
                "source_sentence_ids": ids,
            }
            errors = []
            if not english:
                errors.append("missing_english")
            if not vietnamese:
                errors.append("missing_vietnamese")
            if len(english) > 350 or len(vietnamese) > 450:
                errors.append("sentence_too_long")
            if not attribution.casefold().startswith("cc-by 2.0 (france)"):
                errors.append("unverified_license")
            if len(ids) < 2:
                errors.append("missing_attribution_ids")
            stable = hashlib.sha256(
                (" ".join(english.casefold().split()) + "\0" + " ".join(vietnamese.casefold().split())).encode("utf-8")
            ).hexdigest()
            yield {
                "content_type": "sentence", "source_record_id": source_id,
                "stable_key": stable, "payload": payload, "errors": errors,
                "quality_status": "needs_review" if not errors else "unverified",
            }


def iter_wordnet(path: Path) -> Iterator[dict]:
    """Stream WordNet 3.0 synsets directly from the official tarball."""
    pos_names = {"noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb"}
    with tarfile.open(path, "r:*") as archive:
        members = {member.name.rsplit("/", 1)[-1]: member for member in archive.getmembers()}
        for filename, pos in pos_names.items():
            member = members.get(f"data.{filename}")
            if member is None:
                raise PipelineError(f"WordNet archive is missing dict/data.{filename}")
            handle = archive.extractfile(member)
            if handle is None:
                raise PipelineError(f"Cannot read WordNet member {member.name}")
            for raw in handle:
                line = raw.decode("utf-8", errors="replace")
                if not line or line[0].isspace() or " | " not in line:
                    continue
                metadata, gloss = line.rstrip("\r\n").split(" | ", 1)
                parts = metadata.split()
                errors: list[str] = []
                try:
                    offset = parts[0]
                    word_count = int(parts[3], 16)
                    lemmas = [normalize_word(parts[4 + index * 2].replace("_", " ")) for index in range(word_count)]
                except (IndexError, ValueError):
                    yield {
                        "content_type": "vocabulary", "source_record_id": f"{filename}:invalid",
                        "stable_key": hashlib.sha256(line.encode()).hexdigest(), "payload": {},
                        "errors": ["invalid_wordnet_record"], "quality_status": "unverified",
                    }
                    continue
                quoted_examples = re.findall(r'"([^\"]+)"', gloss)
                definition = gloss.split(";", 1)[0].strip()
                for lemma in lemmas:
                    if not lemma or not WORD_PATTERN.fullmatch(lemma):
                        errors = ["invalid_headword"]
                    else:
                        errors = []
                    payload = {
                        "word": lemma, "lemma": lemma, "pos": pos,
                        "definition_en": definition,
                        "synonyms": [item for item in lemmas if item != lemma],
                        "examples_en": quoted_examples,
                    }
                    yield {
                        "content_type": "vocabulary",
                        "source_record_id": f"{filename}:{offset}:{lemma}",
                        "stable_key": f"{lemma}|{pos}|{offset}", "payload": payload,
                        "errors": errors,
                        "quality_status": "automated_checked" if not errors else "unverified",
                    }


ADAPTERS = {
    "cefr-j-1.5": iter_cefr_j,
    "elispeak-common-mistakes": iter_elispeak,
    "tatoeba-text": iter_tatoeba,
    "princeton-wordnet-3.0": iter_wordnet,
}


def source_records(path: Path, source_key: str) -> Iterator[dict]:
    adapter = ADAPTERS.get(source_key)
    if adapter is None:
        raise PipelineError(
            f"No parser is implemented for {source_key!r}; the source is audited but cannot be imported yet"
        )
    yield from adapter(path)


def scan(path: Path, source_key: str, *, limit: int) -> tuple[list[dict], dict]:
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seen_source_ids: set[tuple[str, str]] = set()
    reasons: Counter[str] = Counter()
    processed = valid = rejected = duplicates = 0
    for record in source_records(path, source_key):
        if processed >= limit:
            break
        processed += 1
        dedupe_key = (record["content_type"], record["stable_key"])
        if dedupe_key in seen:
            record["errors"] = sorted(set(record["errors"] + ["duplicate_stable_key"]))
            record["stable_key"] += f"|duplicate:{processed}"
            duplicates += 1
        seen.add(dedupe_key)
        source_id_key = (record["content_type"], record["source_record_id"])
        if source_id_key in seen_source_ids:
            record["errors"] = sorted(set(record["errors"] + ["duplicate_source_record_id"]))
            record["source_record_id"] += f"|duplicate:{processed}"
        seen_source_ids.add(source_id_key)
        if record["errors"]:
            rejected += 1
            reasons.update(record["errors"])
        else:
            valid += 1
        records.append(record)
    return records, {
        "source": source_key,
        "input": str(path.resolve()),
        "processed": processed,
        "valid": valid,
        "rejected": rejected,
        "duplicates": duplicates,
        "rejection_reasons": dict(sorted(reasons.items())),
        "publishes_content": False,
        "human_reviewed": 0,
    }


def dry_run_stream(path: Path, source_key: str, *, limit: int) -> dict:
    """Validate without retaining dataset payloads in memory or app DB."""
    reasons: Counter[str] = Counter()
    processed = valid = rejected = duplicates = 0
    with tempfile.TemporaryDirectory(prefix="speakseed-content-") as directory:
        scratch = sqlite3.connect(Path(directory) / "dedupe.db")
        scratch.executescript("""
          CREATE TABLE seen_stable(content_type TEXT,stable_key TEXT,PRIMARY KEY(content_type,stable_key));
          CREATE TABLE seen_source(content_type TEXT,source_record_id TEXT,PRIMARY KEY(content_type,source_record_id));
        """)
        for record in source_records(path, source_key):
            if processed >= limit:
                break
            processed += 1
            errors = list(record["errors"])
            try:
                scratch.execute("INSERT INTO seen_stable VALUES(?,?)", (record["content_type"], record["stable_key"]))
            except sqlite3.IntegrityError:
                errors.append("duplicate_stable_key"); duplicates += 1
            try:
                scratch.execute("INSERT INTO seen_source VALUES(?,?)", (record["content_type"], record["source_record_id"]))
            except sqlite3.IntegrityError:
                errors.append("duplicate_source_record_id")
            errors = sorted(set(errors))
            if errors:
                rejected += 1; reasons.update(errors)
            else:
                valid += 1
        scratch.close()
    return {
        "source": source_key, "input": str(path.resolve()), "processed": processed,
        "valid": valid, "rejected": rejected, "duplicates": duplicates,
        "rejection_reasons": dict(sorted(reasons.items())),
        "publishes_content": False, "human_reviewed": 0,
    }


def upsert_source(con: sqlite3.Connection, key: str, source: dict) -> None:
    columns = (
        "display_name", "owner_name", "source_url", "dataset_version", "license_name",
        "license_url", "commercial_use", "attribution", "obligations", "audit_status",
        "evidence_url", "audited_at", "notes",
    )
    values = [source[column] for column in columns]
    updates = ",".join(f"{column}=excluded.{column}" for column in columns)
    con.execute(
        f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(len(columns)+1))}) "
        f"ON CONFLICT(source_key) DO UPDATE SET {updates}",
        [key, *values],
    )


def _batch_report(con: sqlite3.Connection, batch_id: int, path: Path, source_hash: str,
                  *, reused: bool = False, interrupted: bool = False) -> dict:
    row = con.execute(
        """SELECT source_key,status,checkpoint,processed,accepted,rejected,report_json
           FROM content_import_batches WHERE id=?""", (batch_id,)
    ).fetchone()
    reasons = dict(con.execute(
        """SELECT reason,COUNT(*) FROM content_import_rejections
           WHERE batch_id=? GROUP BY reason ORDER BY reason""", (batch_id,)
    ).fetchall())
    return {
        "source": row[0], "input": str(path.resolve()), "source_sha256": source_hash,
        "batch_id": batch_id, "status": row[1], "checkpoint": int(row[2] or 0),
        "processed": row[3], "valid": row[4], "rejected": row[5],
        "rejection_reasons": reasons, "idempotent_reuse": reused,
        "interrupted": interrupted, "publishes_content": False, "human_reviewed": 0,
    }


def stage_streaming(database: Path, migrations: Path, source_key: str, source: dict,
                    path: Path, *, limit: int, batch_size: int, resume: bool,
                    stop_after: int = 0) -> dict:
    """Stage input in bounded transactions and persist a source-row checkpoint.

    Checkpoint, counters and staged rows are committed atomically after each
    chunk. Resume deterministically replays the source and skips rows through
    that checkpoint, so no file seek assumptions are needed for CSV/JSONL/TSV.
    """
    if batch_size < 1:
        raise PipelineError("batch_size must be positive")
    run_migrations(database, migrations)
    source_hash = file_sha256(path)
    con = sqlite3.connect(database, timeout=30)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    try:
        con.execute("BEGIN IMMEDIATE")
        upsert_source(con, source_key, source)
        row = con.execute(
            """SELECT id,status,checkpoint FROM content_import_batches
               WHERE source_key=? AND source_version=? AND source_sha256=? AND importer_version=?""",
            (source_key, source["dataset_version"], source_hash, IMPORTER_VERSION),
        ).fetchone()
        if row and row[1] == "staged":
            con.rollback()
            return _batch_report(con, row[0], path, source_hash, reused=True)
        if row and row[1] in {"running", "failed"} and not resume:
            con.rollback()
            raise PipelineError(
                f"Batch {row[0]} is {row[1]} at checkpoint {row[2]}; rerun with --resume"
            )
        if row and row[1] == "rolled_back":
            con.execute(
                """UPDATE content_import_batches SET status='running',started_at=?,finished_at=NULL,
                   checkpoint='',processed=0,accepted=0,rejected=0,report_json='{}' WHERE id=?""",
                (now(), row[0]),
            )
            batch_id, checkpoint = row[0], 0
        elif row:
            batch_id, checkpoint = row[0], int(row[2] or 0)
            con.execute("UPDATE content_import_batches SET status='running',finished_at=NULL WHERE id=?", (batch_id,))
        else:
            batch_id = con.execute(
                """INSERT INTO content_import_batches(
                   source_key,source_version,source_sha256,importer_version,status,started_at)
                   VALUES(?,?,?,?,'running',?)""",
                (source_key, source["dataset_version"], source_hash, IMPORTER_VERSION, now()),
            ).lastrowid
            checkpoint = 0
        con.commit()

        chunk_processed = chunk_valid = chunk_rejected = processed_this_run = 0
        for ordinal, record in enumerate(source_records(path, source_key), 1):
            if ordinal <= checkpoint:
                continue
            if ordinal > limit:
                break
            errors = list(record["errors"])
            collision = con.execute(
                """SELECT CASE WHEN stable_key=? THEN 'duplicate_stable_key'
                          ELSE 'duplicate_source_record_id' END
                   FROM content_staging_records
                   WHERE batch_id=? AND content_type=? AND (stable_key=? OR source_record_id=?)
                   LIMIT 1""",
                (record["stable_key"], batch_id, record["content_type"],
                 record["stable_key"], record["source_record_id"]),
            ).fetchone()
            if collision:
                errors.append(collision[0])
                con.execute(
                    """INSERT OR IGNORE INTO content_import_rejections(
                       batch_id,source_record_id,content_type,reason,payload_hash,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (batch_id, record["source_record_id"], record["content_type"], collision[0],
                     normalized_hash(record["payload"]), now()),
                )
            else:
                con.execute(
                    """INSERT INTO content_staging_records(
                       batch_id,content_type,source_record_id,stable_key,normalized_hash,payload_json,
                       validation_status,validation_errors_json,quality_status,review_status,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,'pending',?)""",
                    (batch_id, record["content_type"], record["source_record_id"], record["stable_key"],
                     normalized_hash(record["payload"]), canonical_json(record["payload"]),
                     "rejected" if errors else "valid", canonical_json(sorted(set(errors))),
                     record["quality_status"], now()),
                )
                for reason in sorted(set(errors)):
                    con.execute(
                        """INSERT OR IGNORE INTO content_import_rejections(
                           batch_id,source_record_id,content_type,reason,payload_hash,created_at)
                           VALUES(?,?,?,?,?,?)""",
                        (batch_id, record["source_record_id"], record["content_type"], reason,
                         normalized_hash(record["payload"]), now()),
                    )
            checkpoint = ordinal
            chunk_processed += 1; processed_this_run += 1
            if errors:
                chunk_rejected += 1
            else:
                chunk_valid += 1
            should_commit = chunk_processed >= batch_size or (stop_after and processed_this_run >= stop_after)
            if should_commit:
                con.execute(
                    """UPDATE content_import_batches SET checkpoint=?,processed=processed+?,
                       accepted=accepted+?,rejected=rejected+? WHERE id=?""",
                    (str(checkpoint), chunk_processed, chunk_valid, chunk_rejected, batch_id),
                )
                con.commit()
                chunk_processed = chunk_valid = chunk_rejected = 0
            if stop_after and processed_this_run >= stop_after:
                return _batch_report(con, batch_id, path, source_hash, interrupted=True)

        if chunk_processed:
            con.execute(
                """UPDATE content_import_batches SET checkpoint=?,processed=processed+?,
                   accepted=accepted+?,rejected=rejected+? WHERE id=?""",
                (str(checkpoint), chunk_processed, chunk_valid, chunk_rejected, batch_id),
            )
        con.execute("UPDATE content_import_batches SET status='staged',finished_at=? WHERE id=?", (now(), batch_id))
        report = _batch_report(con, batch_id, path, source_hash)
        report["status"] = "staged"
        con.execute("UPDATE content_import_batches SET report_json=? WHERE id=?", (canonical_json(report), batch_id))
        con.commit()
        return report
    except Exception as exc:
        con.rollback()
        if 'batch_id' in locals():
            con.execute("UPDATE content_import_batches SET status='failed',finished_at=? WHERE id=?", (now(), batch_id))
            con.commit()
        raise
    finally:
        con.close()


def stage_records(database: Path, migrations: Path, source_key: str, source: dict,
                  source_hash: str, records: Iterable[dict], report: dict,
                  *, rollback_on_error: bool = True) -> dict:
    run_migrations(database, migrations)
    con = sqlite3.connect(database, timeout=30)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        upsert_source(con, source_key, source)
        existing = con.execute(
            """SELECT id,status,processed,accepted,rejected FROM content_import_batches
               WHERE source_key=? AND source_version=? AND source_sha256=? AND importer_version=?""",
            (source_key, source["dataset_version"], source_hash, IMPORTER_VERSION),
        ).fetchone()
        if existing and existing[1] == "staged":
            con.rollback()
            return {**report, "batch_id": existing[0], "idempotent_reuse": True,
                    "staged": existing[2], "accepted": existing[3], "rejected": existing[4]}
        if existing:
            batch_id = existing[0]
            con.execute("DELETE FROM content_staging_records WHERE batch_id=?", (batch_id,))
            con.execute(
                """UPDATE content_import_batches SET status='running',started_at=?,finished_at=NULL,
                   checkpoint='',processed=0,accepted=0,rejected=0,report_json='{}' WHERE id=?""",
                (now(), batch_id),
            )
        else:
            batch_id = con.execute(
                """INSERT INTO content_import_batches(
                   source_key,source_version,source_sha256,importer_version,status,started_at)
                   VALUES(?,?,?,?,'running',?)""",
                (source_key, source["dataset_version"], source_hash, IMPORTER_VERSION, now()),
            ).lastrowid
        created_at = now()
        for index, record in enumerate(records, 1):
            errors = record["errors"]
            con.execute(
                """INSERT INTO content_staging_records(
                   batch_id,content_type,source_record_id,stable_key,normalized_hash,payload_json,
                   validation_status,validation_errors_json,quality_status,review_status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,'pending',?)""",
                (batch_id, record["content_type"], record["source_record_id"], record["stable_key"],
                 normalized_hash(record["payload"]), canonical_json(record["payload"]),
                 "rejected" if errors else "valid", canonical_json(errors),
                 record["quality_status"], created_at),
            )
        final_report = {**report, "batch_id": batch_id, "idempotent_reuse": False,
                        "staged": report["processed"]}
        con.execute(
            """UPDATE content_import_batches SET status='staged',finished_at=?,checkpoint=?,
               processed=?,accepted=?,rejected=?,report_json=? WHERE id=?""",
            (now(), str(report["processed"]), report["processed"], report["valid"],
             report["rejected"], canonical_json(final_report), batch_id),
        )
        con.commit()
        return final_report
    except Exception:
        if rollback_on_error:
            con.rollback()
        raise
    finally:
        con.close()


def rollback_batch(database: Path, batch_id: int) -> dict:
    con = sqlite3.connect(database, timeout=30)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status,source_key FROM content_import_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not row:
            raise PipelineError(f"Unknown staging batch {batch_id}")
        if con.execute("SELECT COUNT(*) FROM question_bank_drafts WHERE staging_record_id IN (SELECT id FROM content_staging_records WHERE batch_id=?)", (batch_id,)).fetchone()[0]:
            raise PipelineError("Batch has linked question drafts; reject/review them before rollback")
        if con.execute("""SELECT COUNT(*) FROM word_enrichment_candidates
            WHERE review_status='human_reviewed' AND staging_record_id IN
            (SELECT id FROM content_staging_records WHERE batch_id=?)""", (batch_id,)).fetchone()[0]:
            raise PipelineError("Batch has human-reviewed enrichment; rollback requires explicit review reversal")
        removed = con.execute(
            "SELECT COUNT(*) FROM content_staging_records WHERE batch_id=?", (batch_id,)
        ).fetchone()[0]
        removed_enrichment = con.execute("""SELECT COUNT(*) FROM word_enrichment_values
            WHERE candidate_id IN (SELECT c.id FROM word_enrichment_candidates c
              JOIN content_staging_records r ON r.id=c.staging_record_id WHERE r.batch_id=?)""",
            (batch_id,)).fetchone()[0]
        con.execute("""DELETE FROM word_enrichment_values WHERE candidate_id IN
            (SELECT c.id FROM word_enrichment_candidates c JOIN content_staging_records r
             ON r.id=c.staging_record_id WHERE r.batch_id=?)""", (batch_id,))
        con.execute("""DELETE FROM word_enrichment_events WHERE candidate_id IN
            (SELECT c.id FROM word_enrichment_candidates c JOIN content_staging_records r
             ON r.id=c.staging_record_id WHERE r.batch_id=?)""", (batch_id,))
        con.execute("""DELETE FROM word_enrichment_candidates WHERE staging_record_id IN
            (SELECT id FROM content_staging_records WHERE batch_id=?)""", (batch_id,))
        con.execute("DELETE FROM content_staging_records WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM content_import_rejections WHERE batch_id=?", (batch_id,))
        con.execute("UPDATE content_import_batches SET status='rolled_back',finished_at=? WHERE id=?", (now(), batch_id))
        con.commit()
        return {"batch_id": batch_id, "source": row[1], "status": "rolled_back",
                "removed": removed, "removed_enrichment_values": removed_enrichment}
    finally:
        con.close()


def write_report(path: Path | None, report: dict) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    try:
        print(rendered)
    except UnicodeEncodeError:
        # Windows PowerShell may expose a legacy cp1252 stdout even though the
        # report file itself is UTF-8. Escaped JSON remains exact and readable.
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="License-gated offline SpeakSeed content pipeline")
    parser.add_argument("command", choices=("audit", "stage", "rollback"))
    parser.add_argument("--source")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--database", type=Path, default=ROOT / "speakseed.db")
    parser.add_argument("--migrations", type=Path, default=ROOT / "migrations")
    parser.add_argument("--registry", type=Path, default=ROOT / "data/source_registry.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--accept-conditions", action="store_true")
    parser.add_argument("--batch-id", type=int)
    args = parser.parse_args()
    try:
        sources = load_registry(args.registry)
        if args.command == "audit":
            write_report(args.report, {"sources": {key: {"audit_status": value["audit_status"],
                "commercial_use": value["commercial_use"], "license_name": value["license_name"],
                "evidence_url": value["evidence_url"]} for key, value in sorted(sources.items())}})
            return
        if args.command == "rollback":
            if not args.batch_id:
                parser.error("rollback requires --batch-id")
            write_report(args.report, rollback_batch(args.database, args.batch_id))
            return
        if not args.source or args.source not in sources:
            parser.error("stage requires a --source present in the registry")
        if not args.input or not args.input.is_file():
            parser.error("stage requires an existing --input file")
        if args.limit < 1:
            parser.error("--limit must be positive")
        source = sources[args.source]
        license_gate(args.source, source, args.accept_conditions)
        report = dry_run_stream(args.input, args.source, limit=args.limit)
        report.update({"mode": "dry-run" if args.dry_run else "stage",
                       "source_sha256": file_sha256(args.input),
                       "license_status": source["audit_status"]})
        if not args.dry_run:
            report = stage_streaming(
                args.database, args.migrations, args.source, source, args.input,
                limit=args.limit, batch_size=args.batch_size, resume=args.resume,
            )
            report.update({"mode": "stage", "license_status": source["audit_status"]})
        write_report(args.report, report)
    except PipelineError as exc:
        parser.exit(2, f"content-pipeline: {exc}\n")


if __name__ == "__main__":
    main()
