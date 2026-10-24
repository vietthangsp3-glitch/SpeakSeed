"""Placement, dashboard and evidence-based learning-path helpers."""
from __future__ import annotations

import json
import math
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timezone

from question_bank import placement_form

LEVELS = ("A0", "A1", "A2", "B1", "B2")
LEVEL_RANK = {level: index for index, level in enumerate(LEVELS)}
PLACEMENT_LIMITATION = (
    "Kết quả là ước tính nội bộ từ 40 câu grammar, vocabulary, listening và reading. "
    "Bài này không đánh giá speaking hay writing tự do và không phải chứng chỉ CEFR."
)

PLACEMENT_SECTION_WEIGHTS = {
    "grammar": .20, "vocabulary": .10, "listening": .25,
    "fill_blank": .15, "sentence_ordering": .10, "reading": .20,
}


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", str(text).casefold().replace("’", "'")))


def ensure_profile(con, user_id: int, stamp: str) -> dict:
    con.execute(
        "INSERT OR IGNORE INTO learner_profiles(user_id,updated_at) VALUES(?,?)",
        (user_id, stamp),
    )
    return dict(con.execute("SELECT * FROM learner_profiles WHERE user_id=?", (user_id,)).fetchone())


def _sample(rows: list, count: int, rng: random.Random, excluded: set[str], key_prefix: str) -> list:
    """Prefer unseen records, then fill from the complete reviewed pool."""
    if len(rows) < count:
        raise RuntimeError(f"Không đủ câu hỏi kiểm tra: cần {count}, có {len(rows)}")
    unseen = [row for row in rows if f"{key_prefix}:{row['id']}" not in excluded]
    seen = [row for row in rows if f"{key_prefix}:{row['id']}" in excluded]
    rng.shuffle(unseen); rng.shuffle(seen)
    return (unseen + seen)[:count]


def _grammar_items(con, kind: str, targets: dict[str, int], section: str,
                   rng: random.Random, excluded: set[str]) -> list[dict]:
    output = []
    for level, target in targets.items():
        rows = con.execute(
            """SELECT e.id,e.lesson_id,e.level,e.prompt,e.options_json,e.answers_json,
                      e.explanation_vi,e.source,e.review_status,l.title,l.topic
               FROM grammar_exercises e JOIN grammar_lessons l ON l.id=e.lesson_id
               WHERE e.published=1 AND l.published=1 AND e.kind=? AND e.level=?
               ORDER BY l.sequence,e.sequence,e.id""", (kind, level)
        ).fetchall()
        for row in _sample(list(rows), target, rng, excluded, section):
            answers = json.loads(row["answers_json"])
            item = {
                "key": f"{section}:{row['id']}", "section": section,
                "domain": "grammar", "kind": kind, "level": level,
                "topic": row["topic"], "prompt": row["prompt"],
                "options": json.loads(row["options_json"]), "answers": answers,
                "explanation_vi": row["explanation_vi"], "source": row["source"],
                "review_status": row["review_status"], "lesson_id": row["lesson_id"],
                "lesson_title": row["title"],
            }
            if kind == "sentence_ordering":
                tail = row["prompt"].rsplit(":", 1)[-1]
                item["tokens"] = [token.strip() for token in tail.split("/") if token.strip()]
            if kind == "fill_blank":
                item["completed_sentence"] = row["prompt"].replace("___", answers[0])
            output.append(item)
    return output


