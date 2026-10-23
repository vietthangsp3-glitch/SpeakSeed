import sqlite3
from pathlib import Path

from migrations import run_migrations
from tools.classify_vocabulary_topics import classify


def _word(con, word: str, meaning: str, pos: str = "noun") -> int:
    cur = con.execute("""INSERT INTO library_words
        (word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,
         normalized_word,example_vi,quality_score,updated_at)
        VALUES(?,?,'','','Unclassified','📘','A2',?,'test','test','CC0-1.0',1,?,'',100,CURRENT_TIMESTAMP)""",
        (word, meaning, pos, word.casefold()))
    return cur.lastrowid


def test_automatic_topic_rules_are_idempotent_and_not_human_review(tmp_path: Path):
    db = tmp_path / "topic.db"
    root = Path(__file__).resolve().parents[1]
    run_migrations(db, root / "migrations")
    with sqlite3.connect(db) as con:
        biscuit = _word(con, "biscuit", "Bánh quy.")
        ambiguous = _word(con, "bank", "Ngân hàng; bờ sông.")

    dry = classify(db, False)
    assert dry["proposed_words"] == 1
    first = classify(db, True, tmp_path / "backups")
    second = classify(db, True, tmp_path / "backups")
    assert first["published_words"] == 1
    assert second["published_mappings"] == 0

    with sqlite3.connect(db) as con:
        row = con.execute("""SELECT tw.review_status,tw.source_key,tw.published,t.slug
          FROM vocabulary_topic_words tw JOIN vocabulary_topics t ON t.id=tw.topic_id
          WHERE tw.word_id=?""", (biscuit,)).fetchone()
        assert row == ("pending", "automated-topic-v1", 1, "food-drinks")
        assert con.execute("SELECT COUNT(*) FROM vocabulary_automated_topic_releases WHERE word_id=?", (biscuit,)).fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE word_id=?", (ambiguous,)).fetchone()[0] == 0
