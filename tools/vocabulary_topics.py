"""Local-only topic mapping review tool. It has no web admin endpoint."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(database: Path) -> sqlite3.Connection:
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def list_mappings(database: Path, status: str = "pending", limit: int = 100,
                  min_confidence: int = 0) -> list[dict]:
    with connect(database) as con:
        return [dict(row) for row in con.execute("""SELECT tw.word_id,w.word,w.stage,t.slug,t.name_en,t.name_vi,
            tw.sense_key,tw.review_status,tw.published,tw.confidence,tw.source_key,tw.rationale
            FROM vocabulary_topic_words tw JOIN vocabulary_topics t ON t.id=tw.topic_id
            JOIN library_words w ON w.id=tw.word_id WHERE tw.review_status=? AND tw.confidence>=?
            ORDER BY tw.confidence DESC,w.stage,w.word,t.id LIMIT ?""",
            (status, max(0, min(min_confidence, 100)), max(1, min(limit, 1000))))]


def propose(database: Path, word_id: int, topic_slug: str, sense_key: str,
            source_key: str, rationale: str, confidence: int) -> dict:
    if not source_key.strip() or not rationale.strip():
        raise ValueError("Source and rationale are required")
    if confidence < 0 or confidence > 100:
        raise ValueError("Confidence must be between 0 and 100")
    with connect(database) as con:
        word = con.execute("SELECT id,word FROM library_words WHERE id=? AND reviewed=1", (word_id,)).fetchone()
        topic = con.execute("SELECT id,slug FROM vocabulary_topics WHERE slug=? AND active=1", (topic_slug,)).fetchone()
        if not word or not topic:
            raise ValueError("Unknown published word or active topic")
        con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,
            confidence,source_key,rationale,created_at) VALUES(?,?,?,'pending',0,?,?,?,?)
            ON CONFLICT(word_id,topic_id,sense_key) DO UPDATE SET confidence=excluded.confidence,
            source_key=excluded.source_key,rationale=excluded.rationale,review_status='pending',published=0,
            reviewed_at=NULL,reviewed_by=''""",
            (word_id, topic["id"], sense_key.strip(), confidence, source_key.strip(), rationale.strip(), now()))
        return {"word_id": word_id, "word": word["word"], "topic": topic_slug,
                "review_status": "pending", "published": 0}


def review(database: Path, word_id: int, topic_slug: str, sense_key: str,
           reviewer: str, decision: str, reason: str) -> dict:
    if not reviewer.strip() or not reason.strip() or decision not in {"approve", "reject"}:
        raise ValueError("Reviewer identity, valid decision and reason are required")
    con = connect(database)
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("""SELECT tw.*,t.slug FROM vocabulary_topic_words tw JOIN vocabulary_topics t ON t.id=tw.topic_id
            WHERE tw.word_id=? AND t.slug=? AND tw.sense_key=?""", (word_id, topic_slug, sense_key)).fetchone()
        if not row or row["published"]:
            raise ValueError("Unknown or already-published mapping")
        stamp = now()
        con.execute("""INSERT INTO vocabulary_topic_reviews(word_id,topic_id,sense_key,reviewer_name,decision,reason,reviewed_at)
            VALUES(?,?,?,?,?,?,?)""", (word_id, row["topic_id"], sense_key, reviewer.strip(), decision, reason.strip(), stamp))
        status = "human_reviewed" if decision == "approve" else "rejected"
        con.execute("""UPDATE vocabulary_topic_words SET review_status=?,reviewed_at=?,reviewed_by=?
            WHERE word_id=? AND topic_id=? AND sense_key=?""",
            (status, stamp, reviewer.strip(), word_id, row["topic_id"], sense_key))
        con.commit()
        return {"word_id": word_id, "topic": topic_slug, "review_status": status, "published": 0}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def publish(database: Path, word_id: int, topic_slug: str, sense_key: str, confirm: bool) -> dict:
    if not confirm:
        raise ValueError("Explicit --confirm-publish is required")
    with connect(database) as con:
        cursor = con.execute("""UPDATE vocabulary_topic_words SET published=1 WHERE word_id=? AND sense_key=?
            AND topic_id=(SELECT id FROM vocabulary_topics WHERE slug=?) AND review_status='human_reviewed'""",
            (word_id, sense_key, topic_slug))
        if cursor.rowcount != 1:
            raise ValueError("Mapping is not human-reviewed or does not exist")
        return {"word_id": word_id, "topic": topic_slug, "published": 1}


def report(database: Path) -> dict:
    with connect(database) as con:
        return {
            "published_words": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
            "topics": con.execute("SELECT COUNT(*) FROM vocabulary_topics WHERE active=1").fetchone()[0],
            "published_mappings": con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE published=1").fetchone()[0],
            "classified_words": con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0],
            "pending_mappings": con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE review_status='pending'").fetchone()[0],
            "human_reviewed_mappings": con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE review_status='human_reviewed'").fetchone()[0],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local SpeakSeed vocabulary-topic review")
    parser.add_argument("command", choices=("list", "propose", "approve", "reject", "publish", "report"))
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--word-id", type=int)
    parser.add_argument("--topic", default="")
    parser.add_argument("--sense-key", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--confidence", type=int, default=0)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--status", default="pending")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-confidence", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-publish", action="store_true")
    args = parser.parse_args()
    if args.command == "list": result = list_mappings(args.database, args.status, args.limit, args.min_confidence)
    elif args.command == "report": result = report(args.database)
    elif args.command == "propose": result = propose(args.database, args.word_id, args.topic, args.sense_key,
                                                        args.source, args.rationale, args.confidence)
    elif args.command in {"approve", "reject"}: result = review(args.database, args.word_id, args.topic,
        args.sense_key, args.reviewer, args.command, args.reason)
    else: result = publish(args.database, args.word_id, args.topic, args.sense_key, args.confirm_publish)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
