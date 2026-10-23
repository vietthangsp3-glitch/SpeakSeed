"""Recover a small, traceable vocabulary review batch from vi.wiktionary.

The command is intentionally SQLite/local-only.  It audits the legacy
Skypedia fields, streams a pinned Kaikki snapshot, and prepares candidates for
human review.  It never grants roles, marks human review, or publishes words.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE_KEY = "kaikki-viwiktionary-en-2026-10-02"
SNAPSHOT_SHA256 = "dcdaf93d642ae1d1c4d495b68d90eb572fac86d00281044cf804e0d98147a25e"
REVIEW_BATCH = "phase6-first-vocabulary-release"
BLOCKED_TAGS = {
    "abbreviation", "archaic", "dated", "derogatory", "ethnic", "euphemistic",
    "figuratively", "historical", "informal", "nonstandard", "obsolete", "offensive",
    "rare", "slang", "vulgar",
}
VIETNAMESE_MARKS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
VIETNAMESE_TOKENS = {"là", "một", "của", "người", "sự", "việc", "có", "được", "cho", "và", "hoặc", "trong", "với", "để", "không"}
MEANING_STOPWORDS = VIETNAMESE_TOKENS | {"cái", "con", "các", "những", "thứ", "làm", "ra", "về"}
POS_MAP = {
    "noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb",
    "pron": "pronoun", "prep": "preposition", "intj": "interjection",
    "det": "determiner", "num": "number", "conj": "conjunction",
}
# These rows passed structural checks but a manual source-audit spot check found
# an obsolete, specialist, or non-target primary sense.  Exclusion is not a
# human-review approval; it simply keeps known-bad rows out of the first queue.
FIRST_BATCH_EXCLUSIONS = {
    "affection", "cola", "compress", "converse", "flunk", "skyscraper", "thriller", "wheelchair",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_word(value: object) -> str:
    return " ".join(str(value or "").casefold().replace("’", "'").split())


def clean_gloss(entry: dict) -> tuple[str, dict] | None:
    """Return only a conservative primary sense; never synthesize a translation."""
    senses = entry.get("senses")
    if not isinstance(senses, list) or not senses:
        return None
    sense = senses[0]
    if not isinstance(sense, dict):
        return None
    tags = {str(tag).casefold() for tag in sense.get("tags", [])}
    if tags & BLOCKED_TAGS or sense.get("form_of") or sense.get("alt_of"):
        return None
    glosses = sense.get("glosses")
    if not isinstance(glosses, list) or not glosses:
        return None
    raw = str(glosses[-1]).strip()
    # Date notes do not help a Core learner definition.  Removing them is an
    # explicitly disclosed adaptation, not a claim that the source lacked them.
    gloss = re.sub(r"\s*\[(?:từ )?thế kỷ[^\]]*\]\s*$", "", raw, flags=re.I)
    gloss = " ".join(gloss.split())
    if (not 2 <= len(gloss) <= 180 or any(token in gloss for token in ("{{", "}}", "<", ">", "[", "]", "&"))
            or any(char.isdigit() for char in gloss) or gloss[0] in ",;:.!?"):
        return None
    lowered = gloss.casefold()
    tokens = set(re.findall(r"[^\W\d_]+", lowered, flags=re.UNICODE))
    if not (set(lowered) & VIETNAMESE_MARKS or tokens & VIETNAMESE_TOKENS):
        return None
    return gloss, {"source_gloss": raw, "source_tags": sorted(tags)}


def meaning_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE)
            if len(token) >= 3 and token not in MEANING_STOPWORDS}


def independent_meaning_agreement(replacement: str, legacy: str) -> bool:
    """Use legacy text only as a QA witness, never as releasable provenance."""
    return bool(meaning_tokens(replacement) & meaning_tokens(legacy))


def clean_source_ipa(entry: dict) -> str:
    """Return one source-provided IPA value without generating pronunciation."""
    for sound in entry.get("sounds", []):
        if not isinstance(sound, dict):
            continue
        value = " ".join(str(sound.get("ipa") or "").split())
        if value and len(value) <= 80 and not any(token in value for token in ("<", ">", "{{", "}}")):
            return value
    return ""


def scan_snapshot(snapshot: Path, wanted: set[tuple[str, str]]) -> tuple[dict[tuple[str, str], dict], Counter]:
    found: dict[tuple[str, str], dict] = {}
    stats = Counter()
    with gzip.open(snapshot, "rt", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            stats["snapshot_records"] += 1
            entry = json.loads(raw)
            if entry.get("lang_code") != "en":
                continue
            stats["english_records"] += 1
            key = (normalize_word(entry.get("word")), POS_MAP.get(str(entry.get("pos", "")).casefold(), ""))
            if key not in wanted or key in found:
                continue
            cleaned = clean_gloss(entry)
            if not cleaned:
                stats["matched_but_rejected_quality"] += 1
                continue
            gloss, detail = cleaned
            word = key[0]
            page_url = "https://vi.wiktionary.org/wiki/" + quote(word.replace(" ", "_"), safe="")
            found[key] = {
                "meaning_vi": gloss,
                "ipa": clean_source_ipa(entry),
                "line_number": line_number,
                "source_record_id": f"line:{line_number};word:{word};pos:{entry.get('pos')}",
                "page_url": page_url,
                **detail,
            }
            stats["usable_exact_word_pos"] += 1
    return found, stats


def source_record(registry_path: Path) -> dict:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))["sources"]
    return registry[SOURCE_KEY]


def upsert_source(con: sqlite3.Connection, source: dict) -> None:
    columns = ("display_name", "owner_name", "source_url", "dataset_version", "license_name",
               "license_url", "commercial_use", "attribution", "obligations", "audit_status",
               "evidence_url", "audited_at", "notes")
    con.execute(
        f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(14))}) "
        f"ON CONFLICT(source_key) DO UPDATE SET " + ",".join(f"{column}=excluded.{column}" for column in columns),
        (SOURCE_KEY, *(source[column] for column in columns)),
    )


def wordnet_sense_counts(con: sqlite3.Connection) -> Counter:
    counts = Counter()
    rows = con.execute("""SELECT r.payload_json FROM content_staging_records r
      JOIN content_import_batches b ON b.id=r.batch_id
      WHERE b.source_key='princeton-wordnet-3.0' AND r.validation_status='valid'""")
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        key = (normalize_word(payload.get("lemma")), str(payload.get("pos", "")).casefold())
        counts[key] += 1
    return counts


def mark_legacy_field_audit(provenance: dict, meaning: str, ipa: str) -> dict:
    result = dict(provenance)
    legacy = result.get("meaning_vi_ipa") if isinstance(result.get("meaning_vi_ipa"), dict) else {}
    if meaning and "meaning_vi" not in result:
        result["meaning_vi"] = {
            "source": "skypedia-en-vi", "classification": "UNVERIFIED", "disposition": "REPLACE",
            "reason": "The local SQLite row has no upstream source identifier for this definition.",
            "legacy_value_sha256": hashlib.sha256(meaning.encode("utf-8")).hexdigest(),
        }
    if ipa and "ipa" not in result:
        result["ipa"] = {
            "source": "skypedia-en-vi", "classification": "UNVERIFIED", "disposition": "REPLACE",
            "reason": "The row does not identify whether IPA was upstream, corrected, or G2P-generated.",
            "legacy_value_sha256": hashlib.sha256(ipa.encode("utf-8")).hexdigest(),
        }
    if legacy:
        result["legacy_dataset_claim"] = {
            **legacy, "classification": "CONDITIONAL_DATASET_ONLY", "excluded_from_release": True,
        }
        result.pop("meaning_vi_ipa", None)
    return result


def recover(database: Path, snapshot: Path, registry_path: Path, limit: int, output: Path,
            dry_run: bool = False) -> dict:
    if database.resolve() == (ROOT / "speakseed.db").resolve():
        raise ValueError("Refusing to modify the canonical SQLite database; use a staging copy")
    if not snapshot.is_file():
        raise ValueError(f"Missing pinned snapshot: {snapshot}")
    actual_hash = file_sha256(snapshot)
    if actual_hash != SNAPSHOT_SHA256:
        raise ValueError(f"Snapshot SHA-256 mismatch: {actual_hash}")
    if not 1 <= limit <= 200:
        raise ValueError("Review batch size must be between 1 and 200")

    con = sqlite3.connect(database, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    candidates = con.execute("""SELECT c.* FROM vocabulary_candidates c
      WHERE c.published_word_id IS NULL AND c.review_status<>'human_reviewed'
      ORDER BY CASE c.cefr_level WHEN 'A1' THEN 0 WHEN 'A2' THEN 1 WHEN 'B1' THEN 2 ELSE 3 END,
               c.word,c.id""").fetchall()
    legacy_ipa_rows = sum(
        1 for row in candidates
        if str(row["ipa"] or "").strip()
        or (json.loads(row["provenance_json"]).get("ipa") or {}).get("legacy_value_sha256")
    )
    wanted = {(row["normalized_word"], row["pos"]) for row in candidates}
    matches, scan = scan_snapshot(snapshot, wanted)
    topic_ids = {row[0] for row in con.execute("SELECT DISTINCT candidate_id FROM vocabulary_candidate_topics")}
    sense_counts = wordnet_sense_counts(con)
    eligible = [row for row in candidates
                if (row["normalized_word"], row["pos"]) in matches and row["id"] in topic_ids
                and row["normalized_word"] not in FIRST_BATCH_EXCLUSIONS
                and sense_counts[(row["normalized_word"], row["pos"])] == 1
                and independent_meaning_agreement(matches[(row["normalized_word"], row["pos"])]["meaning_vi"],
                                                  row["meaning_vi"])]
    selected = eligible[:limit]
    before = {
        "published_words": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
        "legacy_meaning_rows": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE trim(meaning_vi)<>''").fetchone()[0],
        "legacy_ipa_rows": legacy_ipa_rows,
        "human_reviewed": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE review_status='human_reviewed'").fetchone()[0],
        "published_candidates": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE published_word_id IS NOT NULL").fetchone()[0],
    }
    stamp = utcnow()
    try:
        con.execute("BEGIN IMMEDIATE")
        upsert_source(con, source_record(registry_path))
        audited = 0
        for row in candidates:
            provenance = json.loads(row["provenance_json"])
            updated = mark_legacy_field_audit(provenance, row["meaning_vi"], row["ipa"])
            if updated != provenance:
                con.execute("UPDATE vocabulary_candidates SET provenance_json=?,updated_at=? WHERE id=?",
                            (json.dumps(updated, ensure_ascii=False, sort_keys=True), stamp, row["id"]))
                audited += 1

        manifest = []
        for row in selected:
            evidence = matches[(row["normalized_word"], row["pos"])]
            provenance = json.loads(con.execute("SELECT provenance_json FROM vocabulary_candidates WHERE id=?", (row["id"],)).fetchone()[0])
            provenance["meaning_vi"] = {
                "source": SOURCE_KEY,
                "record": evidence["source_record_id"],
                "page_url": evidence["page_url"],
                "snapshot_sha256": SNAPSHOT_SHA256,
                "classification": "CONDITIONAL",
                "license": "CC BY-SA 4.0",
                "changes": "Primary POS-matched gloss selected; whitespace normalized; trailing century note removed when present.",
                "attribution": "Vietnamese Wiktionary contributors; Kaikki.org/Wiktextract (Tatu Ylonen).",
            }
            # The old IPA remains documented by hash above, but is excluded from
            # the releasable row because its row-level generation chain is unknown.
            ipa_audit = provenance.setdefault("ipa", {
                "classification": "UNVERIFIED", "disposition": "REPLACE",
                "reason": "No row-level IPA evidence is available for this candidate.",
            })
            ipa_audit["excluded_from_release"] = True
            provenance["review_batch"] = {"key": REVIEW_BATCH, "human_reviewed": False}
            con.execute("""UPDATE vocabulary_candidates SET meaning_vi=?,ipa='',source_key=?,source_record_id=?,
              provenance_json=?,license_status='pass',qa_status='pass',core_status='review_ready',
              review_status='pending',reviewed_at=NULL,reviewed_by_user_id=NULL,updated_at=? WHERE id=?""",
              (evidence["meaning_vi"], SOURCE_KEY, evidence["source_record_id"],
               json.dumps(provenance, ensure_ascii=False, sort_keys=True), stamp, row["id"]))
            manifest.append({"candidate_id": row["id"], "word": row["word"], "pos": row["pos"],
                             "cefr": row["cefr_level"], "meaning_vi": evidence["meaning_vi"],
                             "source_record_id": evidence["source_record_id"], "source_url": evidence["page_url"]})
        if dry_run:
            con.rollback()
        else:
            con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    report = {
        "mode": "dry-run" if dry_run else "staging-write",
        "database": str(database), "source_key": SOURCE_KEY, "snapshot_sha256": actual_hash,
        "legacy_field_audit": {
            "candidate_rows_audited": len(candidates),
            "meaning_vi_unverified": before["legacy_meaning_rows"],
            "ipa_unverified": before["legacy_ipa_rows"],
            "verified_meaning_vi": 0, "verified_ipa": 0,
            "reason": "Skypedia SQLite has no field-level upstream record identifiers; dataset-level CC BY-SA evidence is not row-level provenance.",
        },
        "candidate_classification": {
            "VERIFIED": 0,
            "CONDITIONAL": len(selected),
            "UNVERIFIED": before["legacy_meaning_rows"] - len(selected),
            "RESTRICTED": 0,
            "REPLACE_OR_NEEDS_SOURCE": len(candidates) - before["legacy_meaning_rows"],
        },
        "snapshot_scan": dict(scan),
        "automated_qa_rule": "Exact headword/POS, conservative primary gloss, no restricted usage tag, exactly one staged WordNet sense, and lexical agreement with the legacy meaning witness.",
        "conditional_replacements_available_with_topic": len(eligible),
        "fields_replaced": {"meaning_vi": len(selected), "ipa": 0},
        "first_review_batch": {"key": REVIEW_BATCH, "count": len(manifest), "items": manifest},
        "human_reviewed": before["human_reviewed"], "published_new": before["published_candidates"],
        "published_words_before": before["published_words"], "published_words_after": before["published_words"],
        "safety": {"canonical_sqlite_modified": False, "neon_used": False, "roles_created": False,
                   "human_review_fabricated": False, "published": False},
    }
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the Phase 6 vocabulary review batch locally")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path, default=ROOT / ".source-cache/viwiktionary-2026-10-02.jsonl.gz")
    parser.add_argument("--registry", type=Path, default=ROOT / "data/source_registry.json")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "qa_artifacts/phase6-first-review-batch.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(recover(args.database, args.snapshot, args.registry, args.limit, args.output, args.dry_run),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
