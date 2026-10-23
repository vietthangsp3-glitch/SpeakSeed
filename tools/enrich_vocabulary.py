"""Create source-backed, field-level enrichment values without changing word IDs."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def enrich(database: Path) -> dict:
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    created = applied = skipped_existing = 0
    words: set[int] = set()
    try:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute(
            """SELECT r.id staging_id,b.source_key,r.source_record_id,r.payload_json,
                      s.audit_status,s.commercial_use
               FROM content_staging_records r
               JOIN content_import_batches b ON b.id=r.batch_id
               JOIN content_sources s ON s.source_key=b.source_key
               WHERE r.validation_status='valid' AND b.status='staged'
                 AND b.source_key IN ('cefr-j-1.5','princeton-wordnet-3.0')
               ORDER BY r.id"""
        )
        for row in rows:
            payload = json.loads(row["payload_json"])
            lemma = " ".join(str(payload.get("lemma") or payload.get("word") or "").casefold().split())
            word = con.execute(
                "SELECT id,stage,pos FROM library_words WHERE normalized_word=? ORDER BY reviewed DESC,id LIMIT 1",
                (lemma,),
            ).fetchone()
            if not word:
                continue
            candidates: list[tuple[str, object, int]] = []
            if row["source_key"] == "cefr-j-1.5":
                candidates.extend((field, payload[key], 100) for field, key in (("cefr", "cefr_level"), ("pos", "pos")) if payload.get(key))
            else:
                if payload.get("definition_en"):
                    candidates.append(("definition_en", payload["definition_en"], 95))
                candidates.extend(("synonym", value, 90) for value in payload.get("synonyms", []) if value)
                candidates.extend(("example_en", value, 90) for value in payload.get("examples_en", []) if value)
            for field, value, confidence in candidates:
                value_json = json.dumps(value, ensure_ascii=False)
                nv = normalized(value)
                cursor = con.execute(
                    """INSERT OR IGNORE INTO word_enrichment_candidates(
                       word_id,staging_record_id,field_name,value_json,normalized_value,source_key,
                       source_record_id,confidence,quality_status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (word["id"], row["staging_id"], field, value_json, nv, row["source_key"],
                     row["source_record_id"], confidence, "automated_checked", now(), now()),
                )
                candidate = con.execute(
                    """SELECT id,applied FROM word_enrichment_candidates
                       WHERE word_id=? AND field_name=? AND normalized_value=? AND source_key=?""",
                    (word["id"], field, nv, row["source_key"]),
                ).fetchone()
                if cursor.rowcount:
                    created += 1
                base_has_value = (field == "cefr" and bool(word["stage"])) or (field == "pos" and bool(word["pos"]))
                if base_has_value:
                    skipped_existing += 1
                    continue
                if row["audit_status"] != "approved" or row["commercial_use"] != "allowed" or confidence < 90:
                    continue
                insert = con.execute(
                    """INSERT OR IGNORE INTO word_enrichment_values(
                       word_id,candidate_id,field_name,value_json,normalized_value,source_key,
                       source_record_id,quality_status,review_status,applied_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (word["id"], candidate["id"], field, value_json, nv, row["source_key"],
                     row["source_record_id"], "automated_checked", "pending", now()),
                )
                if insert.rowcount:
                    con.execute("UPDATE word_enrichment_candidates SET applied=1,updated_at=? WHERE id=?", (now(), candidate["id"]))
                    con.execute(
                        "INSERT INTO word_enrichment_events(candidate_id,action,reason,occurred_at) VALUES(?,'apply_automated',?,?)",
                        (candidate["id"], "approved source and confidence threshold; human review remains pending", now()),
                    )
                    applied += 1
                    words.add(word["id"])
        con.commit()
        return {"candidates_created": created, "values_applied": applied,
                "words_enriched": len(words), "skipped_existing_fields": skipped_existing,
                "human_reviewed": 0, "base_rows_modified": 0}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(enrich(args.database), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
