# SpeakSeed Phase 4 — Vocabulary expansion and topic-based learning

Date: **2026-10-23**

## Outcome

Phase 4 adds a working topic-based vocabulary experience over the released vocabulary
without changing word IDs or SRS rows. It does **not** claim a vocabulary expansion that
the source data cannot support. No Neon connection, production migration, content
publication, Git push, Vercel deployment or Gemini request was made.

## Exact vocabulary audit

| Measure | Count |
|---|---:|
| Learnable words before Phase 4 | 4,213 |
| Valid unique CEFR-J headwords | 6,698 |
| Valid CEFR-J source records | 7,627 |
| New unique CEFR-J headwords | 2,485 |
| New headwords with a Vietnamese meaning and IPA in the conditional dictionary source | 2,220 |
| New headwords with a licensed bilingual corpus example | 105 |
| New headwords satisfying both sets plus all publish fields | 0 |
| New words ready for content review | 0 |
| New words human-reviewed | 0 |
| New words published locally | 0 |
| **Total words actually learnable after Phase 4** | **4,213** |

The 2,485 new headwords are A1 80, A2 240, B1 771 and B2 1,394. They are candidate
headwords, not new SpeakSeed words. The dictionary/example sets do not overlap on a
complete new record, so publishing any of them would require inventing or machine-
translating a bilingual example. Phase 4 intentionally does not do that.

All 4,213 released words still have a Vietnamese meaning, IPA, part of speech, CEFR,
English example and Vietnamese example. Word IDs and all existing progress references
are unchanged.

## Topic catalog

Migration `017_vocabulary_topics.sql` creates 24 stable topics, many-to-many mappings
and immutable review evidence. It inherits only non-General topic labels already
released in `library_words`, with status `existing_published`; this status is explicitly
not called human review.

| Topic | Published words |
|---|---:|
| Daily Life | 176 |
| Family & Relationships | 72 |
| Food & Drinks | 103 |
| Home & Furniture | 82 |
| Education | 87 |
| Work & Careers | 92 |
| Travel & Tourism | 57 |
| Transportation | 0 |
| Shopping & Money | 0 |
| Health & Body | 54 |
| Sports & Fitness | 0 |
| Technology | 49 |
| Nature & Environment | 86 |
| Animals & Plants | 0 |
| Entertainment | 0 |
| Hobbies & Leisure | 0 |
| Emotions & Personality | 68 |
| Clothing & Fashion | 0 |
| Communication | 72 |
| Science | 0 |
| Business & Finance | 0 |
| Society & Culture | 246 |
| Places & Directions | 0 |
| Weather & Seasons | 0 |

There are **1,244 classified words** and **2,969 explicitly unclassified words**. Empty
topics remain visible but disabled for a CEFR level with no published words. No broad
`General` word was silently assigned from its spelling alone.

## Learning experience

The Vocabulary page now has CEFR and topic modes, topic cards, per-level counts,
search, new/learning/mastered filters and topic progress. Flashcards support English →
Vietnamese and Vietnamese → English, Web Speech playback, reveal, remembered/not-
remembered actions and the existing due-review queue. A word mapped to multiple topics
still has one `(user_id, word_id)` SRS record.

The topic-filtered set feeds the existing vocabulary multiple-choice game. Listening
selection uses Web Speech and never Gemini TTS. The existing Vietnamese → English mode
remains available. Phase 3 questions are not exposed unless they are published,
human-reviewed and QA PASS; the current published Phase 3 count remains zero.

## Enrichment visibility

The Phase 2 sidecar contains 83,861 values for 4,104 words: 22,795 English definitions,
29,378 English examples and 31,688 synonyms. All remain `pending`; human-reviewed: 0.
Learner APIs now have a safe display path, but return an enrichment value only when its
row is `human_reviewed` **and** an approval event with reviewer identity exists. Thus no
pending synonym/definition/example is currently displayed.

## Review and publication controls

`tools/vocabulary_topics.py` provides local list/propose/approve/reject/publish/report
commands. New mappings start pending. Publication requires a published base word,
`human_reviewed` status, immutable named-review evidence and explicit
`--confirm-publish`. There is no public admin endpoint.

## Source assessment for further expansion

- Kaikki/Wiktionary can provide reusable dictionary fields under Wiktionary's
  share-alike/GFDL terms, but it does not by itself guarantee a Vietnamese translation
  and bilingual learner example for each CEFR headword.
- Tatoeba remains suitable only with sentence-level attribution/license handling; the
  current local snapshot produced 105 new-headword examples but no complete overlap
  with the trusted dictionary+IPA candidates.
- The CLC English–Vietnamese corpus page exposes samples but no sufficiently clear
  redistribution/commercial license was found, so it was not imported.
- The reviewed Hugging Face aggregate has missing licensing information and mixed
  upstream obligations; it was rejected for automatic import.
- ELRA's corpus is paid/licensed and was not acquired.

No new dataset was downloaded or imported during this assessment.

## Database and deployment

- Latest SQLite schema: `017_vocabulary_topics.sql`.
- Application tables: 54.
- SQLite integrity and foreign-key checks pass.
- PostgreSQL migration 017 uses native PostgreSQL functions/triggers and is included in
  the explicit 011–017 migrator.
- PostgreSQL runtime migration remains **BLOCKED** because Docker is unavailable and no
  authorized staging URL was supplied. Neon production was not contacted.
- The SQLite → PostgreSQL release preflight now treats 4,213 published words as a
  protected minimum (so reviewed expansion is allowed) while keeping the 100 lessons
  and 1,000 exercises as exact anti-duplication checks.

Safe production order: back up and verify PostgreSQL staging; apply 011–017 explicitly;
verify 4,213 baseline words, accounts and progress; deploy code; test public topic
counts and two-account isolation; review new mappings with named humans; publish only
explicit approved batches. Do not expand the health baseline by overwriting SQLite or
auto-running migrations in Vercel startup.

## Tests

- Pytest: **94 passed**, 0 failed; one third-party Starlette/httpx deprecation warning.
- Browser E2E: **16/16 passed**, including topic learning and 390px responsive checks.
- JavaScript errors captured: **0**.
- Focused topic/migration/API tests: **13/13 passed**.

The important blocker for 6,000–8,000 learnable words is content, not schema: at least
1,787 complete, licensed, pedagogically suitable records still need a trustworthy
Vietnamese meaning, IPA/POS/CEFR and paired English–Vietnamese example, followed by real
content review. Current sources do not meet that intersection without unsupported
translation or filler content.

## Phase 4 files

- Database: `migrations/017_vocabulary_topics.sql`,
  `deploy/postgres/017_vocabulary_topics.sql`.
- Backend and migration tooling: `app.py`, `tools/vocabulary_topics.py`,
  `tools/audit_vocabulary_phase4.py`, `tools/migrate_to_postgres.py`,
  `tools/apply_postgres_content_phase2.py`.
- Frontend: `static/index.html`, `static/app.js`, `static/style.css`.
- Tests: `tests/test_vocabulary_topics.py`, `tests/test_migrations.py`,
  `tests/test_database_operations.py`, `e2e/run_stage6.py`.
- Documentation: `DATA_SOURCE_AUDIT.md`, `CONTENT_PIPELINE_RUNBOOK.md`, `README.md`,
  this report.
