"""Prepare auditable Phase 5 vocabulary candidates and topic proposals.

This tool only writes staging/proposal rows. It never grants roles, records human
review, publishes vocabulary, or mutates SRS/user progress.
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
from tools.build_vocabulary import dictionary_entry, load_cefr, load_examples

POLICY_VERSION = "core-v1"
TOKEN_RE = re.compile(r"[a-z]+(?:['-][a-z]+)*")

# Curated semantic concepts. Matching uses complete normalized tokens from the
# WordNet definition/synonyms/headword, never arbitrary substrings. Results are
# proposals only and remain invisible until a named reviewer approves/publishes.
TOPIC_CONCEPTS = {
    "daily-life": "routine time day week month year morning evening night sleep wake wash clean daily calendar appointment habit".split(),
    "family-relationships": "family parent mother father sister brother child son daughter husband wife marriage friend relationship relative cousin uncle aunt".split(),
    "food-drinks": "food drink meal eat cook kitchen restaurant bread rice fruit vegetable meat coffee tea milk recipe taste".split(),
    "home-furniture": "home house room furniture chair table bed kitchen bathroom bedroom garden household door window".split(),
    "education": "school student teacher learn study lesson exam university college education classroom course academic".split(),
    "work-careers": "work job office career employer employee profession occupation salary manager workplace hire".split(),
    "travel-tourism": "travel tourist tourism hotel passport vacation holiday flight airport journey trip luggage".split(),
    "transportation": "transport vehicle car bus train bicycle ship boat road railway drive traffic passenger".split(),
    "shopping-money": "shop shopping buy sell price payment money market store customer cash cost purchase".split(),
    "health-body": "health body medicine medical doctor hospital disease illness pain patient organ blood treatment".split(),
    "sports-fitness": "sport game athlete exercise fitness football tennis swim run team match competition".split(),
    "technology": "technology computer software internet digital electronic machine website phone data network".split(),
    "nature-environment": "nature environment earth river sea mountain forest climate natural pollution geography".split(),
    "animals-plants": "animal plant bird fish insect tree flower species mammal dog cat horse".split(),
    "entertainment": "entertainment film movie music television theater actor concert media performance".split(),
    "hobbies-leisure": "hobby leisure recreation game collect craft relax pastime photography".split(),
    "emotions-personality": "emotion feeling personality happy sad angry fear love attitude character mood".split(),
    "clothing-fashion": "clothing clothes dress shirt shoe wear fashion garment coat hat".split(),
    "communication": "communicate communication speak say tell ask answer write read language message conversation word".split(),
    "science": "science scientific research physics chemistry biology experiment theory laboratory".split(),
    "business-finance": "business finance financial company trade bank investment profit economic economy industry".split(),
    "society-culture": "society social culture government law public community religion political country people".split(),
    "places-directions": "place location direction north south east west building street area position".split(),
    "weather-seasons": "weather season rain snow wind cloud storm temperature summer winter spring autumn".split(),
}
TOPIC_CONCEPTS = {key: set(value) for key, value in TOPIC_CONCEPTS.items()}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def semantic_topics(word: str, definitions: list[dict]) -> list[tuple[str, int, str]]:
    head_tokens = set(TOKEN_RE.findall(word.casefold()))
    definition_tokens: set[str] = set()
    synonym_tokens: set[str] = set()
    for item in definitions[:8]:
        definition_tokens.update(TOKEN_RE.findall(str(item.get("definition_en", "")).casefold()))
        for synonym in item.get("synonyms", []):
            synonym_tokens.update(TOKEN_RE.findall(str(synonym).casefold()))
    scored = []
    for slug, concepts in TOPIC_CONCEPTS.items():
        direct = head_tokens & concepts
        synonyms = synonym_tokens & concepts
        context = definition_tokens & concepts
        score = min(95, len(direct) * 45 + len(synonyms) * 25 + len(context) * 12)
        # One exact concept in a WordNet definition is enough to propose a
        # mapping, never to publish it. Direct headword/synonym evidence remains
        # weighted much higher and is visible to the reviewer as rationale.
        if score >= 12:
            evidence = sorted(direct | synonyms | context)[:8]
            scored.append((slug, score, "WordNet exact-token semantic evidence: " + ", ".join(evidence)))
    return sorted(scored, key=lambda item: (-item[1], item[0]))[:2]


def load_wordnet(staging: sqlite3.Connection, wanted: set[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    rows = staging.execute("""SELECT r.payload_json FROM content_staging_records r
      JOIN content_import_batches b ON b.id=r.batch_id
      WHERE b.source_key='princeton-wordnet-3.0' AND r.validation_status='valid'""")
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        lemma = " ".join(str(payload.get("lemma", "")).casefold().split())
        if lemma in wanted and len(result[lemma]) < 8:
            result[lemma].append(payload)
    return result


def prepare(database: Path, root: Path) -> dict:
    run_migrations(database, root / "migrations")
    cefr = load_cefr(root / ".source-cache/cefrj/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv")
    con = sqlite3.connect(database, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    published = {row[0] for row in con.execute("SELECT normalized_word FROM library_words WHERE reviewed=1")}
    new_words = set(cefr) - published
    examples = load_examples(root / ".source-cache/tatoeba/vie.txt", root / ".source-cache/flores/flores200_dataset",
                             root / ".source-cache/ntrex.eng.txt", root / ".source-cache/ntrex.vie.txt", new_words)
    wordnet = load_wordnet(con, set(cefr))
    dictionary = sqlite3.connect(root / ".source-cache/dictionary_en_vi.db")
    topic_ids = {row["slug"]: row["id"] for row in con.execute("SELECT id,slug FROM vocabulary_topics WHERE active=1")}
    counts = Counter(); topic_proposals = Counter()
    stamp = utcnow()
    try:
        con.execute("BEGIN IMMEDIATE")
        for word in sorted(new_words):
            meta = cefr[word]
            pair = examples.get(word)
            entry = dictionary_entry(dictionary, word, meta["positions"], pair[1] if pair else "")
            topics = semantic_topics(word, wordnet.get(word, []))
            if entry:
                meaning, ipa, pos = entry
                license_status = "blocked"  # upstream provenance review remains unresolved
                qa_status = "pass" if topics else "warn"
                core_status = "license_blocked" if topics else "needs_data"
                counts["has_meaning_ipa"] += 1
            else:
                meaning = ipa = ""
                pos = sorted(meta["positions"])[0]
                license_status = "blocked"
                qa_status = "warn"
                core_status = "needs_data"
                counts["needs_meaning"] += 1
            definition = wordnet.get(word, [{}])[0].get("definition_en", "") if wordnet.get(word) else ""
            example_en, example_vi = (pair[0], pair[1]) if pair else ("", "")
            provenance = {
                "headword_pos_cefr": {"source": "cefr-j-1.5", "record": meta["source_id"]},
                "meaning_vi_ipa": {"source": "skypedia-en-vi", "status": "conditional_unresolved"} if entry else None,
                "definition_en": {"source": "princeton-wordnet-3.0"} if definition else None,
                "example_pair": {"source": pair[3], "attribution": pair[2]} if pair else None,
            }
            stable = f"{word}|{pos}|{meta['level']}"
            cur = con.execute("""INSERT INTO vocabulary_candidates(stable_key,normalized_word,word,pos,meaning_vi,ipa,
              cefr_level,definition_en,example_en,example_vi,source_key,source_record_id,provenance_json,
              license_status,qa_status,core_status,review_status,policy_version,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)
              ON CONFLICT(stable_key) DO UPDATE SET definition_en=excluded.definition_en,
                example_en=excluded.example_en,example_vi=excluded.example_vi,
                provenance_json=excluded.provenance_json,license_status=excluded.license_status,
                qa_status=excluded.qa_status,core_status=excluded.core_status,updated_at=excluded.updated_at
              RETURNING id""", (stable,word,word,pos,meaning,ipa,meta["level"],definition,example_en,example_vi,
              "cefr-j-1.5",meta["source_id"],json.dumps(provenance,ensure_ascii=False,sort_keys=True),
              license_status,qa_status,core_status,POLICY_VERSION,stamp,stamp))
            candidate_id = cur.fetchone()[0]
            for slug, confidence, rationale in topics:
                con.execute("""INSERT INTO vocabulary_candidate_topics(candidate_id,topic_id,confidence,source_key,rationale)
                  VALUES(?,?,?,?,?) ON CONFLICT(candidate_id,topic_id) DO UPDATE SET confidence=excluded.confidence,
                  source_key=excluded.source_key,rationale=excluded.rationale""",
                  (candidate_id,topic_ids[slug],confidence,"princeton-wordnet-3.0",rationale))
                topic_proposals[slug] += 1
            counts[core_status] += 1
            counts["with_example"] += bool(pair)
            counts["with_topic_proposal"] += bool(topics)

        # Existing words get pending semantic proposals only. They remain absent
        # from public APIs until a human review and separate publish action.
        existing = con.execute("""SELECT id,normalized_word FROM library_words w WHERE reviewed=1 AND NOT EXISTS(
          SELECT 1 FROM vocabulary_topic_words tw WHERE tw.word_id=w.id AND tw.published=1)""").fetchall()
        for row in existing:
            for slug, confidence, rationale in semantic_topics(row["normalized_word"], wordnet.get(row["normalized_word"], [])):
                con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,
                  confidence,source_key,rationale,created_at) VALUES(?,?,'','pending',0,?,?,?,?)
                  ON CONFLICT(word_id,topic_id,sense_key) DO NOTHING""",
                  (row["id"],topic_ids[slug],confidence,"princeton-wordnet-3.0",rationale,stamp))
                counts["existing_topic_proposals"] += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        dictionary.close(); con.close()
    return {
        "policy_version": POLICY_VERSION,
        "candidate_headwords": len(new_words),
        "classification": dict(sorted(counts.items())),
        "topic_proposals_by_topic": dict(sorted(topic_proposals.items())),
        "human_reviewed": 0, "published": 0,
        "note": "Skypedia-derived Vietnamese meanings remain license-blocked pending upstream provenance review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.database, args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
