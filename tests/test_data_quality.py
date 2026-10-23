import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bundled_vocabulary_is_complete_and_unique():
    con = sqlite3.connect(ROOT / "speakseed.db")
    published = con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0]
    core_complete = con.execute("""SELECT COUNT(*) FROM library_words WHERE reviewed=1
        AND normalized_word<>'' AND meaning<>'' AND pos<>''
        AND stage IN ('A0','A1','A2','B1','B2') AND topic<>'' AND source<>''""").fetchone()[0]
    fully_enriched = con.execute("""SELECT COUNT(*) FROM library_words WHERE reviewed=1
        AND ipa<>'' AND example<>'' AND example_vi<>''""").fetchone()[0]
    unique = con.execute("SELECT COUNT(DISTINCT normalized_word) FROM library_words WHERE reviewed=1").fetchone()[0]
    assert published == core_complete == unique == 6280
    assert fully_enriched == 4213
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_every_published_word_has_field_provenance():
    con = sqlite3.connect(ROOT / "speakseed.db")
    legacy_missing = con.execute("""SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1
        AND w.source<>'kaikki-viwiktionary-en-2026-10-02' AND
        (SELECT COUNT(*) FROM word_attributions a WHERE a.word_id=w.id) < 3""").fetchone()[0]
    automated_missing = con.execute("""SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1
        AND w.source='kaikki-viwiktionary-en-2026-10-02' AND (
          NOT EXISTS(SELECT 1 FROM word_attributions a WHERE a.word_id=w.id AND a.field_name='meaning')
          OR NOT EXISTS(SELECT 1 FROM vocabulary_automated_releases r WHERE r.word_id=w.id
            AND r.rule_version='auto-core-v1'))""").fetchone()[0]
    assert legacy_missing == automated_missing == 0
    assert con.execute("SELECT COUNT(*) FROM vocabulary_automated_releases").fetchone()[0] == 2067
    assert con.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0] >= 5


def test_level_distribution_reaches_b2():
    con = sqlite3.connect(ROOT / "speakseed.db")
    levels = dict(con.execute("SELECT stage,COUNT(*) FROM library_words WHERE reviewed=1 GROUP BY stage"))
    assert all(levels.get(level, 0) > 0 for level in ("A1", "A2", "B1", "B2"))
