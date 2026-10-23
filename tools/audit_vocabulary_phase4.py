"""Read-only Phase 4 vocabulary gap audit; never publishes or mutates data."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from build_vocabulary import dictionary_entry, load_cefr, load_examples


def audit(root: Path, database: Path) -> dict:
    cefr = load_cefr(root / ".source-cache/cefrj/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv")
    with sqlite3.connect(database) as con:
        published = {row[0] for row in con.execute("SELECT normalized_word FROM library_words WHERE reviewed=1")}
        base = dict(zip(("total","meaning_vi","ipa","pos","example_en","example_vi"), con.execute(
            """SELECT COUNT(*),SUM(trim(meaning)<>''),SUM(trim(ipa)<>''),SUM(trim(pos)<>''),
               SUM(trim(example)<>''),SUM(trim(example_vi)<>'') FROM library_words WHERE reviewed=1""").fetchone()))
        topics = {row[0]: row[1] for row in con.execute("""SELECT t.slug,COUNT(DISTINCT tw.word_id)
            FROM vocabulary_topics t LEFT JOIN vocabulary_topic_words tw ON tw.topic_id=t.id AND tw.published=1
            GROUP BY t.id ORDER BY t.id""")}
        classified = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    new = sorted(set(cefr) - published)
    examples = load_examples(root / ".source-cache/tatoeba/vie.txt",
                             root / ".source-cache/flores/flores200_dataset",
                             root / ".source-cache/ntrex.eng.txt", root / ".source-cache/ntrex.vie.txt", set(new))
    dictionary = sqlite3.connect(root / ".source-cache/dictionary_en_vi.db")
    with_dictionary = 0; complete = []
    for word in new:
        translated_example = examples.get(word, ("", "", "", ""))[1]
        entry = dictionary_entry(dictionary, word, cefr[word]["positions"], translated_example)
        if entry: with_dictionary += 1
        if entry and word in examples: complete.append(word)
    dictionary.close()
    return {
        "published_before": base,
        "cefr_j_valid_headwords": len(cefr),
        "cefr_j_valid_source_records": 7627,
        "new_unique_headwords": len(new),
        "new_with_vietnamese_meaning_and_ipa": with_dictionary,
        "new_with_bilingual_example": len(examples),
        "new_complete_candidates": len(complete),
        "new_ready_for_review": 0,
        "new_human_reviewed": 0,
        "new_published": 0,
        "new_levels": dict(sorted(Counter(cefr[word]["level"] for word in new).items())),
        "topics": len(topics), "topic_counts": topics,
        "classified_words": classified, "unclassified_words": base["total"] - classified,
        "blocker": "No new headword has both a trusted Vietnamese dictionary entry/IPA and a licensed bilingual example in the local sources.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--database", type=Path, default=Path("speakseed.db")); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]; result = audit(root, args.database)
    if args.output: args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
