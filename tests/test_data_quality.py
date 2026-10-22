import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bundled_vocabulary_is_complete_and_unique():
    con = sqlite3.connect(ROOT / "speakseed.db")
    published = con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0]
    complete = con.execute("""SELECT COUNT(*) FROM library_words WHERE reviewed=1
        AND normalized_word<>'' AND meaning<>'' AND ipa<>'' AND pos<>''
        AND stage IN ('A0','A1','A2','B1','B2') AND topic<>''
        AND example<>'' AND example_vi<>'' AND source<>''""").fetchone()[0]
    unique = con.execute("SELECT COUNT(DISTINCT normalized_word) FROM library_words WHERE reviewed=1").fetchone()[0]
    assert published >= 4000
    assert complete == published == unique
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_every_published_word_has_field_provenance():
    con = sqlite3.connect(ROOT / "speakseed.db")
    missing = con.execute("""SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1 AND
        (SELECT COUNT(*) FROM word_attributions a WHERE a.word_id=w.id) < 3""").fetchone()[0]
    assert missing == 0
    assert con.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0] >= 5


def test_level_distribution_reaches_b2():
    con = sqlite3.connect(ROOT / "speakseed.db")
    levels = dict(con.execute("SELECT stage,COUNT(*) FROM library_words WHERE reviewed=1 GROUP BY stage"))
    assert all(levels.get(level, 0) > 0 for level in ("A1", "A2", "B1", "B2"))
