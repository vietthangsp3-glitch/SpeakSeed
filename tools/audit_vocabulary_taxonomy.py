"""Read-only CEFR/topic audit for the published SpeakSeed vocabulary."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.build_vocabulary import load_cefr

CEFR_J = ROOT / ".source-cache/cefrj/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv"


def audit(database: Path, cefr_path: Path = CEFR_J) -> dict:
    con = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    reference = load_cefr(cefr_path)
    words = list(con.execute("SELECT id,normalized_word,stage FROM library_words WHERE reviewed=1 ORDER BY id"))
    levels = Counter(row["stage"] if row["stage"] in {"A0", "A1", "A2", "B1", "B2"} else "unverified"
                     for row in words)
    mismatches = []
    missing = []
    for row in words:
        expected = reference.get(row["normalized_word"])
        if not expected:
            missing.append(row["normalized_word"])
        elif expected["level"] != row["stage"]:
            mismatches.append({"word": row["normalized_word"], "stored": row["stage"],
                               "cefr_j": expected["level"]})
    topics = {row["slug"]: row["total"] for row in con.execute(
        """SELECT t.slug,COUNT(DISTINCT tw.word_id) total FROM vocabulary_topics t
           LEFT JOIN vocabulary_topic_words tw ON tw.topic_id=t.id AND tw.published=1
           WHERE t.active=1 GROUP BY t.id,t.slug ORDER BY t.id""")}
    classified = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    result = {
        "published_words": len(words), "levels": {key: levels.get(key, 0) for key in ("A0", "A1", "A2", "B1", "B2", "unverified")},
        "a0_policy": "A0 is SpeakSeed's internal pre-A1 onboarding label, not an official CEFR level.",
        "cefr_reference": "CEFR-J Vocabulary Profile 1.5",
        "cefr_reference_matches": len(words) - len(missing), "cefr_mismatches": mismatches,
        "cefr_unmatched": missing, "topics": topics, "classified_words": classified,
        "unclassified_words": len(words) - classified,
        "published_topic_mappings": con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE published=1").fetchone()[0],
        "automated_topic_corrections": con.execute("SELECT COUNT(*) FROM vocabulary_topic_corrections").fetchone()[0],
        "integrity": con.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_key_errors": len(con.execute("PRAGMA foreign_key_check").fetchall()),
    }
    con.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "speakseed.db")
    parser.add_argument("--cefr", type=Path, default=CEFR_J)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.database, args.cefr)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
