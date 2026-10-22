"""Build the A0-B2 grammar curriculum without replacing user or vocabulary data."""
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
from tools.grammar_catalog import LESSONS, LEVEL_NAMES, UNIT_TITLES

VERSION = "1.0.0"
SOURCE = "SpeakSeed original grammar curriculum v1"
REVIEW_STATUS = "automated_checked"
KINDS = ("multiple_choice", "fill_blank", "sentence_ordering", "error_correction", "vi_to_en")
UNIT_TEST_PLAN = {
    1: {(1, 1), (2, 2)},
    2: {(1, 3), (2, 4)},
    3: {(1, 5), (2, 1)},
    4: {(1, 2), (2, 3)},
    5: {(1, 4), (2, 5)},
}
ALTERNATE_CLOZE = {
    ("Much, many và a lot of", 2): ["much", "a lot of"],
    ("Some và any", 2): ["any", "some"],
    ("Should và shouldn't", 1): ["should", "ought to"],
    ("Should và shouldn't", 2): ["shouldn't", "should not", "ought not to"],
    ("Must và have to", 1): ["must", "have to"],
    ("May, might và could", 1): ["might", "may", "could"],
    ("May, might và could", 2): ["may", "might", "could"],
    ("Mệnh đề quan hệ xác định", 1): ["who", "that"],
    ("Mệnh đề quan hệ xác định", 2): ["that", "which"],
    ("Câu hỏi gián tiếp", 2): ["starts", "begins"],
    ("Câu điều kiện loại 2", 1): ["were", "was"],
    ("Liên từ tương phản", 1): ["although", "though", "even though"],
    ("Nguyên nhân và kết quả", 1): ["because", "since", "as"],
    ("Nguyên nhân và kết quả", 2): ["therefore", "consequently", "hence"],
    ("Câu chẻ với it", 1): ["who", "that"],
    ("Câu chẻ với it", 2): ["that", "when"],
    ("Thức giả định", 2): ["be", "is"],
    ("Would rather và it's time", 2): ["went", "should go"],
    ("Mệnh đề phân từ", 1): ["feeling", "being"],
    ("Mệnh đề phân từ", 2): ["built", "constructed"],
    ("Từ nối bổ sung và đối lập", 1): ["moreover", "furthermore", "additionally"],
    ("Từ nối bổ sung và đối lập", 2): ["nevertheless", "nonetheless", "however"],
    ("Ngôn ngữ giảm nhẹ", 1): ["may", "might", "could"],
    ("Giới từ trong mệnh đề quan hệ", 1): ["whom", "who"],
    ("Tường thuật với động từ đa dạng", 1): ["taking", "having taken"],
}
TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
LINK_STOPWORDS = {
    "a", "an", "the", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those", "am", "is", "are", "was", "were",
    "be", "been", "being", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could", "may", "might",
    "must", "should", "to", "of", "in", "on", "at", "by", "for", "from", "with", "and", "but", "or", "if", "than", "as",
    "not", "no", "so", "who", "which", "what", "where", "when", "how", "there", "here", "then", "very", "more", "most",
}


