"""Publish conservative, reproducible vocabulary-topic mappings.

The rules intentionally prefer precision over coverage.  They use exact English
headwords or unambiguous Vietnamese dictionary phrases, never an AI service.
Every published mapping has immutable automated evidence and is not represented
as human reviewed.  Dry-run is the default.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations import run_migrations
RULE_VERSION = "topic-core-v1"

# Exact headwords are deliberately limited to words whose ordinary sense is a
# clear member of a topic. Ambiguous words (bank, court, case, drive...) are not
# included. Vietnamese patterns require the compatible part of speech.
EXACT: dict[str, set[str]] = {
    "family-relationships": {"bride", "bridegroom", "grandchild", "granddaughter", "grandparent", "grandson", "nephew", "niece", "stepfather", "stepmother", "widow", "widower"},
    "food-drinks": {"aubergine", "bacon", "barbecue", "barley", "biscuit", "broccoli", "bun", "cabbage", "cauliflower", "cereal", "cheesecake", "cucumber", "dessert", "garlic", "hamburger", "lemonade", "mushroom", "omelette", "pancake", "pineapple", "sausage", "spaghetti", "spinach", "strawberry", "watermelon"},
    "home-furniture": {"balcony", "bedside", "blanket", "bookcase", "bucket", "carpet", "cupboard", "curtain", "doorbell", "furniture", "mattress", "pillow", "sofa", "staircase", "wardrobe"},
    "education": {"blackboard", "classmate", "coursebook", "dictionary", "headmaster", "homework", "schoolchild", "schoolteacher", "textbook", "undergraduate"},
    "work-careers": {"accountant", "applicant", "architect", "baker", "barber", "builder", "businessman", "businesswoman", "carpenter", "cashier", "dentist", "electrician", "engineer", "farmer", "firefighter", "journalist", "librarian", "mechanic", "nurse", "photographer", "plumber", "receptionist", "scientist", "secretary", "waiter", "waitress"},
    "travel-tourism": {"backpacker", "campsite", "guidebook", "hostel", "sightseeing", "suitcase", "tourist", "traveller"},
    "transportation": {"aircrew", "airline", "airplane", "biker", "crossroads", "helicopter", "motorbike", "motorcycle", "railway", "taxi", "tram"},
    "shopping-money": {"bargain", "bookshop", "checkout", "department-store", "shopkeeper", "supermarket"},
    "health-body": {"addict", "addiction", "alcoholism", "ankle", "backache", "bloodstream", "bruise", "bulimia", "headache", "heartbeat", "toothache", "wheelchair"},
    "sports-fitness": {"aerobics", "badminton", "boxer", "boxing", "cricket", "gymnastics", "jogging", "skateboarding", "skiing", "snowboarding", "volleyball"},
    "technology": {"amplifier", "antivirus", "backup", "broadband", "browser", "cybercrime", "database", "download", "email", "keyboard", "laptop", "microchip", "password", "printer", "smartphone", "webpage", "website"},
    "nature-environment": {"antipollution", "earthquake", "ecosystem", "environmental", "flood", "greenhouse", "landscape", "recycling", "waterfall", "wildlife"},
    "animals-plants": {"ape", "beagle", "beaver", "berry", "blooming", "botany", "breeding", "bull", "butterfly", "caterpillar", "dolphin", "eagle", "elephant", "giraffe", "kangaroo", "kitten", "penguin", "puppy", "rabbit", "shark", "sparrow"},
    "entertainment": {"ballad", "ballet", "broadcaster", "cinema", "comedian", "documentary", "drama", "filmmaker", "musician", "novelist", "orchestra", "singer", "songwriter"},
    "hobbies-leisure": {"bookmark", "camping", "chess", "gardening", "knitting", "painting", "sightseeing"},
    "emotions-personality": {"affectionate", "amazement", "anguish", "annoyance", "anxiously", "awkward", "benevolence", "benevolent", "bewilderment", "boredom", "bravery", "jealousy", "loneliness"},
    "clothing-fashion": {"accessory", "apron", "bikini", "bracelet", "earring", "handbag", "jacket", "necklace", "pyjamas", "sandal", "scarf", "sweater", "trousers"},
    "communication": {"addressee", "adverb", "antonym", "apostrophe", "biography", "brochure", "grammar", "pronunciation", "speaker", "vocabulary"},
    "science": {"ammonia", "astronaut", "biochemistry", "biotechnology", "botany", "geology", "mathematics", "microscope", "psychology", "telescope"},
    "business-finance": {"accountant", "audit", "bankrupt", "bankruptcy", "bonus", "businessman", "businesswoman", "investment", "shareholder", "stockbroker"},
    "society-culture": {"altar", "battlefield", "bishop", "bureaucracy", "burglary", "citizenship", "democracy", "governmental", "parliament", "politician", "religion"},
    "places-directions": {"aisle", "arch", "avenue", "birthplace", "crossroads", "downstairs", "entrance", "exit", "indoors", "outdoors", "upstairs"},
    "weather-seasons": {"barometer", "blizzard", "breeze", "cloudy", "foggy", "forecast", "rainfall", "snowfall", "sunshine", "thunderstorm", "windy"},
}

MEANING_RULES = {
    "health-body": ("noun", re.compile(r"(?:chứng|căn) bệnh|bệnh tật|dòng máu trong cơ thể|bộ phận cơ thể|thuốc chữa|y học", re.I)),
    "science": ("noun", re.compile(r"(?:hoá|hóa) sinh|(?:hoá|hóa) học|vật lý học|sinh vật học|khoa học nghiên cứu", re.I)),
    "technology": ("noun", re.compile(r"phần mềm|máy tính|mạng internet|dữ liệu máy tính|virus máy tính", re.I)),
    "sports-fitness": ("noun", re.compile(r"thể dục nhịp điệu|cầu lông|quyền anh|môn thể thao", re.I)),
    "food-drinks": ("noun", re.compile(r"bánh quy|bông cải|thịt .*muối|món ăn|đồ uống", re.I)),
    "animals-plants": ("noun", re.compile(r"(?:con|loài) (?:hải ly|khỉ|chó|bò|chim|cá|ngựa)|thực vật học", re.I)),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def proposals(con: sqlite3.Connection) -> list[dict]:
    existing = {(r[0], r[1]) for r in con.execute(
        "SELECT word_id,topic_id FROM vocabulary_topic_words WHERE published=1")}
    topic_ids = {r[0]: r[1] for r in con.execute("SELECT slug,id FROM vocabulary_topics WHERE active=1")}
    result: list[dict] = []
    for row in con.execute("SELECT id,normalized_word,pos,meaning FROM library_words WHERE reviewed=1 ORDER BY id"):
        word_id, word, pos, meaning = row
        matched: dict[str, tuple[str, str]] = {}
        for slug, words in EXACT.items():
            if word in words:
                matched[slug] = (f"exact:{slug}:{word}", "exact normalized headword in curated topic lexicon")
        for slug, (required_pos, pattern) in MEANING_RULES.items():
            hit = pattern.search(meaning or "")
            if pos == required_pos and hit:
                matched.setdefault(slug, (f"meaning:{slug}:{hit.group(0).casefold()}",
                                          f"unambiguous Vietnamese meaning phrase: {hit.group(0)}"))
        for slug, (rule_id, evidence) in matched.items():
            topic_id = topic_ids[slug]
            if (word_id, topic_id) not in existing:
                result.append({"word_id": word_id, "word": word, "topic_id": topic_id,
                               "topic": slug, "rule_id": rule_id, "evidence": evidence})
    return result


def classify(database: Path, apply: bool, backup_dir: Path | None = None) -> dict:
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database, timeout=60)
    con.execute("PRAGMA foreign_keys=ON")
    rows = proposals(con)
    before = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    if not apply:
        con.close()
        return {"mode": "dry-run", "proposed_mappings": len(rows),
                "proposed_words": len({r['word_id'] for r in rows}), "classified_before": before,
                "by_topic": _counts(rows)}
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"speakseed-before-topic-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        shutil.copy2(database, target)
    stamp = now()
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in rows:
            evidence = json.dumps({"rule_version": RULE_VERSION, "rule_id": row["rule_id"],
                                   "evidence": row["evidence"], "word": row["word"]}, ensure_ascii=False)
            con.execute("""INSERT OR IGNORE INTO vocabulary_automated_topic_releases
                (word_id,topic_id,rule_version,rule_id,evidence_json,released_at) VALUES(?,?,?,?,?,?)""",
                (row["word_id"], row["topic_id"], RULE_VERSION, row["rule_id"], evidence, stamp))
            con.execute("""INSERT INTO vocabulary_topic_words
                (word_id,topic_id,sense_key,review_status,published,confidence,source_key,rationale,created_at)
                VALUES(?,?,'','pending',1,90,'automated-topic-v1',?,?)
                ON CONFLICT(word_id,topic_id,sense_key) DO NOTHING""",
                (row["word_id"], row["topic_id"], row["evidence"], stamp))
        # The legacy display field is only changed when it was explicitly
        # unclassified and exactly one published mapping now exists.
        con.execute("""UPDATE library_words SET topic=(
              SELECT t.name_en FROM vocabulary_topic_words tw JOIN vocabulary_topics t ON t.id=tw.topic_id
              WHERE tw.word_id=library_words.id AND tw.published=1 ORDER BY t.id LIMIT 1)
            WHERE topic='Unclassified' AND
              (SELECT COUNT(*) FROM vocabulary_topic_words tw WHERE tw.word_id=library_words.id AND tw.published=1)=1""")
        con.commit()
    except Exception:
        con.rollback()
        raise
    after = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    unclassified = con.execute("""SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1 AND NOT EXISTS
        (SELECT 1 FROM vocabulary_topic_words tw WHERE tw.word_id=w.id AND tw.published=1)""").fetchone()[0]
    con.close()
    return {"mode": "apply", "published_mappings": len(rows), "published_words": after-before,
            "classified_total": after, "unclassified_by_mapping": unclassified, "by_topic": _counts(rows)}


def _counts(rows: list[dict]) -> dict[str, int]:
    return {slug: sum(1 for row in rows if row["topic"] == slug) for slug in sorted({r["topic"] for r in rows})}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "speakseed.db")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "qa_artifacts")
    args = parser.parse_args()
    print(json.dumps(classify(args.database, args.apply, args.backup_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
