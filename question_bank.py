"""Published-only question-bank adapters shared by placement and lesson APIs."""
from __future__ import annotations

import json
import random
import re
from collections import defaultdict

LEVELS = ("A0", "A1", "A2", "B1", "B2")
CONTEXTS = {"placement", "vocabulary", "grammar", "listening", "reading", "daily_review"}


def normalize_answer(value: str) -> str:
    return " ".join(re.findall(r"[\w']+", str(value).casefold().replace("’", "'")))


def _json(value: str, fallback):
    try:
        parsed = json.loads(value)
        return parsed
    except (TypeError, ValueError):
        return fallback


def published_rows(con, context: str, *, level: str | None = None, limit: int = 100) -> list:
    if context not in CONTEXTS:
        raise ValueError("Invalid learning context")
    params: list = [context]
    where = ["d.published=1", "d.review_status='human_reviewed'", "q.overall_status='pass'",
             "EXISTS(SELECT 1 FROM question_bank_links l WHERE l.question_id=d.id AND l.learning_context=?)"]
    if level:
        where.append("d.cefr_level=?"); params.append(level)
    params.append(limit)
    return list(con.execute(
        """SELECT d.* FROM question_bank_drafts d
           JOIN question_qa_results q ON q.question_id=d.id
           WHERE """ + " AND ".join(where) + " ORDER BY d.cefr_level,d.difficulty,d.id LIMIT ?", params
    ).fetchall())


def internal_item(row) -> dict:
    payload = _json(row["payload_json"], {})
    answers = _json(row["accepted_answers_json"], []) or _json(row["answer_key_json"], [])
    question_type = row["question_type"]
    skill = row["skill"]
    section = skill if skill in {"grammar", "vocabulary", "listening", "reading"} else question_type
    if question_type == "fill_blank": section = "fill_blank"
    if question_type == "sentence_ordering": section = "sentence_ordering"
    item = {
        "key": f"bank:{row['id']}", "question_bank_id": row["id"],
        "section": section, "domain": skill, "kind": question_type,
        "level": row["cefr_level"], "topic": row["topic"], "prompt": row["prompt"],
        "options": payload.get("options", []), "answers": answers,
        "explanation_vi": row["explanation_vi"], "source": row["source_key"],
        "license": row["license_name"], "review_status": row["review_status"],
    }
    if question_type == "sentence_ordering": item["tokens"] = payload.get("tokens", [])
    if skill == "listening":
        item["audio_text"] = payload.get("transcript", row["context_text"])
        item["transcript_en"] = payload.get("transcript", row["context_text"])
    if skill == "reading": item["passage_en"] = payload.get("passage", row["context_text"])
    return item


def public_item(row) -> dict:
    item = internal_item(row)
    for key in ("answers", "explanation_vi", "audio_text", "transcript_en"):
        item.pop(key, None)
    return item


def check(row, answer: str) -> dict:
    item = internal_item(row)
    correct = any(normalize_answer(answer) == normalize_answer(expected) for expected in item["answers"])
    result = {"correct": correct, "accepted_answers": item["answers"],
              "explanation_vi": item["explanation_vi"]}
    if item["domain"] == "listening": result["transcript_en"] = item.get("transcript_en", "")
    if item["domain"] == "reading": result["passage_en"] = item.get("passage_en", "")
    return result


def placement_form(con, excluded_keys: set[str] | None = None, rng=None) -> list[dict] | None:
    """Return a balanced published form, or None so the legacy form stays active."""
    try:
        rows = published_rows(con, "placement", limit=1000)
    except Exception:
        return None
    items = [internal_item(row) for row in rows if row["placement_eligible"]]
    by_level: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["level"] in LEVELS:
            by_level[item["level"]].append(item)
    quotas = {
        "A0": {"grammar": 3, "vocabulary": 0, "listening": 2, "fill_blank": 1, "sentence_ordering": 1, "reading": 1},
        "A1": {"grammar": 1, "vocabulary": 2, "listening": 2, "fill_blank": 1, "sentence_ordering": 1, "reading": 1},
        "A2": {"grammar": 1, "vocabulary": 1, "listening": 2, "fill_blank": 2, "sentence_ordering": 1, "reading": 1},
        "B1": {"grammar": 1, "vocabulary": 1, "listening": 1, "fill_blank": 2, "sentence_ordering": 1, "reading": 2},
        "B2": {"grammar": 1, "vocabulary": 1, "listening": 1, "fill_blank": 2, "sentence_ordering": 2, "reading": 1},
    }
    selected = []
    excluded = excluded_keys or set()
    picker = rng or random.SystemRandom()
    for level in LEVELS:
        for section, count in quotas[level].items():
            pool = [item for item in by_level[level] if item["section"] == section]
            if len(pool) < count:
                return None
            unseen = [item for item in pool if item["key"] not in excluded]
            seen = [item for item in pool if item["key"] in excluded]
            picker.shuffle(unseen); picker.shuffle(seen)
            selected.extend((unseen + seen)[:count])
    if len(selected) != 40:
        return None
    picker.shuffle(selected)
    return selected
