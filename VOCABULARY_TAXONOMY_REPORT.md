# SpeakSeed Vocabulary Taxonomy Audit — 2026-10-24

## Outcome

The complete published catalog contains **6,280 unique words**. All 6,280
headwords match CEFR-J Vocabulary Profile 1.5 records and their stored level;
therefore this audit made **0 unsupported CEFR changes**. SpeakSeed's `A0`
label remains an internal pre-A1 onboarding level, not an official CEFR level.

Topic classification started with 1,481 classified and 4,799 unclassified
words. The bilingual, sense-aligned WordNet pass classified **273 additional
words**, withdrew **45 demonstrably incorrect inherited mappings**, and left
**4,526 words unclassified** rather than guessing. A word can retain multiple
published topic mappings when both meanings are defensible.

## CEFR distribution

| Level | Published words |
|---|---:|
| A0 (internal pre-A1) | 0 |
| A1 | 1,000 |
| A2 | 1,152 |
| B1 | 1,957 |
| B2 | 2,171 |
| Unverified | 0 |

CEFR-J comparison: **6,280 matched, 0 unmatched, 0 mismatched**. This is an
automated source comparison, not a claim of independent human validation.

## Published topic distribution

| Topic | Words | Topic | Words |
|---|---:|---|---:|
| daily-life | 213 | family-relationships | 88 |
| food-drinks | 145 | home-furniture | 92 |
| education | 95 | work-careers | 124 |
| travel-tourism | 60 | transportation | 20 |
| shopping-money | 20 | health-body | 102 |
| sports-fitness | 17 | technology | 64 |
| nature-environment | 91 | animals-plants | 46 |
| entertainment | 11 | hobbies-leisure | 6 |
| emotions-personality | 110 | clothing-fashion | 22 |
| communication | 130 | science | 18 |
| business-finance | 10 | society-culture | 246 |
| places-directions | 45 | weather-seasons | 12 |

There are 1,754 classified words and 1,787 published mappings. Counts overlap
because multi-topic membership is supported. The remaining 4,526 words do not
have sufficient high-confidence topic evidence yet.

## Classification and correction rules

- WordNet 3.0 first-sense lexicographer domains are accepted only when the
  published Vietnamese meaning independently confirms the same domain.
- Ambiguous collisions such as `server` (waiter/server), `bank`, `blade`,
  `printer`, `prince`, and `extension` are not released from WordNet evidence
  alone.
- Each automated release stores immutable evidence under
  `wordnet-domain-v1`; it is never labeled `human_reviewed`.
- The 45 withdrawn legacy labels are exact, audited contradictions. Plausible
  multi-topic cases such as email (technology + communication), bus (travel +
  transportation), and mathematics (education + science) are preserved.

## Learning behavior

- `/api/words` now supports validated combined `level` + `topic` filtering.
- The browser filter continues to combine CEFR, topic, search and SRS status.
- A0 vocabulary deliberately uses A1 content because CEFR-J has no official A0
  band. Daily plans query only the learner's level (`A0` maps to A1); B1/B2
  vocabulary is not selected for A0/A1 plans.
- Flashcard, SRS and exercise persistence were not reset or rewritten.

## Tests and integrity

- Pytest: **115 passed**, 1 dependency deprecation warning.
- Chrome desktop/mobile E2E: **PASS** (full account, placement, vocabulary/SRS,
  grammar, four skills, reload/session and 390px responsive flow), with no real
  Gemini call.
- SQLite: `integrity_check=ok`, 0 foreign-key errors.
- PostgreSQL: 65 tables, 81 validated foreign keys, 0 orphan topic mappings,
  0 orphan correction rows.

## Production

- Target verified as the existing SpeakSeed Neon database `neondb`.
- Pre-change backup verified: `qa_artifacts/neon-production-before-taxonomy-20261024.zip`,
  64 tables, 29,778 rows, SHA-256
  `da3fc84f01199d818d4918478a80bd25cafad92a50ac684f4b725a0d27dc308e`.
- PostgreSQL migration 022 was parsed/executed inside a transaction and rolled
  back before the real apply.
- Current schema: `022_wordnet_topic_classification.sql`, 65 tables.
- Preserved after sync: 6,280 unique words, 100 grammar lessons, 1,000 grammar
  exercises, 1 user, 1 session, 2 placement attempts, and all existing progress
  rows (currently 0 vocabulary progress rows).
- Production taxonomy now matches local: 1,754 classified words, 1,787 mappings,
  581 immutable automated evidence rows and 45 correction records.

No Gemini API was called during classification, tests, migration or deployment.
