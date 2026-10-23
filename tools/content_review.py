"""Local-only review CLI. It deliberately exposes no web/admin API."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from question_bank import public_item


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def materialize_question_drafts(database: Path) -> dict:
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    created = 0
    try:
        for row in con.execute(
            """SELECT r.id,r.source_record_id,r.payload_json,r.quality_status,b.source_key,
                      s.license_name FROM content_staging_records r
               JOIN content_import_batches b ON b.id=r.batch_id
               JOIN content_sources s ON s.source_key=b.source_key
               WHERE r.content_type='question' AND r.validation_status='valid' AND b.status='staged'"""
        ):
            payload = json.loads(row["payload_json"])
            level = payload.get("cefr_level", "unverified")
            difficulty = {"A0": 1, "A1": 1, "A2": 2, "B1": 3, "B2": 4}.get(level, 3)
            cursor = con.execute(
                """INSERT OR IGNORE INTO question_bank_drafts(
                   staging_record_id,stable_id,question_type,cefr_level,skill,topic,difficulty,
                   prompt,answer_key_json,accepted_answers_json,explanation_vi,explanation_en,
                   context_text,source_key,source_record_id,license_name,quality_status,
                   review_status,published,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?)""",
                (row["id"], f"{row['source_key']}:{payload.get('stable_id') or row['source_record_id']}",
                 payload["question_type"], level, payload.get("skill", "grammar"),
                 payload.get("topic", ""), difficulty, payload["prompt"],
                 json.dumps(payload.get("answer_key", []), ensure_ascii=False),
                 json.dumps(payload.get("accepted_answers", []), ensure_ascii=False),
                 payload.get("explanation_vi", ""), payload.get("explanation_en", ""),
                 payload.get("context_text", ""), row["source_key"], row["source_record_id"],
                 row["license_name"], row["quality_status"], now(), now()),
            )
            created += max(cursor.rowcount, 0)
        con.commit()
        return {"created": created, "published": 0, "human_reviewed": 0}
    finally:
        con.close()


def materialize_sentence_drafts(database: Path, per_type: int = 50) -> dict:
    """Build conservative drafts only when every English token has a CEFR word."""
    if per_type < 1:
        raise ValueError("per_type must be positive")
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    levels = {"A0": 0, "A1": 1, "A2": 2, "B1": 3, "B2": 4}
    reverse = {value: key for key, value in levels.items()}
    vocabulary = {
        row["normalized_word"]: row["stage"]
        for row in con.execute("SELECT normalized_word,stage FROM library_words WHERE reviewed=1")
        if row["stage"] in levels
    }
    counts = {"fill_blank": 0, "sentence_ordering": 0, "listening": 0}
    try:
        rows = con.execute(
            """SELECT r.id,r.source_record_id,r.stable_key,r.payload_json,b.source_key,
                      s.license_name,s.attribution source_attribution
               FROM content_staging_records r
               JOIN content_import_batches b ON b.id=r.batch_id
               JOIN content_sources s ON s.source_key=b.source_key
               WHERE b.source_key='tatoeba-text' AND b.status='staged'
                 AND r.validation_status='valid' ORDER BY r.id"""
        )
        for row in rows:
            if all(value >= per_type for value in counts.values()):
                break
            source = json.loads(row["payload_json"])
            tokens = re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", source["english"])
            normalized_tokens = [token.casefold().replace("’", "'") for token in tokens]
            if not 4 <= len(tokens) <= 10 or any(token not in vocabulary for token in normalized_tokens):
                continue
            level = reverse[max(levels[vocabulary[token]] for token in normalized_tokens)]
            answer_index = next((i for i in range(len(tokens) - 1, -1, -1) if len(tokens[i]) >= 4), len(tokens) - 1)
            answer = tokens[answer_index]
            blanked = re.sub(rf"\b{re.escape(answer)}\b", "_____", source["english"], count=1)
            shuffled = tokens[1:] + tokens[:1]
            if shuffled == tokens:
                continue
            variants = [
                ("fill_blank", f"Điền từ còn thiếu: {blanked}", [answer], {"sentence": blanked, "translation_vi": source["vietnamese"]}),
                ("sentence_ordering", "Sắp xếp các từ thành câu đúng.", [source["english"]], {"tokens": shuffled, "translation_vi": source["vietnamese"]}),
                ("listening", f"Nghe và điền từ còn thiếu: {blanked}", [answer], {"transcript": source["english"], "sentence": blanked, "translation_vi": source["vietnamese"]}),
            ]
            for question_type, prompt, answers, payload in variants:
                if counts[question_type] >= per_type:
                    continue
                stable_id = f"tatoeba:{question_type}:{row['stable_key']}"
                cursor = con.execute(
                    """INSERT OR IGNORE INTO question_bank_drafts(
                       staging_record_id,stable_id,question_type,cefr_level,skill,topic,difficulty,
                       prompt,answer_key_json,accepted_answers_json,explanation_vi,explanation_en,
                       context_text,source_key,source_record_id,license_name,quality_status,
                       review_status,published,created_at,updated_at,payload_json,attribution)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?,?,?)""",
                    (row["id"], stable_id, question_type, level,
                     "listening" if question_type == "listening" else "grammar",
                     "Sentence patterns", max(1, levels[level]), prompt,
                     json.dumps(answers, ensure_ascii=False), json.dumps(answers, ensure_ascii=False),
                     f"Câu hoàn chỉnh: {source['english']} Nghĩa: {source['vietnamese']}", "",
                     source["english"] if question_type == "listening" else "",
                     row["source_key"], row["source_record_id"], row["license_name"],
                     "needs_review", now(), now(), json.dumps(payload, ensure_ascii=False),
                     source.get("attribution") or row["source_attribution"]),
                )
                if cursor.rowcount:
                    counts[question_type] += 1
        con.commit()
        return {"created_by_type": counts, "created": sum(counts.values()),
                "published": 0, "human_reviewed": 0}
    finally:
        con.close()


def review(database: Path, draft_id: int, reviewer: str, decision: str, reason: str,
           explanation_vi: str = "") -> dict:
    if not reviewer.strip():
        raise ValueError("Reviewer identity is required")
    if not reason.strip():
        raise ValueError("A review reason is required")
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        draft = con.execute("SELECT * FROM question_bank_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft:
            raise ValueError(f"Unknown draft {draft_id}")
        if explanation_vi.strip():
            raise ValueError("Edit the explanation first, rerun QA, then approve")
        if decision == "approve" and (not draft["explanation_vi"].strip() or draft["answer_key_json"] in ("", "[]", "{}", "null")):
            raise ValueError("Cannot approve: Vietnamese explanation and answer key are required")
        qa = con.execute("SELECT overall_status,checked_at FROM question_qa_results WHERE question_id=?", (draft_id,)).fetchone()
        if decision == "approve" and (not qa or qa["overall_status"] == "fail" or qa["checked_at"] < draft["updated_at"]):
            raise ValueError("Cannot approve: a current non-failing automated QA result is required")
        stamp = now()
        event_decision = "approve" if decision == "approve" else "reject"
        con.execute(
            """INSERT INTO content_review_events(staging_record_id,reviewer_name,decision,notes,reviewed_at)
               VALUES(?,?,?,?,?)""",
            (draft["staging_record_id"], reviewer.strip(), event_decision, reason.strip(), stamp),
        )
        status = "human_reviewed" if decision == "approve" else "rejected"
        con.execute("UPDATE content_staging_records SET review_status=? WHERE id=?", (status, draft["staging_record_id"]))
        con.execute("UPDATE question_bank_drafts SET review_status=?,updated_at=? WHERE id=?", (status, stamp, draft_id))
        con.commit()
        return {"draft_id": draft_id, "decision": decision, "reviewer": reviewer.strip(), "published": False}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def list_pending(database: Path, draft_id: int | None = None, *, level: str = "",
                 question_type: str = "", source: str = "", limit: int = 100) -> list[dict]:
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        if draft_id:
            rows = con.execute("SELECT * FROM question_bank_drafts WHERE id=?", (draft_id,))
        else:
            where = ["d.review_status='pending'"]; params: list = []
            if level: where.append("d.cefr_level=?"); params.append(level)
            if question_type: where.append("d.question_type=?"); params.append(question_type)
            if source: where.append("d.source_key=?"); params.append(source)
            params.append(limit)
            rows = con.execute("""SELECT d.*,q.overall_status qa_status,q.issues_json
                FROM question_bank_drafts d LEFT JOIN question_qa_results q ON q.question_id=d.id
                WHERE """ + " AND ".join(where) + " ORDER BY d.id LIMIT ?", params)
        return [dict(row) for row in rows]
    finally:
        con.close()


def edit_draft(database: Path, draft_id: int, editor: str, reason: str, **changes) -> dict:
    if not editor.strip() or not reason.strip():
        raise ValueError("Editor identity and reason are required")
    allowed = {"prompt", "explanation_vi", "cefr_level", "accepted_answers_json", "payload_json"}
    changes = {key: value for key, value in changes.items() if key in allowed and value is not None}
    if not changes:
        raise ValueError("No draft changes supplied")
    if "cefr_level" in changes and changes["cefr_level"] not in {"A0","A1","A2","B1","B2","unverified"}:
        raise ValueError("Invalid CEFR level")
    for key in ("accepted_answers_json", "payload_json"):
        if key in changes:
            parsed = json.loads(changes[key])
            if key == "accepted_answers_json" and (not isinstance(parsed, list) or not parsed):
                raise ValueError("Accepted answers must be a non-empty JSON list")
            if key == "payload_json" and not isinstance(parsed, dict):
                raise ValueError("Payload must be a JSON object")
            changes[key] = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    con = sqlite3.connect(database, timeout=30); con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM question_bank_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row: raise ValueError(f"Unknown draft {draft_id}")
        if row["published"]: raise ValueError("Published content is immutable")
        before = {key: row[key] for key in allowed}
        stamp = now()
        assignments = ",".join(f"{key}=?" for key in changes)
        con.execute(f"UPDATE question_bank_drafts SET {assignments},review_status='pending',updated_at=? WHERE id=?",
                    [*changes.values(), stamp, draft_id])
        con.execute("UPDATE content_staging_records SET review_status='pending' WHERE id=?", (row["staging_record_id"],))
        after_row = con.execute("SELECT * FROM question_bank_drafts WHERE id=?", (draft_id,)).fetchone()
        after = {key: after_row[key] for key in allowed}
        con.execute("""INSERT INTO question_draft_revisions(question_id,editor_name,reason,before_json,after_json,edited_at)
                       VALUES(?,?,?,?,?,?)""",
                    (draft_id, editor.strip(), reason.strip(), json.dumps(before, ensure_ascii=False),
                     json.dumps(after, ensure_ascii=False), stamp))
        con.execute("DELETE FROM question_qa_results WHERE question_id=?", (draft_id,))
        con.commit()
        return {"draft_id": draft_id, "edited": sorted(changes), "review_status": "pending", "qa_required": True}
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def preview(database: Path, draft_id: int) -> dict:
    con = sqlite3.connect(database); con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM question_bank_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row: raise ValueError(f"Unknown draft {draft_id}")
        return {"learner_view": public_item(row), "answers_hidden": True,
                "status": {"review": row["review_status"], "published": bool(row["published"])}}
    finally:
        con.close()


def audit_log(database: Path, draft_id: int) -> dict:
    con = sqlite3.connect(database); con.row_factory = sqlite3.Row
    try:
        draft = con.execute("SELECT staging_record_id FROM question_bank_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft: raise ValueError(f"Unknown draft {draft_id}")
        return {
            "reviews": [dict(row) for row in con.execute(
                "SELECT reviewer_name,decision,notes,reviewed_at FROM content_review_events WHERE staging_record_id=? ORDER BY id",
                (draft["staging_record_id"],))],
            "revisions": [dict(row) for row in con.execute(
                "SELECT editor_name,reason,before_json,after_json,edited_at FROM question_draft_revisions WHERE question_id=? ORDER BY id",
                (draft_id,))],
            "publications": [dict(row) for row in con.execute(
                """SELECT b.id,b.publisher_name,b.reason,b.status,b.created_at,b.finished_at
                   FROM question_publication_items i JOIN question_publication_batches b ON b.id=i.batch_id
                   WHERE i.question_id=? ORDER BY b.id""", (draft_id,))],
        }
    finally:
        con.close()


def publish_batch(database: Path, draft_ids: list[int], publisher: str, reason: str, confirm: bool,
                  confirm_license_conditions: bool = False) -> dict:
    if not confirm: raise ValueError("Explicit --confirm-publish is required")
    if not publisher.strip() or not reason.strip(): raise ValueError("Publisher identity and reason are required")
    draft_ids = sorted(set(draft_ids))
    if not draft_ids: raise ValueError("At least one draft ID is required")
    con = sqlite3.connect(database, timeout=30); con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in draft_ids)
        rows = list(con.execute(f"""SELECT d.*,q.overall_status,s.audit_status,s.commercial_use,s.evidence_url
            FROM question_bank_drafts d JOIN question_qa_results q ON q.question_id=d.id
            JOIN content_sources s ON s.source_key=d.source_key WHERE d.id IN ({placeholders})""", draft_ids))
        if len(rows) != len(draft_ids): raise ValueError("One or more drafts do not exist or have no QA result")
        for row in rows:
            if row["published"]: raise ValueError(f"Draft {row['id']} is already published")
            if row["review_status"] != "human_reviewed" or row["overall_status"] != "pass":
                raise ValueError(f"Draft {row['id']} is not human-reviewed with QA PASS")
            if row["audit_status"] not in {"approved", "conditional"} or row["commercial_use"] not in {"allowed", "conditional"} or not row["evidence_url"]:
                raise ValueError(f"Draft {row['id']} has no publishable license evidence")
            if row["audit_status"] == "conditional" and not confirm_license_conditions:
                raise ValueError(f"Draft {row['id']} requires explicit --confirm-license-conditions")
        stamp = now()
        batch_id = con.execute("""INSERT INTO question_publication_batches(publisher_name,reason,status,created_at,item_count,
            license_conditions_confirmed) VALUES(?,?,'publishing',?,?,?)""",
            (publisher.strip(), reason.strip(), stamp, len(rows), int(confirm_license_conditions))).lastrowid
        for row in rows:
            snapshot = {key: row[key] for key in ("id","stable_id","prompt","answer_key_json","accepted_answers_json","explanation_vi","payload_json")}
            digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            con.execute("INSERT INTO question_publication_items(batch_id,question_id,published_hash) VALUES(?,?,?)",
                        (batch_id, row["id"], digest))
            con.execute("UPDATE question_bank_drafts SET published=1,published_at=?,published_by=? WHERE id=?",
                        (stamp, publisher.strip(), row["id"]))
        con.execute("UPDATE question_publication_batches SET status='published',finished_at=? WHERE id=?", (now(), batch_id))
        con.commit()
        return {"batch_id": batch_id, "published": len(rows), "publisher": publisher.strip()}
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local SpeakSeed content review")
    parser.add_argument("command", choices=("materialize", "materialize-sentences", "list", "show",
                                            "edit", "preview", "audit-log", "approve", "reject", "publish-batch"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--draft-id", type=int)
    parser.add_argument("--reviewer")
    parser.add_argument("--reason", default="")
    parser.add_argument("--explanation-vi", default="")
    parser.add_argument("--per-type", type=int, default=50)
    parser.add_argument("--level", default="")
    parser.add_argument("--type", dest="question_type", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--editor")
    parser.add_argument("--prompt")
    parser.add_argument("--cefr-level")
    parser.add_argument("--accepted-answers-json")
    parser.add_argument("--payload-json")
    parser.add_argument("--draft-ids", default="")
    parser.add_argument("--confirm-publish", action="store_true")
    parser.add_argument("--confirm-license-conditions", action="store_true")
    args = parser.parse_args()
    if args.command == "materialize":
        result = materialize_question_drafts(args.database)
    elif args.command == "materialize-sentences":
        result = materialize_sentence_drafts(args.database, args.per_type)
    elif args.command in {"list", "show"}:
        if args.command == "show" and not args.draft_id:
            parser.error("show requires --draft-id")
        result = list_pending(args.database, args.draft_id if args.command == "show" else None,
                              level=args.level, question_type=args.question_type,
                              source=args.source, limit=args.limit)
    elif args.command == "edit":
        if not args.draft_id or not args.editor: parser.error("edit requires --draft-id and --editor")
        result = edit_draft(args.database, args.draft_id, args.editor, args.reason,
                            prompt=args.prompt, explanation_vi=args.explanation_vi or None,
                            cefr_level=args.cefr_level, accepted_answers_json=args.accepted_answers_json,
                            payload_json=args.payload_json)
    elif args.command == "preview":
        if not args.draft_id: parser.error("preview requires --draft-id")
        result = preview(args.database, args.draft_id)
    elif args.command == "audit-log":
        if not args.draft_id: parser.error("audit-log requires --draft-id")
        result = audit_log(args.database, args.draft_id)
    elif args.command == "publish-batch":
        ids = [int(value) for value in args.draft_ids.split(",") if value.strip().isdigit()]
        result = publish_batch(args.database, ids, args.reviewer or "", args.reason, args.confirm_publish,
                               args.confirm_license_conditions)
    else:
        if not args.draft_id or not args.reviewer:
            parser.error("approve/reject require --draft-id and --reviewer")
        result = review(args.database, args.draft_id, args.reviewer, args.command,
                        args.reason, args.explanation_vi)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