def slugify(text: str) -> str:
    import unicodedata
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def ordered_tokens(sentence: str) -> str:
    tokens = sentence.rstrip(".?!").split()
    shift = max(1, len(tokens) // 2)
    rotated = tokens[shift:] + tokens[:shift]
    return " / ".join(rotated)


def build_rows():
    units, lessons, examples, exercises = [], [], [], []
    level_seen = Counter()
    for lesson_id, item in enumerate(LESSONS, 1):
        level = item["level"]
        level_index = level_seen[level]
        level_seen[level] += 1
        unit_offset = level_index // 5
        unit_id = list(LEVEL_NAMES).index(level) * 4 + unit_offset + 1
        unit_seq = unit_offset + 1
        unit_slug = f"{level.lower()}-{unit_seq}-{slugify(UNIT_TITLES[level][unit_offset])}"
        if not any(row["id"] == unit_id for row in units):
            units.append({
                "id": unit_id, "slug": unit_slug, "level": level, "sequence": unit_seq,
                "title": UNIT_TITLES[level][unit_offset],
                "description_vi": f"Unit {unit_seq} · {LEVEL_NAMES[level]}: năm chủ điểm và bài kiểm tra cuối unit.",
            })
        lesson_seq = level_index % 5 + 1
        lesson_slug = f"{level.lower()}-{level_index + 1:02d}-{slugify(item['title'])}"
        errors = [
            {"wrong": ex[4], "correct": ex[0], "note": item["explanation_vi"]}
            for ex in item["examples"]
        ]
        lessons.append({**item, "id": lesson_id, "unit_id": unit_id, "slug": lesson_slug,
                        "sequence": lesson_seq, "common_errors": errors})
        for example_index, ex in enumerate(item["examples"], 1):
            english, vietnamese, cloze, cloze_answer, wrong = ex
            examples.append({"id": lesson_id * 10 + example_index, "lesson_id": lesson_id,
                             "sequence": example_index, "english": english,
                             "vietnamese": vietnamese, "focus": cloze_answer})
            base = (lesson_id - 1) * 10 + (example_index - 1) * 5
            common = {"lesson_id": lesson_id, "unit_id": unit_id, "level": level,
                      "explanation_vi": item["explanation_vi"]}
            exercises.extend([
                {**common, "id": base + 1, "kind": "multiple_choice", "is_unit_test": int((example_index, 1) in UNIT_TEST_PLAN[lesson_seq]),
                 "prompt": f"Chọn câu diễn đạt đúng: “{vietnamese}”",
                 "options": [english, wrong], "answers": [english]},
                {**common, "id": base + 2, "kind": "fill_blank", "is_unit_test": int((example_index, 2) in UNIT_TEST_PLAN[lesson_seq]), "prompt": f"Hoàn thành câu “{vietnamese}”: {cloze}",
                 "options": [], "answers": ALTERNATE_CLOZE.get((item["title"], example_index), [cloze_answer])},
                {**common, "id": base + 3, "kind": "sentence_ordering", "is_unit_test": int((example_index, 3) in UNIT_TEST_PLAN[lesson_seq]),
                 "prompt": f"Sắp xếp câu “{vietnamese}”: " + ordered_tokens(english),
                 "options": [], "answers": [english]},
                {**common, "id": base + 4, "kind": "error_correction", "is_unit_test": int((example_index, 4) in UNIT_TEST_PLAN[lesson_seq]),
                 "prompt": f"Sửa câu để diễn đạt “{vietnamese}”: {wrong}", "options": [], "answers": [english]},
                {**common, "id": base + 5, "kind": "vi_to_en", "is_unit_test": int((example_index, 5) in UNIT_TEST_PLAN[lesson_seq]),
                 "prompt": "Dịch sang tiếng Anh: " + vietnamese, "options": [], "answers": [english]},
            ])
    return units, lessons, examples, exercises


def validate(units, lessons, examples, exercises):
    errors = []
    if len(units) != 20: errors.append(f"expected 20 units, found {len(units)}")
    if len(lessons) != 100: errors.append(f"expected 100 lessons, found {len(lessons)}")
    if len(examples) != 200: errors.append(f"expected 200 examples, found {len(examples)}")
    if len(exercises) != 1000: errors.append(f"expected 1000 exercises, found {len(exercises)}")
    if Counter(x["level"] for x in lessons) != Counter({x: 20 for x in LEVEL_NAMES}):
        errors.append("each CEFR level must contain exactly 20 lessons")
    if Counter(x["kind"] for x in exercises) != Counter({x: 200 for x in KINDS}):
        errors.append("each exercise kind must contain exactly 200 items")
    if len({x["prompt"] for x in exercises}) != len(exercises):
        errors.append("exercise prompts must be unique")
    for row in lessons:
        if not all(str(row.get(k, "")).strip() for k in ("title", "topic", "explanation_vi", "formula")):
            errors.append(f"lesson {row['id']} is incomplete")
    for row in exercises:
        if not row["answers"] or not row["prompt"].strip() or not row["explanation_vi"].strip():
            errors.append(f"exercise {row['id']} is incomplete")
    if errors:
        raise ValueError("; ".join(errors))


def import_curriculum(database: Path, migrations: Path) -> dict:
    run_migrations(database, migrations)
    units, lessons, examples, exercises = build_rows()
    validate(units, lessons, examples, exercises)
    timestamp = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(database, timeout=30)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in units:
            con.execute("""INSERT INTO grammar_units(id,slug,level,sequence,title,description_vi,published)
                VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug,level=excluded.level,
                sequence=excluded.sequence,title=excluded.title,description_vi=excluded.description_vi,published=1""",
                (row["id"], row["slug"], row["level"], row["sequence"], row["title"], row["description_vi"]))
        for row in lessons:
            con.execute("""INSERT INTO grammar_lessons(id,unit_id,slug,level,sequence,title,topic,explanation_vi,
                formula,common_errors_json,source,review_status,published,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET unit_id=excluded.unit_id,
                slug=excluded.slug,level=excluded.level,sequence=excluded.sequence,title=excluded.title,
                topic=excluded.topic,explanation_vi=excluded.explanation_vi,formula=excluded.formula,
                common_errors_json=excluded.common_errors_json,source=excluded.source,
                review_status=excluded.review_status,published=1,updated_at=excluded.updated_at""",
                (row["id"], row["unit_id"], row["slug"], row["level"], row["sequence"], row["title"],
                 row["topic"], row["explanation_vi"], row["formula"], json.dumps(row["common_errors"], ensure_ascii=False),
                 SOURCE, REVIEW_STATUS, timestamp))
        for row in examples:
            con.execute("""INSERT INTO grammar_examples(id,lesson_id,sequence,english,vietnamese,focus)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET lesson_id=excluded.lesson_id,
                sequence=excluded.sequence,english=excluded.english,vietnamese=excluded.vietnamese,focus=excluded.focus""",
                (row["id"], row["lesson_id"], row["sequence"], row["english"], row["vietnamese"], row["focus"]))
        vocab = {row[0]: row[1] for row in con.execute("SELECT normalized_word,id FROM library_words WHERE reviewed=1")}
        for index, row in enumerate(exercises, 1):
            source_id = f"grammar-v1-{row['id']:04d}"
            con.execute("""INSERT INTO grammar_exercises(id,lesson_id,unit_id,source_id,level,kind,sequence,prompt,
                options_json,answers_json,explanation_vi,is_unit_test,source,review_status,published,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET lesson_id=excluded.lesson_id,
                unit_id=excluded.unit_id,source_id=excluded.source_id,level=excluded.level,kind=excluded.kind,
                sequence=excluded.sequence,prompt=excluded.prompt,options_json=excluded.options_json,
                answers_json=excluded.answers_json,explanation_vi=excluded.explanation_vi,
                is_unit_test=excluded.is_unit_test,source=excluded.source,review_status=excluded.review_status,
                published=1,updated_at=excluded.updated_at""",
                (row["id"], row["lesson_id"], row["unit_id"], source_id, row["level"], row["kind"], index,
                 row["prompt"], json.dumps(row["options"], ensure_ascii=False), json.dumps(row["answers"], ensure_ascii=False),
                 row["explanation_vi"], row["is_unit_test"], SOURCE, REVIEW_STATUS, timestamp))
            con.execute("DELETE FROM grammar_exercise_words WHERE exercise_id=?", (row["id"],))
            language = " ".join([row["prompt"], *row["answers"], *row["options"]]).lower().replace("’", "'")
            word_ids = {vocab[token] for token in TOKEN_RE.findall(language) if token in vocab and token not in LINK_STOPWORDS}
            con.executemany("INSERT OR IGNORE INTO grammar_exercise_words(exercise_id,word_id) VALUES(?,?)",
                            ((row["id"], word_id) for word_id in word_ids))
        con.execute("UPDATE grammar_units SET published=0 WHERE id>20")
        con.execute("UPDATE grammar_lessons SET published=0 WHERE source=? AND id>100", (SOURCE,))
        con.execute("UPDATE grammar_exercises SET published=0 WHERE source=? AND id>1000", (SOURCE,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    linked = con.execute("SELECT COUNT(DISTINCT exercise_id) FROM grammar_exercise_words").fetchone()[0]
    con.close()
    return {
        "version": VERSION, "units": len(units), "lessons": len(lessons),
        "examples": len(examples), "exercises": len(exercises),
        "levels": dict(Counter(x["level"] for x in lessons)),
        "exercise_kinds": dict(Counter(x["kind"] for x in exercises)),
        "unit_test_questions": sum(x["is_unit_test"] for x in exercises),
        "exercises_linked_to_vocabulary": linked,
        "review_status": REVIEW_STATUS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "speakseed.db")
    parser.add_argument("--migrations", type=Path, default=PROJECT_ROOT / "migrations")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = build_rows()
    validate(*rows)
    if args.dry_run:
        report = {"units": len(rows[0]), "lessons": len(rows[1]), "examples": len(rows[2]),
                  "exercises": len(rows[3]), "levels": dict(Counter(x["level"] for x in rows[1])),
                  "exercise_kinds": dict(Counter(x["kind"] for x in rows[3])),
                  "unit_test_questions": sum(x["is_unit_test"] for x in rows[3]),
                  "review_status": REVIEW_STATUS}
    else:
        report = import_curriculum(args.database, args.migrations)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
