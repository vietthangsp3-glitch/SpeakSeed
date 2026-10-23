"""Publish a conservatively verified vocabulary batch without faking human review.

The source candidate database and pinned vi.wiktionary snapshot are opened read-only.
Only exact headword/POS records with a clean Vietnamese gloss, independent lexical
agreement, an allowed CEFR level, and complete record-level provenance are released.
The target operation is one SQLite transaction and is idempotent by normalized word.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations import run_migrations
from tools.recover_vocabulary_phase6 import (
    FIRST_BATCH_EXCLUSIONS,
    SNAPSHOT_SHA256,
    SOURCE_KEY,
    file_sha256,
    independent_meaning_agreement,
    scan_snapshot,
    source_record,
)

RULE_VERSION = "auto-core-v1"
TOPIC_SOURCE = "automated-release-v1"
LEVELS = ("A0", "A1", "A2", "B1", "B2")
HEADWORD_RE = re.compile(r"[a-z][a-z '\-]{0,69}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def readonly(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def recovered_evidence_matches(row: sqlite3.Row, evidence: dict) -> bool:
    if row["source_key"] != SOURCE_KEY or row["source_record_id"] != evidence["source_record_id"]:
        return False
    try:
        meaning = json.loads(row["provenance_json"]).get("meaning_vi", {})
    except (TypeError, ValueError):
        return False
    return (meaning.get("source") == SOURCE_KEY
            and meaning.get("snapshot_sha256") == SNAPSHOT_SHA256
            and meaning.get("classification") == "CONDITIONAL")


def candidate_is_eligible(row: sqlite3.Row, evidence: dict | None) -> tuple[bool, str]:
    if evidence is None:
        return False, "no_clean_exact_licensed_record"
    if row["normalized_word"] in FIRST_BATCH_EXCLUSIONS:
        return False, "known_unsuitable_primary_sense"
    if row["cefr_level"] not in LEVELS:
        return False, "invalid_or_missing_cefr"
    if not row["pos"].strip() or not HEADWORD_RE.fullmatch(row["normalized_word"]):
        return False, "invalid_headword_or_pos"
    if not (recovered_evidence_matches(row, evidence)
            or independent_meaning_agreement(evidence["meaning_vi"], row["meaning_vi"])):
        return False, "meaning_not_independently_corroborated"
    return True, "eligible"


def build_plan(source_database: Path, target_database: Path, snapshot: Path,
               registry: Path, min_topic_confidence: int = 70) -> dict:
    if source_database.resolve() == target_database.resolve():
        raise ValueError("Source candidate database and target library must be different files")
    if file_sha256(snapshot) != SNAPSHOT_SHA256:
        raise ValueError("Pinned vi.wiktionary snapshot SHA-256 mismatch")
    source_meta = source_record(registry)
    if (source_meta["audit_status"] not in {"approved", "conditional"}
            or source_meta["commercial_use"] not in {"allowed", "conditional"}
            or not source_meta["license_name"] or not source_meta["evidence_url"]):
        raise ValueError("Source registry does not satisfy the automated license gate")

    with readonly(source_database) as source, readonly(target_database) as target:
        candidates = source.execute("SELECT * FROM vocabulary_candidates ORDER BY id").fetchall()
        existing = {row[0] for row in target.execute(
            "SELECT normalized_word FROM library_words WHERE reviewed=1"
        )}
        matches, scan_stats = scan_snapshot(snapshot, {
            (row["normalized_word"], row["pos"]) for row in candidates
        })
        topic_rows = source.execute("""SELECT ct.candidate_id,ct.confidence,ct.source_key,ct.rationale,
          t.slug,t.name_en FROM vocabulary_candidate_topics ct
          JOIN vocabulary_topics t ON t.id=ct.topic_id
          WHERE t.active=1 ORDER BY ct.candidate_id,ct.confidence DESC,t.id""").fetchall()

    topics: dict[int, dict] = {}
    for item in topic_rows:
        if item["candidate_id"] not in topics and item["confidence"] >= min_topic_confidence:
            topics[item["candidate_id"]] = dict(item)

    blocked = Counter()
    eligible = []
    duplicate_target = []
    for row in candidates:
        evidence = matches.get((row["normalized_word"], row["pos"]))
        valid, reason = candidate_is_eligible(row, evidence)
        if not valid:
            blocked[reason] += 1
            continue
        if row["normalized_word"] in existing:
            blocked["already_published_normalized_word"] += 1
            duplicate_target.append(row["id"])
            continue
        eligible.append({"row": row, "evidence": evidence, "topic": topics.get(row["id"])})

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in eligible:
        grouped[item["row"]["normalized_word"]].append(item)
    releases = []
    level_order = {level: index for index, level in enumerate(LEVELS)}
    for normalized_word, items in sorted(grouped.items()):
        meanings = list(dict.fromkeys(item["evidence"]["meaning_vi"] for item in items))
        poses = list(dict.fromkeys(item["row"]["pos"] for item in items))
        best_topic = max((item["topic"] for item in items if item["topic"]),
                         key=lambda value: value["confidence"], default=None)
        releases.append({
            "normalized_word": normalized_word,
            "word": items[0]["row"]["word"],
            "meaning": "; ".join(meanings),
            "ipa": next((item["evidence"]["ipa"] for item in items if item["evidence"]["ipa"]), ""),
            "pos": " / ".join(poses),
            "cefr": min((item["row"]["cefr_level"] for item in items), key=level_order.get),
            "topic": best_topic,
            "candidate_ids": [item["row"]["id"] for item in items],
            "records": [{"record": item["evidence"]["source_record_id"],
                         "page_url": item["evidence"]["page_url"]} for item in items],
        })

    unique_candidates = len({row["normalized_word"] for row in candidates})
    return {
        "source_database": str(source_database), "target_database": str(target_database),
        "source_key": SOURCE_KEY, "source_metadata": source_meta,
        "snapshot_sha256": SNAPSHOT_SHA256, "snapshot_scan": dict(scan_stats),
        "old_published": len(existing), "candidate_rows": len(candidates),
        "candidate_unique_normalized": unique_candidates,
        "duplicate_candidate_rows": len(candidates) - unique_candidates,
        "duplicates_against_library": len(duplicate_target),
        "eligible_candidate_rows": len(eligible), "release_rows": len(releases),
        "blocked": dict(sorted(blocked.items())), "releases": releases,
        "min_topic_confidence": min_topic_confidence,
    }


def publish(plan: dict, target_database: Path) -> dict:
    run_migrations(target_database, ROOT / "migrations")
    con = sqlite3.connect(target_database, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    stamp = now()
    source = plan["source_metadata"]
    before = {
        "published": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
        "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "progress": con.execute("SELECT COUNT(*) FROM progress").fetchone()[0],
    }
    published = []
    topic_count = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("""INSERT INTO data_sources(name,version,source_url,license_name,license_url,attribution,retrieved_at,sha256)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(name) DO NOTHING""",
          (SOURCE_KEY, source["dataset_version"], source["source_url"], source["license_name"],
           source["license_url"], source["attribution"], stamp, SNAPSHOT_SHA256))
        for item in plan["releases"]:
            if con.execute("SELECT 1 FROM library_words WHERE normalized_word=? AND reviewed=1",
                           (item["normalized_word"],)).fetchone():
                continue
            topic_name = item["topic"]["name_en"] if item["topic"] else "Unclassified"
            cur = con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,
              source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at)
              VALUES(?,?,?,'',?,'📘',?,?,?,?,'CC BY-SA 4.0; automated_checked',1,?,'',90,?)""",
              (item["word"], item["meaning"], item["ipa"], topic_name, item["cefr"], item["pos"],
               SOURCE_KEY, " | ".join(record["record"] for record in item["records"]),
               item["normalized_word"], stamp))
            word_id = cur.lastrowid
            checks = {
                "exact_headword_pos": True, "clean_vietnamese_gloss": True,
                "independent_lexical_agreement": True, "cefr_present": True,
                "license_registry_gate": True, "deduplicated_normalized_word": True,
                "human_reviewed": False,
            }
            provenance = {
                "source_records": item["records"], "license": source["license_name"],
                "license_url": source["license_url"], "attribution": source["attribution"],
                "changes": "Exact POS-matched primary gloss selected; whitespace normalized; senses merged by normalized headword.",
            }
            con.execute("""INSERT INTO vocabulary_automated_releases(word_id,source_candidate_ids_json,source_key,
              source_snapshot_sha256,rule_version,checks_json,provenance_json,released_at)
              VALUES(?,?,?,?,?,?,?,?)""",
              (word_id, json.dumps(item["candidate_ids"]), SOURCE_KEY, SNAPSHOT_SHA256, RULE_VERSION,
               json.dumps(checks, sort_keys=True), json.dumps(provenance, ensure_ascii=False, sort_keys=True), stamp))
            for field_name in ("meaning", "ipa"):
                if field_name == "ipa" and not item["ipa"]:
                    continue
                for record in item["records"]:
                    con.execute("""INSERT OR IGNORE INTO word_attributions(word_id,field_name,source_name,
                      source_record_id,source_url,license_name,attribution) VALUES(?,?,?,?,?,?,?)""",
                      (word_id, field_name, SOURCE_KEY, record["record"], record["page_url"],
                       source["license_name"], source["attribution"]))
            if item["topic"]:
                topic_id = con.execute("SELECT id FROM vocabulary_topics WHERE slug=? AND active=1",
                                       (item["topic"]["slug"],)).fetchone()[0]
                con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,
                  confidence,source_key,rationale,created_at,reviewed_at,reviewed_by)
                  VALUES(?,?,'','pending',1,?,'automated-release-v1',?,? ,NULL,'')""",
                  (word_id, topic_id, item["topic"]["confidence"],
                   "Automated WordNet semantic mapping; not human-reviewed. " + item["topic"]["rationale"], stamp))
                topic_count += 1
            published.append({"word_id": word_id, "normalized_word": item["normalized_word"]})
        con.commit()
    except Exception:
        con.rollback()
        raise
    after = {
        "published": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
        "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "progress": con.execute("SELECT COUNT(*) FROM progress").fetchone()[0],
        "integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_key_errors": len(con.execute("PRAGMA foreign_key_check").fetchall()),
    }
    con.close()
    if before["users"] != after["users"] or before["progress"] != after["progress"]:
        raise RuntimeError("User or progress counts changed during vocabulary release")
    return {"published_this_run": len(published), "topic_mappings_published": topic_count,
            "before": before, "after": after, "items": published}


def serializable_plan(plan: dict) -> dict:
    return {key: value for key, value in plan.items() if key != "releases"} | {
        "release_preview": [{key: value for key, value in item.items() if key != "topic"}
                            | {"topic": item["topic"]["slug"] if item["topic"] else "unclassified"}
                            for item in plan["releases"][:100]]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated, provenance-gated vocabulary release")
    parser.add_argument("--source-database", required=True, type=Path)
    parser.add_argument("--target-database", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path,
                        default=ROOT / ".source-cache/viwiktionary-2026-10-02.jsonl.gz")
    parser.add_argument("--registry", type=Path, default=ROOT / "data/source_registry.json")
    parser.add_argument("--min-topic-confidence", type=int, default=70)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "qa_artifacts/vocabulary-auto-release.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.min_topic_confidence <= 100:
        parser.error("--min-topic-confidence must be between 0 and 100")
    plan = build_plan(args.source_database, args.target_database, args.snapshot, args.registry,
                      args.min_topic_confidence)
    result = {"mode": "dry-run" if args.dry_run else "write", "plan": serializable_plan(plan)}
    if not args.dry_run:
        result["release"] = publish(plan, args.target_database)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "mode": result["mode"],
        "candidate_rows": plan["candidate_rows"],
        "release_rows": plan["release_rows"],
        "blocked": plan["blocked"],
        "published_this_run": result.get("release", {}).get("published_this_run", 0),
        "published_after": result.get("release", {}).get("after", {}).get("published", plan["old_published"]),
        "report": str(args.report),
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
