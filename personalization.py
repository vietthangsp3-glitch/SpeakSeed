"""Placement, dashboard and evidence-based learning-path helpers."""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone

LEVELS = ("A0", "A1", "A2", "B1", "B2")
LEVEL_RANK = {level: index for index, level in enumerate(LEVELS)}
PLACEMENT_LIMITATION = (
    "Kết quả chỉ là gợi ý xếp lớp nhanh dựa trên 25 câu từ vựng và ngữ pháp. "
    "Bài kiểm tra không đo đầy đủ nghe, nói, đọc, viết và không phải chứng chỉ CEFR."
)


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", str(text).casefold().replace("’", "'")))


def ensure_profile(con, user_id: int, stamp: str) -> dict:
    con.execute(
        "INSERT OR IGNORE INTO learner_profiles(user_id,updated_at) VALUES(?,?)",
        (user_id, stamp),
    )
    return dict(con.execute("SELECT * FROM learner_profiles WHERE user_id=?", (user_id,)).fetchone())


def placement_questions(con) -> list[dict]:
    """Build a deterministic 25-item test from published, reviewed content."""
    questions: list[dict] = []
    grammar_by_level: dict[str, list] = defaultdict(list)
    rows = con.execute(
        """SELECT e.id,e.level,e.prompt,e.options_json,e.answers_json
           FROM grammar_exercises e JOIN grammar_lessons l ON l.id=e.lesson_id
           WHERE e.published=1 AND l.published=1 AND e.kind='multiple_choice'
           ORDER BY e.level,l.sequence,e.sequence"""
    ).fetchall()
    for row in rows:
        grammar_by_level[row["level"]].append(row)
    for level in LEVELS:
        pool = grammar_by_level[level]
        if len(pool) < 3:
            raise RuntimeError(f"Không đủ câu grammar placement cho {level}")
        indexes = (0, len(pool) // 2, len(pool) - 1)
        for row in (pool[index] for index in indexes):
            questions.append({
                "key": f"grammar:{row['id']}", "domain": "grammar", "level": level,
                "prompt": row["prompt"], "options": json.loads(row["options_json"]),
                "answers": json.loads(row["answers_json"]),
            })

    # CEFR-J vocabulary starts at A1, so A0 is assessed by grammar only.
    vocab_targets = {"A1": 3, "A2": 3, "B1": 2, "B2": 2}
    for level, target in vocab_targets.items():
        rows = con.execute(
            """SELECT id,word,meaning,pos FROM library_words
               WHERE reviewed=1 AND stage=? ORDER BY quality_score DESC,id""",
            (level,),
        ).fetchall()
        if len(rows) < 12:
            raise RuntimeError(f"Không đủ từ placement cho {level}")
        step = max(1, len(rows) // target)
        selected = [rows[min(i * step + step // 2, len(rows) - 1)] for i in range(target)]
        for offset, row in enumerate(selected):
            distractors = con.execute(
                """SELECT meaning FROM library_words
                   WHERE reviewed=1 AND stage=? AND id<>? AND meaning<>? AND pos=?
                   GROUP BY meaning ORDER BY MIN(id) LIMIT 3 OFFSET ?""",
                (level, row["id"], row["meaning"], row["pos"], offset * 3),
            ).fetchall()
            if len(distractors) < 3:
                distractors = con.execute(
                    """SELECT meaning FROM library_words
                       WHERE reviewed=1 AND stage=? AND id<>? AND meaning<>?
                       GROUP BY meaning ORDER BY MIN(id) LIMIT 3""",
                    (level, row["id"], row["meaning"]),
                ).fetchall()
            options = [row["meaning"], *[x["meaning"] for x in distractors]]
            # Deterministic rotation prevents the correct option always being first.
            rotation = row["id"] % len(options)
            options = options[rotation:] + options[:rotation]
            questions.append({
                "key": f"vocab:{row['id']}", "domain": "vocabulary", "level": level,
                "prompt": f"Từ “{row['word']}” có nghĩa nào?", "options": options,
                "answers": [row["meaning"]],
            })
    questions.sort(key=lambda item: (LEVEL_RANK[item["level"]], item["domain"], item["key"]))
    if len(questions) != 25:
        raise RuntimeError(f"Placement test phải có 25 câu, hiện có {len(questions)}")
    return questions


def public_questions(questions: list[dict]) -> list[dict]:
    return [{key: value for key, value in item.items() if key != "answers"} for item in questions]


def score_placement(questions: list[dict], submitted: list[dict]) -> dict:
    expected = {item["key"]: item for item in questions}
    answers = {item.get("question_key"): item.get("answer", "") for item in submitted}
    if len(answers) != len(submitted) or set(answers) != set(expected):
        raise ValueError("Phải trả lời đúng một lần cho toàn bộ 25 câu")
    detail = {}
    total_correct = 0
    checked = []
    for level in LEVELS:
        level_questions = [item for item in questions if item["level"] == level]
        correct = 0
        for item in level_questions:
            is_correct = any(normalize(answers[item["key"]]) == normalize(value) for value in item["answers"])
            correct += int(is_correct)
            checked.append({"question_key": item["key"], "answer": answers[item["key"]], "correct": is_correct})
        total_correct += correct
        detail[level] = {"correct": correct, "total": len(level_questions), "accuracy": round(correct / len(level_questions), 3)}

    # Recommend the first level not yet securely demonstrated. This is placement,
    # not a claim that the learner has certified mastery of lower levels.
    recommended = "A0"
    thresholds = {"A0": 0.5, "A1": 0.6, "A2": 0.6, "B1": 0.6, "B2": 0.7}
    for index, level in enumerate(LEVELS):
        if detail[level]["accuracy"] < thresholds[level]:
            recommended = level
            break
        recommended = LEVELS[min(index + 1, len(LEVELS) - 1)]
    return {
        "total_correct": total_correct, "total": len(questions),
        "accuracy": round(total_correct / len(questions), 3),
        "by_level": detail, "recommended_level": recommended,
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
    return {
        "profile": {key: profile[key] for key in ("recommended_level", "current_level", "daily_goal_minutes", "timezone", "placement_completed_at")},
        "level": level, "lessons": lessons, "next_lesson": next_lesson,
        "skill_paths": skill_paths,
        "weak_skills": weak_skills(con, user_id),
        "unlock_rule": "Mỗi chuỗi bài mở từ bài đầu. Bài tiếp theo chỉ được đề xuất sau khi backend có bằng chứng hoàn thành bài trước.",
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
            "evidence_note": "Chỉ hoạt động đã được backend ghi nhận mới được tính hoàn thành. Ở A0–A1, Speaking và Writing AI là tùy chọn, không nằm trong kế hoạch bắt buộc."}


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
    path = learning_path(con, user_id, stamp)
    return {
        "profile": {"current_level": profile["current_level"], "recommended_level": profile["recommended_level"],
                    "daily_goal_minutes": profile["daily_goal_minutes"]},
        "metrics": {"learned_words": vocabulary["learned"], "due_words": vocabulary["due"],
                    "accuracy": round(correct / attempts, 3) if attempts else None,
                    "grammar_completed_lessons": completed_lessons, "grammar_total_lessons": 100,
                    "streak_days": streak, "skills": skill_metrics},
        "daily_plan": daily_plan(con, user_id, stamp),
        "weak_skills": path["weak_skills"], "next_lesson": path["next_lesson"],
        "accuracy_note": "Độ chính xác chỉ tính các lượt đã được backend chấm; chưa có dữ liệu thì hiển thị chưa đủ dữ liệu.",
    }
