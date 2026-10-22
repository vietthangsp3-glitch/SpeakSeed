"""Idempotently import the original A0-B2 four-skills curriculum."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from migrations import run_migrations
from tools.skills_catalog import LEVELS, LISTENING, READING, SPEAKING_TOPICS, WRITING_TASKS

VERSION = "1.0.0"
SOURCE = "SpeakSeed original four-skills curriculum v1"
LICENSE = "Project-owned original content"
REVIEW_STATUS = "automated_checked"
TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
STOPWORDS = {"a","an","the","i","you","he","she","it","we","they","my","your","our","their",
             "am","is","are","was","were","be","been","do","does","did","have","has","had","to",
             "of","in","on","at","by","for","from","with","and","but","or","if","than","as","not",
             "who","what","where","when","why","how","which","whose","whom"}


def slugify(text: str) -> str:
    import unicodedata
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def _lesson_rows():
    rows = []
    questions = []
    level_sequence = Counter()
    for offset, item in enumerate(LISTENING, 1):
        level_sequence[("listening", item["level"])] += 1
        lesson_id = 1000 + offset
        rows.append({"id": lesson_id, "skill": "listening", "level": item["level"],
                     "sequence": level_sequence[("listening", item["level"])], "title": item["title"],
                     "instructions_vi": item["vi"], "content_en": "", "transcript_en": item["text"],
                     "metadata": {"audio_delivery":"on_demand_tts","question_count":len(item["questions"])}})
        for seq, question in enumerate(item["questions"], 1):
            questions.append({**question, "id": 10000 + (offset - 1) * 3 + seq,
                              "lesson_id": lesson_id, "sequence": seq})
    for offset, item in enumerate(READING, 1):
        level, title, passage, instructions, raw_questions = item
        level_sequence[("reading", level)] += 1
        lesson_id = 2000 + offset
        rows.append({"id": lesson_id, "skill": "reading", "level": level,
                     "sequence": level_sequence[("reading", level)], "title": title,
                     "instructions_vi": instructions, "content_en": passage, "transcript_en": "",
                     "metadata": {"question_count":len(raw_questions)}})
        for seq, (prompt, answers, options, explanation) in enumerate(raw_questions, 1):
            questions.append({"id": 20000 + (offset - 1) * 3 + seq, "lesson_id": lesson_id,
                              "sequence": seq, "kind": "reading_comprehension", "prompt": prompt,
                              "answers": answers, "options": options, "explanation_vi": explanation})
    for offset, item in enumerate(SPEAKING_TOPICS, 1):
        level, title, instructions, scenario = item
        level_sequence[("speaking", level)] += 1
        rows.append({"id": 3000 + offset, "skill": "speaking", "level": level,
                     "sequence": level_sequence[("speaking", level)], "title": title,
                     "instructions_vi": instructions, "content_en": scenario, "transcript_en": "",
                     "metadata": {"minimum_turns":2,"evaluation_dimensions":["grammar","vocabulary","naturalness","task_completion"]}})
    for offset, item in enumerate(WRITING_TASKS, 1):
        level, title, genre, minimum, maximum, instructions, prompt = item
        level_sequence[("writing", level)] += 1
        rows.append({"id": 4000 + offset, "skill": "writing", "level": level,
                     "sequence": level_sequence[("writing", level)], "title": title,
                     "instructions_vi": instructions, "content_en": prompt, "transcript_en": "",
                     "metadata": {"genre":genre,"min_words":minimum,"max_words":maximum,"ai_submissions_per_hour":10}})
    for row in rows:
        row["slug"] = f"{row['skill']}-{row['level'].lower()}-{row['sequence']}-{slugify(row['title'])}"
    return rows, questions


def validate(lessons, questions):
    errors = []
    expected = Counter({(skill, level): 3 for skill in ("listening","reading","speaking","writing") for level in LEVELS})
    if Counter((x["skill"], x["level"]) for x in lessons) != expected:
        errors.append("each skill and CEFR level must have exactly three lessons")
    if len(lessons) != 60:
        errors.append(f"expected 60 lessons, found {len(lessons)}")
    if len(questions) != 90:
        errors.append(f"expected 90 objective questions, found {len(questions)}")
    kinds = Counter(x["kind"] for x in questions)
    if kinds != Counter({"multiple_choice":15,"fill_blank":15,"dictation":15,"reading_comprehension":45}):
        errors.append(f"unexpected question distribution: {dict(kinds)}")
    if len({x["slug"] for x in lessons}) != len(lessons):
        errors.append("lesson slugs are not unique")
    for item in lessons:
        if not all(str(item.get(key, "")).strip() for key in ("title","instructions_vi","content_en" if item["skill"] != "listening" else "transcript_en")):
            errors.append(f"lesson {item['id']} is incomplete")
        if item["skill"] == "listening" and len(item["transcript_en"]) > 500:
            errors.append(f"listening lesson {item['id']} exceeds the TTS request limit")
    for item in questions:
        if not item["answers"] or not item["prompt"].strip() or not item["explanation_vi"].strip():
            errors.append(f"question {item['id']} is incomplete")
        if item["kind"] in ("multiple_choice","reading_comprehension") and len(item["options"]) < 3:
            errors.append(f"question {item['id']} lacks plausible options")
        if item["options"]:
            canonical = lambda value: " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
            if not any(canonical(answer) == canonical(option)
                       for answer in item["answers"] for option in item["options"]):
                errors.append(f"question {item['id']} has no accepted answer among its options")
    if errors:
        raise ValueError("; ".join(errors))


def import_skills(database: Path, migrations_dir: Path) -> dict:
    run_migrations(database, migrations_dir)
    lessons, questions = _lesson_rows()
    validate(lessons, questions)
    stamp = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(database, timeout=30)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN IMMEDIATE")
        vocabulary = {row[0]: row[1] for row in con.execute(
            "SELECT normalized_word,id FROM library_words WHERE reviewed=1 AND normalized_word<>''"
        )}
        question_by_lesson = {}
        for item in questions:
            question_by_lesson.setdefault(item["lesson_id"], []).append(item)
        for row in lessons:
            con.execute("""INSERT INTO skill_lessons(id,slug,skill,level,sequence,title,instructions_vi,
                content_en,transcript_en,metadata_json,source,license,review_status,published,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET
                slug=excluded.slug,skill=excluded.skill,level=excluded.level,sequence=excluded.sequence,
                title=excluded.title,instructions_vi=excluded.instructions_vi,content_en=excluded.content_en,
                transcript_en=excluded.transcript_en,metadata_json=excluded.metadata_json,source=excluded.source,
                license=excluded.license,review_status=excluded.review_status,published=1,updated_at=excluded.updated_at""",
                (row["id"],row["slug"],row["skill"],row["level"],row["sequence"],row["title"],
                 row["instructions_vi"],row["content_en"],row["transcript_en"],json.dumps(row["metadata"],ensure_ascii=False),
                 SOURCE,LICENSE,REVIEW_STATUS,stamp))
            con.execute("DELETE FROM skill_lesson_words WHERE lesson_id=?", (row["id"],))
            language = " ".join([row["content_en"],row["transcript_en"],*(q["prompt"] for q in question_by_lesson.get(row["id"],[]))]).lower().replace("’", "'")
            word_ids = []
            for token in TOKEN_RE.findall(language):
                normalized = token.replace("'", "")
                if normalized not in STOPWORDS and normalized in vocabulary and vocabulary[normalized] not in word_ids:
                    word_ids.append(vocabulary[normalized])
            con.executemany("INSERT OR IGNORE INTO skill_lesson_words(lesson_id,word_id) VALUES(?,?)",
                            ((row["id"], word_id) for word_id in word_ids[:15]))
        for row in questions:
            con.execute("""INSERT INTO skill_questions(id,lesson_id,kind,sequence,prompt,options_json,answers_json,explanation_vi)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET lesson_id=excluded.lesson_id,
                kind=excluded.kind,sequence=excluded.sequence,prompt=excluded.prompt,
                options_json=excluded.options_json,answers_json=excluded.answers_json,explanation_vi=excluded.explanation_vi""",
                (row["id"],row["lesson_id"],row["kind"],row["sequence"],row["prompt"],
                 json.dumps(row["options"],ensure_ascii=False),json.dumps(row["answers"],ensure_ascii=False),row["explanation_vi"]))
        con.commit()
        linked = con.execute("SELECT COUNT(*) FROM skill_lesson_words").fetchone()[0]
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"version":VERSION,"lessons":len(lessons),"objective_questions":len(questions),
            "by_skill":dict(Counter(x["skill"] for x in lessons)),
            "by_level":dict(Counter(x["level"] for x in lessons)),
            "question_kinds":dict(Counter(x["kind"] for x in questions)),
            "vocabulary_links":linked,"source":SOURCE,"license":LICENSE,"review_status":REVIEW_STATUS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "speakseed.db")
    parser.add_argument("--migrations", type=Path, default=PROJECT_ROOT / "migrations")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    lessons, questions = _lesson_rows()
    validate(lessons, questions)
    report = {"lessons":len(lessons),"objective_questions":len(questions),"review_status":REVIEW_STATUS} if args.dry_run else import_skills(args.database,args.migrations)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
