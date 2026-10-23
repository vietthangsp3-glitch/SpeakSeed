"""Build and audit the local Phase-3 question bank without publishing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_VERSION = "phase3-qa-1.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _spread(rows: list, count: int) -> list:
    if count >= len(rows):
        return rows
    return [rows[round(index * (len(rows) - 1) / (count - 1))] for index in range(count)]


def _source() -> dict:
    registry = json.loads((ROOT / "data" / "source_registry.json").read_text(encoding="utf-8"))
    return registry["sources"]["speakseed-original-content-v1"]


def _question(stable_id: str, question_type: str, level: str, skill: str, topic: str,
              prompt: str, answers: list[str], explanation_vi: str, payload: dict,
              ref_type: str, ref_id: int, contexts: list[str]) -> dict:
    return {
        "stable_id": stable_id, "question_type": question_type, "cefr_level": level,
        "skill": skill, "topic": topic, "prompt": prompt, "answers": answers,
        "explanation_vi": explanation_vi, "payload": payload,
        "ref_type": ref_type, "ref_id": ref_id, "contexts": contexts,
    }


def collect_existing_questions(con: sqlite3.Connection) -> list[dict]:
    questions: list[dict] = []
    for level in ("A0", "A1", "A2", "B1", "B2"):
        rows = list(con.execute(
            """SELECT e.id,e.level,e.prompt,e.options_json,e.answers_json,e.explanation_vi,
                      l.topic,l.title FROM grammar_exercises e JOIN grammar_lessons l ON l.id=e.lesson_id
               WHERE e.published=1 AND l.published=1 AND e.kind='multiple_choice' AND e.level=?
               ORDER BY l.sequence,e.sequence,e.id""", (level,)
        ))
        for row in _spread(rows, 20 if level in {"A0", "A1"} else 40):
            questions.append(_question(
                f"internal:grammar:{row['id']}", "multiple_choice", row["level"], "grammar",
                row["topic"], row["prompt"], json.loads(row["answers_json"]),
                row["explanation_vi"], {"options": json.loads(row["options_json"]),
                "lesson_title": row["title"]}, "grammar_exercise", row["id"],
                ["placement", "grammar", "daily_review"],
            ))

    for skill, kind, question_type in (("reading", "reading_comprehension", "reading"),
                                        ("listening", "multiple_choice", "listening")):
        for row in con.execute(
            """SELECT q.id,q.prompt,q.options_json,q.answers_json,q.explanation_vi,
                      l.id lesson_id,l.level,l.title,l.content_en,l.transcript_en
               FROM skill_questions q JOIN skill_lessons l ON l.id=q.lesson_id
               WHERE l.published=1 AND l.skill=? AND q.kind=? ORDER BY l.level,l.sequence,q.sequence""",
            (skill, kind),
        ):
            payload = {"options": json.loads(row["options_json"]), "lesson_title": row["title"]}
            if skill == "reading": payload["passage"] = row["content_en"]
            else: payload["transcript"] = row["transcript_en"]
            questions.append(_question(
                f"internal:{skill}:{row['id']}", question_type, row["level"], skill,
                row["title"], row["prompt"], json.loads(row["answers_json"]),
                row["explanation_vi"], payload, "skill_question", row["id"],
                ["placement", skill],
            ))

    for level in ("A2", "B1", "B2"):
        rows = list(con.execute(
            """SELECT id,word,meaning,pos,topic,license FROM library_words
               WHERE reviewed=1 AND stage=? AND trim(meaning)<>'' AND trim(pos)<>'' ORDER BY id""", (level,)
        ))
        eligible = [row for row in rows if sum(
            item["id"] != row["id"] and item["pos"] == row["pos"]
            and item["meaning"].casefold() != row["meaning"].casefold() for item in rows
        ) >= 3]
        for row in _spread(eligible, 30):
            distractors = [item for item in rows if item["id"] != row["id"] and item["pos"] == row["pos"]
                           and item["meaning"].casefold() != row["meaning"].casefold()]
            start = row["id"] % max(len(distractors), 1)
            distractors = (distractors[start:] + distractors[:start])[:3]
            if len(distractors) < 3:
                continue
            options = [row["meaning"], *(item["meaning"] for item in distractors)]
            rotation = row["id"] % 4
            options = options[rotation:] + options[:rotation]
            questions.append(_question(
                f"internal:vocabulary:{row['id']}", "multiple_choice", level, "vocabulary",
                row["topic"], f"Từ “{row['word']}” có nghĩa nào?", [row["meaning"]],
                f"“{row['word']}” có nghĩa là “{row['meaning']}”.",
                {"options": options, "word_id": row["id"], "word": row["word"],
                 "upstream_license": row["license"]}, "library_word", row["id"],
                ["placement", "vocabulary", "daily_review"],
            ))
    return questions


def stage_existing_content(database: Path) -> dict:
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    source = _source(); source_key = "speakseed-original-content-v1"
    try:
        questions = collect_existing_questions(con)
        source_hash = hashlib.sha256(canonical(questions).encode()).hexdigest()
        existing = con.execute(
            """SELECT id,status,processed,accepted,rejected FROM content_import_batches
               WHERE source_key=? AND source_version=? AND source_sha256=? AND importer_version='3.0.0'""",
            (source_key, source["dataset_version"], source_hash),
        ).fetchone()
        if existing and existing["status"] == "staged":
            return {"batch_id": existing["id"], "processed": existing["processed"],
                    "accepted": existing["accepted"], "rejected": existing["rejected"],
                    "idempotent_reuse": True}
        columns = ("display_name","owner_name","source_url","dataset_version","license_name",
                   "license_url","commercial_use","attribution","obligations","audit_status",
                   "evidence_url","audited_at","notes")
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            f"INSERT INTO content_sources(source_key,{','.join(columns)}) VALUES({','.join('?' for _ in range(14))}) "
            + "ON CONFLICT(source_key) DO NOTHING", [source_key, *(source[key] for key in columns)])
        batch_id = con.execute(
            """INSERT INTO content_import_batches(source_key,source_version,source_sha256,importer_version,
               status,started_at) VALUES(?,?,?,'3.0.0','running',?)""",
            (source_key, source["dataset_version"], source_hash, now()),
        ).lastrowid
        created = Counter()
        for question in questions:
            payload = {**question["payload"], "contexts": question["contexts"],
                       "ref_type": question["ref_type"], "ref_id": question["ref_id"]}
            record_id = question["stable_id"]
            staging_id = con.execute(
                """INSERT INTO content_staging_records(batch_id,content_type,source_record_id,stable_key,
                   normalized_hash,payload_json,validation_status,quality_status,review_status,created_at)
                   VALUES(?,'question',?,?,?,?,?,'automated_checked','pending',?)""",
                (batch_id, record_id, record_id, hashlib.sha256(canonical(payload).encode()).hexdigest(),
                 canonical(payload), "valid", now()),
            ).lastrowid
            draft_id = con.execute(
                """INSERT INTO question_bank_drafts(staging_record_id,stable_id,question_type,cefr_level,
                   skill,topic,difficulty,prompt,answer_key_json,accepted_answers_json,explanation_vi,
                   explanation_en,context_text,source_key,source_record_id,license_name,quality_status,
                   review_status,published,created_at,updated_at,payload_json,attribution,placement_eligible,
                   lesson_contexts_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?,?,?,1,?)""",
                (staging_id, question["stable_id"], question["question_type"], question["cefr_level"],
                 question["skill"], question["topic"], {"A0":1,"A1":1,"A2":2,"B1":3,"B2":4}[question["cefr_level"]],
                 question["prompt"], canonical(question["answers"]), canonical(question["answers"]),
                 question["explanation_vi"], "", payload.get("passage") or payload.get("transcript") or "",
                 source_key, record_id, source["license_name"], "automated_checked", now(), now(),
                 canonical(payload), source["attribution"], canonical(question["contexts"])),
            ).lastrowid
            for context in question["contexts"]:
                con.execute("""INSERT INTO question_bank_links(question_id,learning_context,ref_type,ref_id)
                    VALUES(?,?,?,?)""", (draft_id, context, question["ref_type"], question["ref_id"]))
            created[(question["question_type"], question["cefr_level"])] += 1
        report = {"batch_id": batch_id, "processed": len(questions), "accepted": len(questions),
                  "rejected": 0, "idempotent_reuse": False,
                  "by_type_level": {f"{key[0]}:{key[1]}": value for key, value in sorted(created.items())},
                  "published": 0, "human_reviewed": 0}
        con.execute("""UPDATE content_import_batches SET status='staged',finished_at=?,checkpoint=?,
                    processed=?,accepted=?,report_json=? WHERE id=?""",
                    (now(), str(len(questions)), len(questions), len(questions), canonical(report), batch_id))
        con.commit()
        return report
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


TOPIC_DRAFTS = {
    "conditional": "Cần dùng đúng dạng động từ trong mệnh đề điều kiện và mệnh đề kết quả như câu sửa.",
    "verb_pattern": "Động từ trong câu yêu cầu mẫu động từ theo sau như trong đáp án chuẩn.",
    "word_choice": "Từ ban đầu không phù hợp với nghĩa cần diễn đạt; dùng lựa chọn trong câu sửa.",
    "word_order": "Cần đặt các thành phần theo trật tự tự nhiên thể hiện trong câu sửa.",
    "collocation": "Cần dùng cụm từ kết hợp tự nhiên như trong đáp án chuẩn.",
    "tense": "Cần chọn thì và dạng động từ phù hợp với mốc thời gian của câu.",
    "preposition": "Cụm từ này đi với giới từ được dùng trong đáp án chuẩn.",
    "countability": "Cần chú ý danh từ đếm được hoặc không đếm được và từ hạn định đi kèm.",
    "modal": "Sau động từ khuyết thiếu, cần dùng dạng động từ theo cấu trúc trong đáp án.",
    "question": "Câu hỏi cần đúng trợ động từ và trật tự từ như trong đáp án.",
    "pronoun": "Cần dùng đúng dạng đại từ theo chức năng chủ ngữ hoặc tân ngữ.",
    "article": "Cần dùng mạo từ phù hợp trước danh từ trong ngữ cảnh này.",
}


def add_draft_explanations(database: Path) -> dict:
    con = sqlite3.connect(database, timeout=30); con.row_factory = sqlite3.Row
    changed = 0
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in con.execute("""SELECT * FROM question_bank_drafts
            WHERE source_key='elispeak-common-mistakes' AND trim(explanation_vi)='' AND published=0"""):
            answer = json.loads(row["answer_key_json"])[0]
            explanation = "[Bản nháp chờ người duyệt] " + TOPIC_DRAFTS.get(
                row["topic"], "Cần sửa cấu trúc theo đáp án chuẩn.") + f" Câu sửa: “{answer}”"
            before = {"explanation_vi": row["explanation_vi"], "review_status": row["review_status"]}
            after = {"explanation_vi": explanation, "review_status": "pending"}
            stamp = now()
            con.execute("UPDATE question_bank_drafts SET explanation_vi=?,review_status='pending',updated_at=? WHERE id=?",
                        (explanation, stamp, row["id"]))
            con.execute("""INSERT INTO question_draft_revisions(question_id,editor_name,reason,before_json,after_json,edited_at)
                           VALUES(?,'automated:phase3-draft','Add transparent Vietnamese draft explanation',?,?,?)""",
                        (row["id"], canonical(before), canonical(after), stamp))
            changed += 1
        con.commit(); return {"draft_explanations_added": changed, "human_reviewed": 0}
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def _issue(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _norm(value: object) -> str:
    return " ".join(re.findall(r"[\w']+", str(value).casefold().replace("’", "'")))


def audit_question(row) -> list[dict]:
    issues: list[dict] = []
    answers = json.loads(row["accepted_answers_json"] or "[]")
    payload = json.loads(row["payload_json"] or "{}")
    if not row["prompt"].strip(): issues.append(_issue("missing_prompt", "error", "Thiếu đề bài"))
    if not answers or not all(str(value).strip() for value in answers): issues.append(_issue("missing_answer", "error", "Thiếu đáp án"))
    if not row["explanation_vi"].strip(): issues.append(_issue("missing_explanation_vi", "error", "Thiếu giải thích tiếng Việt"))
    if row["explanation_vi"].startswith("[Bản nháp"):
        issues.append(_issue("draft_explanation_requires_human_review", "warning", "Giải thích tiếng Việt mới là bản nháp tự động"))
    learner_text = " ".join((str(row["prompt"] or ""), str(row["context_text"] or ""),
                             " ".join(str(value) for value in answers)))
    if re.search(r"(?i)\b(shut up|idiot|stupid|damn)\b", learner_text):
        issues.append(_issue("potentially_unsuitable_tone", "warning",
                             "Ngôn ngữ có thể không phù hợp bài học; cần người duyệt xem ngữ cảnh và sắc thái"))
    if not row["license_name"].strip() or not row["source_key"].strip():
        issues.append(_issue("missing_provenance", "error", "Thiếu nguồn hoặc giấy phép"))
    if row["question_type"] == "multiple_choice" or (row["question_type"] in {"reading", "listening"} and payload.get("options")):
        options = payload.get("options", [])
        normalized = [_norm(value) for value in options]
        if len(options) < 2: issues.append(_issue("too_few_options", "error", "Cần ít nhất hai lựa chọn"))
        if len(normalized) != len(set(normalized)): issues.append(_issue("duplicate_options", "error", "Có lựa chọn trùng"))
        if answers and not any(_norm(answer) in normalized for answer in answers):
            issues.append(_issue("answer_not_in_options", "error", "Đáp án không nằm trong lựa chọn"))
    if row["question_type"] == "fill_blank":
        if "___" not in row["prompt"]: issues.append(_issue("missing_blank", "error", "Đề không có vị trí trống"))
        if len(answers) == 1 and re.fullmatch(r"(?i)(a|an|the|in|on|at|to|for|of)", str(answers[0])):
            issues.append(_issue("possible_equivalent_fill_answer", "warning", "Từ chức năng có thể cần thêm ngữ cảnh hoặc đáp án tương đương"))
    if row["question_type"] == "sentence_ordering":
        tokens = payload.get("tokens", [])
        target = re.findall(r"[\w']+", str(answers[0]).casefold()) if answers else []
        token_words = [word for token in tokens for word in re.findall(r"[\w']+", str(token).casefold())]
        if Counter(target) != Counter(token_words): issues.append(_issue("ordering_token_mismatch", "error", "Token không khớp đáp án"))
        if len(token_words) != len(set(token_words)):
            issues.append(_issue("repeated_ordering_token", "warning", "Token lặp cần kiểm tra thao tác sắp xếp"))
        if len(answers) == 1 and not payload.get("alternative_order_reviewed") and re.search(r"(?i)\b(and|or|but|also|sometimes|usually)\b", str(answers[0])):
            issues.append(_issue("possible_alternative_order", "warning", "Cần kiểm tra có trật tự câu đúng khác hay không"))
    if row["skill"] == "listening":
        transcript = str(payload.get("transcript") or row["context_text"] or "").strip()
        if not transcript: issues.append(_issue("missing_transcript", "error", "Thiếu transcript"))
        elif len(transcript) > 500 or re.search(r"https?://|<[^>]+>", transcript):
            issues.append(_issue("speech_synthesis_unsafe", "error", "Transcript không phù hợp Web Speech API"))
    if row["skill"] == "reading" and not str(payload.get("passage") or row["context_text"] or "").strip():
        issues.append(_issue("missing_reading_passage", "error", "Thiếu bài đọc"))
    if row["question_type"] == "error_correction" and len(answers) == 1 and not payload.get("single_answer_reviewed"):
        issues.append(_issue("single_accepted_correction", "warning", "Cần người duyệt kiểm tra các cách sửa tương đương"))
    return issues


def audit_bank(database: Path) -> dict:
    con = sqlite3.connect(database, timeout=30); con.row_factory = sqlite3.Row
    counts = Counter(); issue_counts = Counter()
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in con.execute("SELECT * FROM question_bank_drafts ORDER BY id"):
            issues = audit_question(row)
            status = "fail" if any(item["severity"] == "error" for item in issues) else "warn" if issues else "pass"
            con.execute("""INSERT INTO question_qa_results(question_id,tool_version,overall_status,issues_json,checked_at)
                VALUES(?,?,?,?,?) ON CONFLICT(question_id) DO UPDATE SET tool_version=excluded.tool_version,
                overall_status=excluded.overall_status,issues_json=excluded.issues_json,checked_at=excluded.checked_at""",
                (row["id"], QA_VERSION, status, canonical(issues), now()))
            counts[status] += 1
            issue_counts.update(item["code"] for item in issues)
        con.commit()
        return {"questions": sum(counts.values()), "qa_status": dict(counts),
                "issues": dict(issue_counts), "human_reviewed": 0, "published": 0}
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("stage-existing", "draft-explanations", "audit"))
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    action = {"stage-existing": stage_existing_content,
              "draft-explanations": add_draft_explanations,
              "audit": audit_bank}[args.command]
    print(json.dumps(action(args.database), ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