def placement_questions(con, excluded_keys: set[str] | None = None, seed: int | None = None) -> list[dict]:
    """Build a randomized, balanced 40-item form, preferring unseen questions."""
    excluded = excluded_keys or set()
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    if os.getenv("QUESTION_BANK_PLACEMENT_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
        bank_form = placement_form(con, excluded_keys=excluded, rng=rng)
        if bank_form is not None:
            return bank_form
    questions = _grammar_items(
        con, "multiple_choice", {"A0": 3, "A1": 1, "A2": 1, "B1": 1, "B2": 1}, "grammar", rng, excluded
    )

    # The reviewed CEFR vocabulary bank starts at A1. A0 evidence comes from
    # grammar/listening/reading instead of inventing A0 vocabulary records.
    vocabulary_targets = {"A1": 2, "A2": 1, "B1": 1, "B2": 1}
    for level, target in vocabulary_targets.items():
        rows = list(con.execute(
            """SELECT id,word,meaning,pos,topic,source,license,reviewed
               FROM library_words WHERE reviewed=1 AND stage=?
                 AND trim(word)<>'' AND trim(meaning)<>''
               ORDER BY word,id""", (level,)
        ).fetchall())
        for row in _sample(rows, target, rng, excluded, "vocabulary"):
            distractor_pool = [x["meaning"] for x in rows
                               if x["id"] != row["id"] and x["meaning"] != row["meaning"]
                               and (not row["pos"] or not x["pos"] or x["pos"] == row["pos"])]
            distractor_pool = list(dict.fromkeys(distractor_pool))
            if len(distractor_pool) < 3:
                distractor_pool = list(dict.fromkeys(
                    [x["meaning"] for x in rows if x["id"] != row["id"] and x["meaning"] != row["meaning"]]
                ))
            options = [row["meaning"], *rng.sample(distractor_pool, 3)]
            rng.shuffle(options)
            questions.append({
                "key": f"vocabulary:{row['id']}", "section": "vocabulary",
                "domain": "vocabulary", "kind": "multiple_choice", "level": level,
                "topic": row["topic"], "prompt": f"Từ “{row['word']}” có nghĩa nào?",
                "options": options, "answers": [row["meaning"]],
                "explanation_vi": f"“{row['word']}” có nghĩa là “{row['meaning']}”.",
                "source": row["source"], "license": row["license"],
                "review_status": "automated_checked", "word_id": row["id"],
            })

    listening_targets = {"A0": 2, "A1": 2, "A2": 2, "B1": 1, "B2": 1}
    for level, target in listening_targets.items():
        by_kind = {}
        for kind in ("multiple_choice", "fill_blank"):
            by_kind[kind] = list(con.execute(
                """SELECT q.id,q.lesson_id,q.kind,q.prompt,q.options_json,q.answers_json,q.explanation_vi,
                          l.title,l.level,l.transcript_en,l.source,l.license,l.review_status
                   FROM skill_questions q JOIN skill_lessons l ON l.id=q.lesson_id
                   WHERE l.skill='listening' AND l.level=? AND l.published=1 AND q.kind=?
                   ORDER BY l.sequence,q.sequence""", (level, kind)
            ).fetchall())
        kinds = ["multiple_choice", "fill_blank"] if target == 2 else ["multiple_choice" if LEVEL_RANK[level] % 2 else "fill_blank"]
        for kind_index, kind in enumerate(kinds):
            pool = by_kind[kind]
            row = _sample(pool, 1, rng, excluded, "listening")[0]
            questions.append({
                "key": f"listening:{row['id']}", "section": "listening", "domain": "listening",
                "kind": "listening_" + row["kind"], "level": level, "topic": row["title"],
                "prompt": row["prompt"], "options": json.loads(row["options_json"]),
                "answers": json.loads(row["answers_json"]), "audio_text": row["transcript_en"],
                "transcript_en": row["transcript_en"], "explanation_vi": row["explanation_vi"],
                "source": row["source"], "license": row["license"],
                "review_status": row["review_status"], "lesson_id": row["lesson_id"],
                "lesson_title": row["title"],
            })

    questions.extend(_grammar_items(
        con, "fill_blank", {"A0": 1, "A1": 1, "A2": 2, "B1": 2, "B2": 2}, "fill_blank", rng, excluded
    ))
    questions.extend(_grammar_items(
        con, "sentence_ordering", {"A0": 1, "A1": 1, "A2": 1, "B1": 1, "B2": 2}, "sentence_ordering", rng, excluded
    ))

    for level, target in {"A0": 1, "A1": 1, "A2": 1, "B1": 2, "B2": 1}.items():
        rows = list(con.execute(
            """SELECT q.id,q.lesson_id,q.prompt,q.options_json,q.answers_json,q.explanation_vi,
                      l.title,l.level,l.content_en,l.source,l.license,l.review_status
               FROM skill_questions q JOIN skill_lessons l ON l.id=q.lesson_id
               WHERE l.skill='reading' AND l.level=? AND l.published=1
               ORDER BY l.sequence,q.sequence""", (level,)
        ).fetchall())
        for row in _sample(rows, target, rng, excluded, "reading"):
            questions.append({
                "key": f"reading:{row['id']}", "section": "reading", "domain": "reading",
                "kind": "reading_comprehension", "level": level, "topic": row["title"],
                "prompt": row["prompt"], "options": json.loads(row["options_json"]),
                "answers": json.loads(row["answers_json"]), "passage_en": row["content_en"],
                "explanation_vi": row["explanation_vi"], "source": row["source"],
                "license": row["license"], "review_status": row["review_status"],
                "lesson_id": row["lesson_id"], "lesson_title": row["title"],
            })

    rng.shuffle(questions)
    if len(questions) != 40:
        raise RuntimeError(f"Bài kiểm tra đầu vào phải có 40 câu, hiện có {len(questions)}")
    return questions


def public_questions(questions: list[dict]) -> list[dict]:
    hidden = {"answers", "explanation_vi", "audio_text", "transcript_en", "completed_sentence"}
    return [{key: value for key, value in item.items() if key not in hidden} for item in questions]


def score_placement(questions: list[dict], submitted: list[dict]) -> dict:
    expected = {item["key"]: item for item in questions}
    responses = {item.get("question_key"): item for item in submitted}
    if len(responses) != len(submitted) or set(responses) != set(expected):
        raise ValueError("Cần trả lời, bỏ qua hoặc báo lỗi audio cho đủ 40 câu")
    if any(item.get("state", "answered") not in ("answered", "skipped", "audio_unavailable")
           for item in responses.values()):
        raise ValueError("Một số câu sắp xếp chưa hoàn tất")
    by_level_raw = {level: {"correct": 0, "total": 0} for level in LEVELS}
    by_section_raw = {name: {"correct": 0, "total": 0, "unavailable": 0} for name in PLACEMENT_SECTION_WEIGHTS}
    topics = defaultdict(lambda: [0, 0])
    checked = []
    for item in questions:
        response = responses[item["key"]]
        state = response.get("state", "answered")
        answer = str(response.get("answer", ""))
        unavailable = state == "audio_unavailable" and item["section"] == "listening"
        is_correct = False if state != "answered" else any(normalize(answer) == normalize(value) for value in item["answers"])
        section = by_section_raw[item["section"]]
        if unavailable:
            section["unavailable"] += 1
        else:
            section["total"] += 1; section["correct"] += int(is_correct)
            by_level_raw[item["level"]]["total"] += 1
            by_level_raw[item["level"]]["correct"] += int(is_correct)
            topics[item["topic"]][1] += 1; topics[item["topic"]][0] += int(is_correct)
        checked.append({
            "question_key": item["key"], "section": item["section"], "kind": item["kind"],
            "level": item["level"], "topic": item["topic"], "prompt": item["prompt"],
            "user_answer": answer, "state": state, "correct": is_correct,
            "correct_answers": item["answers"], "explanation_vi": item["explanation_vi"],
            "completed_sentence": item.get("completed_sentence"),
            "transcript_en": item.get("transcript_en"), "passage_en": item.get("passage_en"),
            "source": item.get("source", ""), "license": item.get("license", ""),
        })
    by_level = {level: {**values, "accuracy": round(values["correct"] / values["total"], 3) if values["total"] else None}
                for level, values in by_level_raw.items()}
    by_section = {name: {**values, "accuracy": round(values["correct"] / values["total"], 3) if values["total"] else None,
                         "weight": PLACEMENT_SECTION_WEIGHTS[name]}
                  for name, values in by_section_raw.items()}
    available_weight = sum(PLACEMENT_SECTION_WEIGHTS[name] for name, value in by_section.items() if value["total"])
    weighted_score = sum((value["accuracy"] or 0) * PLACEMENT_SECTION_WEIGHTS[name]
                         for name, value in by_section.items() if value["total"])
    weighted_score = weighted_score / available_weight if available_weight else 0

    recommended = "A0"
    gates = {"A0": .55, "A1": .58, "A2": .60, "B1": .65}
    for level in ("A0", "A1", "A2", "B1"):
        accuracy = by_level[level]["accuracy"]
        if accuracy is None or accuracy < gates[level]:
            break
        recommended = LEVELS[LEVEL_RANK[level] + 1]
    strong_topics = [{"topic": name, "accuracy": round(ok / total, 3), "total": total}
                     for name, (ok, total) in topics.items() if total and ok / total >= .75]
    weak_topics = [{"topic": name, "accuracy": round(ok / total, 3), "total": total}
                   for name, (ok, total) in topics.items() if total and ok / total < .6]
    recommendations = []
    seen = set()
    for item, result in zip(questions, checked):
        if result["correct"] or result["state"] == "audio_unavailable":
            continue
        key = (item["section"], item.get("lesson_id"), item["topic"])
        if key in seen:
            continue
        seen.add(key)
        recommendations.append({"section": item["section"], "topic": item["topic"],
                                "lesson_id": item.get("lesson_id"), "lesson_title": item.get("lesson_title", "")})
    return {
        "version": 2, "total_correct": sum(x["correct"] for x in by_section_raw.values()),
        "total": sum(x["total"] for x in by_section_raw.values()),
        "question_count": len(questions), "weighted_score": round(weighted_score, 3),
        "by_level": by_level, "by_section": by_section, "recommended_level": recommended,
        "strong_topics": sorted(strong_topics, key=lambda x: (-x["accuracy"], x["topic"]))[:8],
        "weak_topics": sorted(weak_topics, key=lambda x: (x["accuracy"], x["topic"]))[:8],
        "recommendations": recommendations[:8], "details": checked,
        "audio_unavailable": by_section["listening"]["unavailable"],
        "confidence": "reduced" if by_section["listening"]["unavailable"] else "standard",
        "limitation": PLACEMENT_LIMITATION, "checked_answers": checked,
    }


def record_event(con, user_id: int, event_type: str, skill: str, stamp: str, *,
                 ref_type: str = "", ref_id: int | None = None,
                 correct: bool | None = None, evidence: dict | None = None) -> None:
    con.execute(
        """INSERT INTO learning_events(
             user_id,event_type,skill,ref_type,ref_id,correct,evidence_json,occurred_at
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (user_id, event_type, skill, ref_type, ref_id,
         None if correct is None else int(correct), json.dumps(evidence or {}, ensure_ascii=False), stamp),
    )


def weak_skills(con, user_id: int) -> list[dict]:
    rows = []
    for row in con.execute(
        """SELECT e.kind skill,SUM(a.correct) correct,SUM(a.attempts) attempts
           FROM grammar_attempts a JOIN grammar_exercises e ON e.id=a.exercise_id
           WHERE a.user_id=? GROUP BY e.kind HAVING SUM(a.attempts)>=3""", (user_id,)
    ):
        accuracy = row["correct"] / row["attempts"]
        if accuracy < .7:
            rows.append({"area": "grammar", "skill": row["skill"], "accuracy": round(accuracy, 3), "attempts": row["attempts"]})
    for row in con.execute(
        """SELECT w.topic skill,SUM(p.correct) correct,SUM(p.correct+p.wrong) attempts
           FROM progress p JOIN library_words w ON w.id=p.word_id
           WHERE p.user_id=? GROUP BY w.topic HAVING SUM(p.correct+p.wrong)>=3""", (user_id,)
    ):
        accuracy = row["correct"] / row["attempts"]
        if accuracy < .7:
            rows.append({"area": "vocabulary", "skill": row["skill"], "accuracy": round(accuracy, 3), "attempts": row["attempts"]})
    exercise_totals = defaultdict(lambda: [0, 0])
    for row in con.execute("SELECT mode,correct,wrong FROM exercise_progress WHERE user_id=?", (user_id,)):
        exercise_totals[row["mode"]][0] += row["correct"]
        exercise_totals[row["mode"]][1] += row["correct"] + row["wrong"]
    for row in con.execute(
        """SELECT e.mode,r.correct,r.wrong FROM library_results r
           JOIN library_exercises e ON e.id=r.exercise_id WHERE r.user_id=?""", (user_id,)
    ):
        exercise_totals[row["mode"]][0] += row["correct"]
        exercise_totals[row["mode"]][1] += row["correct"] + row["wrong"]
    for skill, (correct, attempts) in exercise_totals.items():
        if attempts >= 3 and correct / attempts < .7:
            rows.append({"area": "skills", "skill": skill, "accuracy": round(correct / attempts, 3), "attempts": attempts})
    for row in con.execute(
        """SELECT l.skill,SUM(a.correct) correct,SUM(a.attempts) attempts
           FROM skill_question_attempts a JOIN skill_questions q ON q.id=a.question_id
           JOIN skill_lessons l ON l.id=q.lesson_id WHERE a.user_id=?
           GROUP BY l.skill HAVING SUM(a.attempts)>=3""", (user_id,)
    ):
        accuracy = row["correct"] / row["attempts"]
        if accuracy < .7:
            rows.append({"area": "four_skills", "skill": row["skill"],
                         "accuracy": round(accuracy, 3), "attempts": row["attempts"]})
    return sorted(rows, key=lambda item: (item["accuracy"], -item["attempts"]))[:6]


def four_skill_paths(con, user_id: int, level: str) -> dict:
    progress = {row["lesson_id"]: dict(row) for row in con.execute(
        "SELECT * FROM skill_progress WHERE user_id=?", (user_id,)
    )}
    paths = {}
    for skill in ("listening", "reading", "speaking", "writing"):
        lessons = []
        previous_completed = True
        for row in con.execute(
            """SELECT id,skill,level,sequence,title,instructions_vi FROM skill_lessons
               WHERE skill=? AND level=? AND published=1 ORDER BY sequence""", (skill, level)
        ):
            saved = progress.get(row["id"], {})
            completed = bool(saved.get("completed", 0))
            lessons.append({**dict(row), "attempted": saved.get("attempted", 0),
                            "correct": saved.get("correct", 0), "completed": completed,
                            "unlocked": previous_completed})
            previous_completed = previous_completed and completed
        paths[skill] = {"lessons": lessons,
                        "next_lesson": next((item for item in lessons if item["unlocked"] and not item["completed"]), None)}
    return paths


def learning_path(con, user_id: int, stamp: str) -> dict:
    profile = ensure_profile(con, user_id, stamp)
    level = profile["current_level"]
    lesson_progress = {row["lesson_id"]: dict(row) for row in con.execute(
        "SELECT * FROM grammar_lesson_progress WHERE user_id=?", (user_id,)
    )}
    lessons = []
    previous_completed = True
    for row in con.execute(
        """SELECT l.id,l.level,l.sequence,l.title,l.topic,l.unit_id,u.sequence unit_sequence
           FROM grammar_lessons l JOIN grammar_units u ON u.id=l.unit_id
           WHERE l.level=? AND l.published=1 ORDER BY u.sequence,l.sequence""", (level,)
    ):
        progress = lesson_progress.get(row["id"], {})
        completed = bool(progress.get("completed", 0))
        lessons.append({**dict(row), "attempted": progress.get("attempted", 0),
                        "correct": progress.get("correct", 0), "completed": completed,
                        "unlocked": previous_completed})
        previous_completed = previous_completed and completed
    next_lesson = next((item for item in lessons if item["unlocked"] and not item["completed"]), None)
    skill_paths = four_skill_paths(con, user_id, level)
    journey = []
    previous_unit_completed = True
    for unit in con.execute(
        "SELECT id,sequence,title,description_vi FROM grammar_units WHERE level=? AND published=1 ORDER BY sequence",
        (level,),
    ):
        unit_lessons = [item for item in lessons if item["unit_id"] == unit["id"]]
        completed_count = sum(item["completed"] for item in unit_lessons)
        completed = bool(unit_lessons) and completed_count == len(unit_lessons)
        status = "completed" if completed else ("in_progress" if previous_unit_completed else "locked")
        activities = [{"kind": "vocabulary", "label": "Từ vựng theo cấp độ", "target": 10}]
        for skill in ("listening", "reading"):
            candidates = skill_paths[skill]["lessons"]
            if candidates:
                activity = candidates[min(unit["sequence"] - 1, len(candidates) - 1)]
                activities.append({"kind": skill, "label": activity["title"],
                                   "lesson_id": activity["id"], "completed": activity["completed"]})
        journey.append({**dict(unit), "status": status, "completed_lessons": completed_count,
                        "total_lessons": len(unit_lessons), "activities": activities})
        previous_unit_completed = previous_unit_completed and completed
    return {
        "profile": {key: profile[key] for key in ("recommended_level", "current_level", "daily_goal_minutes", "timezone", "placement_completed_at")},
        "level": level, "lessons": lessons, "next_lesson": next_lesson,
        "skill_paths": skill_paths, "journey": journey,
        "weak_skills": weak_skills(con, user_id),
        "unlock_rule": "Mỗi chuỗi bắt đầu từ bài đầu tiên. Hoàn thành một bài để mở gợi ý cho bài tiếp theo.",
    }


def _today(stamp: str) -> str:
    return stamp[:10]


def daily_plan(con, user_id: int, stamp: str) -> dict:
    profile = ensure_profile(con, user_id, stamp)
    today = _today(stamp)
    saved = con.execute("SELECT items_json,level FROM daily_plans WHERE user_id=? AND plan_date=?", (user_id, today)).fetchone()
    if saved:
        items = json.loads(saved["items_json"])
        level = saved["level"]
        # The small A0-A1 internal beta focuses on non-AI core study. Existing
        # plans are normalized in place without deleting their learning events.
        if level in ("A0", "A1"):
            items = [item for item in items if item.get("key") not in ("speaking", "writing")]
        present = {item.get("key") for item in items}
        path = learning_path(con, user_id, stamp)
        additions = []
        additions_config = [("reading", "Luyện đọc", "skills")]
        if level not in ("A0", "A1"):
            additions_config.append(("writing", "Luyện viết", "skills"))
        for skill, label, view in additions_config:
            if skill not in present:
                lesson = path["skill_paths"][skill]["next_lesson"]
                additions.append({"key": skill, "label": label, "target": 1 if lesson else 0,
                                  "view": view, "lesson_id": lesson["id"] if lesson else None})
        normalized = items + additions
        if normalized != json.loads(saved["items_json"]):
            items = normalized
            con.execute("UPDATE daily_plans SET items_json=? WHERE user_id=? AND plan_date=?",
                        (json.dumps(items, ensure_ascii=False), user_id, today))
    else:
        level = profile["current_level"]
        due = con.execute("SELECT COUNT(*) FROM progress WHERE user_id=? AND due_at<=?", (user_id, stamp)).fetchone()[0]
        vocab_level = "A1" if level == "A0" else level
        unlearned = con.execute(
            """SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1 AND w.stage=? AND NOT EXISTS(
                 SELECT 1 FROM progress p WHERE p.user_id=? AND p.word_id=w.id)""", (vocab_level, user_id)
        ).fetchone()[0]
        path = learning_path(con, user_id, stamp)
        skill_next = {name: path["skill_paths"][name]["next_lesson"] for name in ("listening","reading","speaking","writing")}
        items = [
            {"key": "vocabulary", "label": "Học từ mới", "target": min(5, unlearned), "view": "learn"},
            {"key": "review", "label": "Ôn từ đến hạn", "target": min(10, due), "view": "learn"},
            {"key": "grammar", "label": "Luyện grammar", "target": 5 if path["next_lesson"] else 0, "view": "grammar", "lesson_id": path["next_lesson"]["id"] if path["next_lesson"] else None},
            {"key": "listening", "label": "Luyện nghe", "target": 1 if skill_next["listening"] else 0, "view": "skills", "lesson_id": skill_next["listening"]["id"] if skill_next["listening"] else None},
            {"key": "reading", "label": "Luyện đọc", "target": 1 if skill_next["reading"] else 0, "view": "skills", "lesson_id": skill_next["reading"]["id"] if skill_next["reading"] else None},
        ]
        if level not in ("A0", "A1"):
            items.extend([
                {"key": "speaking", "label": "AI Speaking", "target": 1 if skill_next["speaking"] else 0, "view": "skills", "lesson_id": skill_next["speaking"]["id"] if skill_next["speaking"] else None},
                {"key": "writing", "label": "Luyện viết", "target": 1 if skill_next["writing"] else 0, "view": "skills", "lesson_id": skill_next["writing"]["id"] if skill_next["writing"] else None},
            ])
        con.execute(
            "INSERT OR IGNORE INTO daily_plans(user_id,plan_date,level,items_json,created_at) VALUES(?,?,?,?,?)",
            (user_id, today, level, json.dumps(items, ensure_ascii=False), stamp),
        )
    counts = {row["event_type"]: row["total"] for row in con.execute(
        """SELECT event_type,COUNT(*) total FROM learning_events
           WHERE user_id=? AND substr(occurred_at,1,10)=? GROUP BY event_type""", (user_id, today)
    )}
    event_map = {"vocabulary": "vocabulary_learning", "review": "vocabulary_review", "grammar": "grammar_answer",
                 "listening": "skill_listening_answer", "reading": "reading_answer",
                 "speaking": "speaking_evaluation", "writing": "writing_submission"}
    output = []
    for item in items:
        completed_count = counts.get(event_map[item["key"]], 0)
        target = item["target"]
        output.append({**item, "completed_count": min(completed_count, target),
                       "completed": target > 0 and completed_count >= target})
    return {"date": today, "level": level, "items": output,
            "completed": all(item["target"] == 0 or item["completed"] for item in output),
            "evidence_note": "Một mục chỉ được đánh dấu hoàn thành sau khi bạn thực hiện hoạt động học. Ở A0–A1, luyện nói và phản hồi viết nâng cao là tùy chọn."}


def dashboard(con, user_id: int, stamp: str) -> dict:
    profile = ensure_profile(con, user_id, stamp)
    vocabulary = con.execute(
        """SELECT COALESCE(SUM(CASE WHEN correct+wrong>0 THEN 1 ELSE 0 END),0) learned,COALESCE(SUM(correct),0) correct,
           COALESCE(SUM(correct+wrong),0) attempts,
           COALESCE(SUM(CASE WHEN due_at<=? THEN 1 ELSE 0 END),0) due
           FROM progress WHERE user_id=?""", (stamp, user_id)
    ).fetchone()
    grammar = con.execute(
        """SELECT COUNT(*) attempted,COALESCE(SUM(completed),0) solved,
           COALESCE(SUM(correct),0) correct,COALESCE(SUM(correct+wrong),0) attempts
           FROM grammar_attempts WHERE user_id=?""", (user_id,)
    ).fetchone()
    core = con.execute(
        "SELECT COALESCE(SUM(correct),0) correct,COALESCE(SUM(correct+wrong),0) attempts FROM exercise_progress WHERE user_id=?",
        (user_id,),
    ).fetchone()
    library = con.execute(
        "SELECT COALESCE(SUM(correct),0) correct,COALESCE(SUM(correct+wrong),0) attempts FROM library_results WHERE user_id=?",
        (user_id,),
    ).fetchone()
    objective_skills = con.execute(
        "SELECT COALESCE(SUM(correct),0) correct,COALESCE(SUM(attempts),0) attempts FROM skill_question_attempts WHERE user_id=?",
        (user_id,),
    ).fetchone()
    skill_metrics = {}
    for skill in ("listening", "reading", "speaking", "writing"):
        row = con.execute("""SELECT COUNT(l.id) total,COALESCE(SUM(p.completed),0) completed
            FROM skill_lessons l LEFT JOIN skill_progress p ON p.lesson_id=l.id AND p.user_id=?
            WHERE l.skill=? AND l.published=1""", (user_id, skill)).fetchone()
        skill_metrics[skill] = {"completed_lessons": row["completed"], "total_lessons": row["total"]}
    completed_lessons = con.execute(
        "SELECT COUNT(*) FROM grammar_lesson_progress WHERE user_id=? AND completed=1", (user_id,)
    ).fetchone()[0]
    mastered_words = con.execute(
        "SELECT COUNT(*) FROM progress WHERE user_id=? AND level>=3", (user_id,)
    ).fetchone()[0]
    correct = vocabulary["correct"] + grammar["correct"] + core["correct"] + library["correct"] + objective_skills["correct"]
    attempts = vocabulary["attempts"] + grammar["attempts"] + core["attempts"] + library["attempts"] + objective_skills["attempts"]
    activity_dates = [row[0] for row in con.execute(
        'SELECT DISTINCT substr(occurred_at,1,10) AS "day" FROM learning_events WHERE user_id=? ORDER BY "day" DESC', (user_id,)
    )]
    today = datetime.fromisoformat(stamp).date()
    streak = 0
    dates = set(activity_dates)
    cursor = today
    # If there is no activity today, a streak through yesterday remains visible.
    if cursor.isoformat() not in dates:
        from datetime import timedelta
        cursor -= timedelta(days=1)
    from datetime import timedelta
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)
    xp_rates = {
        "vocabulary_learning": 5, "vocabulary_review": 3, "grammar_answer": 5,
        "listening_answer": 4, "exercise_answer": 4, "skill_listening_answer": 7,
        "reading_answer": 7, "reading_word_saved": 2, "speaking_evaluation": 10,
        "writing_submission": 10, "speaking_turn": 2, "speaking_live": 10,
    }
    # XP is derived from durable evidence. Replaying the same graded activity does
    # not mint more XP; SRS can earn XP once per word per calendar day.
    awards = {}
    for event in con.execute(
        "SELECT event_type,ref_type,ref_id,correct,occurred_at FROM learning_events WHERE user_id=? ORDER BY occurred_at,id",
        (user_id,),
    ):
        day = event["occurred_at"][:10]
        identity = event["ref_id"] if event["ref_id"] is not None else day
        key = (event["event_type"], event["ref_type"], identity,
               day if event["event_type"] == "vocabulary_review" else "")
        points = xp_rates.get(event["event_type"], 0)
        if event["correct"] == 0:
            points = min(points, 1)
        previous = awards.get(key)
        if previous is None or points > previous[0]:
            awards[key] = (points, day)
    xp_total = sum(points for points, _ in awards.values())
    xp_today = sum(points for points, day in awards.values() if day == today.isoformat())
    daily_xp_goal = max(10, profile["daily_goal_minutes"] * 2)
    achievements = [
        {"key": "first_word", "label": "Hạt mầm đầu tiên", "earned": vocabulary["learned"] >= 1},
        {"key": "ten_words", "label": "10 từ đã học", "earned": vocabulary["learned"] >= 10},
        {"key": "grammar_start", "label": "Bắt đầu ngữ pháp", "earned": completed_lessons >= 1},
        {"key": "streak_3", "label": "Chuỗi 3 ngày", "earned": streak >= 3},
    ]
    path = learning_path(con, user_id, stamp)
    return {
        "profile": {"current_level": profile["current_level"], "recommended_level": profile["recommended_level"],
                    "daily_goal_minutes": profile["daily_goal_minutes"]},
        "metrics": {"learned_words": vocabulary["learned"], "mastered_words": mastered_words,
                    "due_words": vocabulary["due"],
                    "accuracy": round(correct / attempts, 3) if attempts else None,
                    "grammar_completed_lessons": completed_lessons, "grammar_total_lessons": 100,
                    "streak_days": streak, "xp_total": xp_total, "xp_today": xp_today,
                    "daily_xp_goal": daily_xp_goal, "skills": skill_metrics},
        "daily_plan": daily_plan(con, user_id, stamp),
        "weak_skills": path["weak_skills"], "next_lesson": path["next_lesson"],
        "journey": path["journey"], "achievements": achievements,
        "accuracy_note": "Độ chính xác được tính từ các bài đã làm; khi chưa đủ dữ liệu, SpeakSeed sẽ chưa đưa ra nhận xét.",
    }
