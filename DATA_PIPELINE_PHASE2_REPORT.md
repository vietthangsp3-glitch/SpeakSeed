# SpeakSeed open-data pipeline — Phase 2 report

Date: **2026-10-23**

## Outcome

Phase 2 was implemented and exercised against `qa_artifacts/phase2-staging.db`, an
ignored local copy. No Neon connection, production migration, publication, Git push,
Vercel deployment or Gemini request was made.

The released content remains **4,213 published words**, **100 grammar lessons** and
**1,000 grammar exercises**. `library_words` contains three additional unpublished
rows (4,216 total); they were already present and are not counted as released words.

## Actual staging imports

| Source | Processed | Accepted | Rejected | Status |
|---|---:|---:|---:|---|
| CEFR-J 1.5 | 7,799 | 7,627 | 172 | staged |
| Tatoeba/ManyThings EN–VI snapshot 2026-02-13 | 12,628 | 12,626 | 2 | staged, conditional license acknowledged locally |
| Princeton WordNet 3.0 | 206,978 | 204,545 | 2,433 | staged |
| Elispeak common mistakes | 40 | 40 | 0 | staged |
| **Total** | **227,445** | **224,838** | **2,607** | unpublished |

Rejection reasons: CEFR-J 171 conservative headword-format failures and one duplicate
stable key; WordNet 2,396 headwords outside the conservative format and 37 duplicate
stable keys; Tatoeba two duplicate English–Vietnamese pairs. Rejected rows remain
auditable by batch/reason. Source hashes and complete JSON reports are generated in
the ignored `qa_artifacts` directory.

## Vocabulary enrichment

Enrichment is field-level and stored in sidecar tables. It does not update
`library_words`, replace stronger fields, or change a `word_id`.

| Field | Values | Distinct words |
|---|---:|---:|
| English definition | 22,795 | 4,104 |
| English example | 29,378 | 3,424 |
| Synonym | 31,688 | 3,716 |
| **Any new field** | **83,861** | **4,104** |

CEFR/POS candidates matching already populated base fields were skipped (10,080
field matches). No trusted imported value was available for IPA, word forms,
collocations, antonyms, Vietnamese meanings or Vietnamese example translations, so
those fields were not invented. All sidecar values are `automated_checked/pending`;
**human-reviewed enrichment: 0**.

## Staging question bank

There are **190** unpublished drafts:

| Type | A0 | A1 | A2 | B1 | B2 | Total |
|---|---:|---:|---:|---:|---:|---:|
| Error correction (Elispeak) | 0 | 0 | 10 | 24 | 6 | 40 |
| Fill blank (Tatoeba) | 0 | 46 | 3 | 1 | 0 | 50 |
| Sentence ordering (Tatoeba) | 0 | 39 | 6 | 3 | 2 | 50 |
| Listening gap-fill (Tatoeba) | 0 | 43 | 5 | 0 | 2 | 50 |
| **Total** | **0** | **128** | **24** | **28** | **10** | **190** |

Tatoeba drafts are restricted to 4–10 word sentences where every token maps to a
published SpeakSeed CEFR word. They retain sentence IDs/contributor attribution,
the English source, Vietnamese translation and answer. Their CEFR is an automated
vocabulary-ceiling heuristic, not a human CEFR judgment.

All 190 drafts are queued for review. The 150 Tatoeba drafts have a derived Vietnamese
answer explanation and are structurally eligible for review. The 40 Elispeak drafts
still require a human-written/checked Vietnamese explanation before approval.
**Human-reviewed: 0. Published: 0.** No multiple-choice or reading-comprehension draft
was generated because a reliable distractor/rationale or passage-question source was
not available locally; generating filler would violate the quality requirement.

## Implementation

- Streaming adapters: CEFR-J CSV, Tatoeba TSV, WordNet 3.0 tarball and Elispeak JSONL.
- Bounded commits, persistent source-row checkpoint, deterministic replay/resume,
  idempotent batch identity and per-batch rejection logs.
- Batch rollback removes staging rows and rejection logs and refuses a batch linked
  to question drafts.
- Local review CLI supports list/show/approve/reject, mandatory reviewer identity,
  mandatory reason and immutable review events. Approval never publishes.
- SQLite migrations 012–014 add rejection, enrichment, payload/attribution and
  review/publish safeguards. PostgreSQL equivalents and an explicit advisory-locked
  migrator are under `deploy/postgres`; they do not run at web startup.
- `app.py` still requires only `010_placement_order_drafts.sql` on PostgreSQL startup.
  Therefore deploying application code does not prematurely require the new offline
  content schema. Before deploying code that reads Phase-2 tables, apply 011–014 first.

Phase-2 files added/changed:

- `tools/content_pipeline.py`, `tools/enrich_vocabulary.py`,
  `tools/content_review.py`, `tools/report_content_phase2.py`
- `tools/apply_postgres_content_phase2.py`, `tools/migrate_to_postgres.py`
- `migrations/012_content_pipeline_phase2.sql`,
  `migrations/013_content_question_payload.sql`,
  `migrations/014_content_review_hardening.sql`
- `deploy/postgres/011_content_import_pipeline.sql` through
  `deploy/postgres/014_content_review_hardening.sql`
- `tests/test_content_pipeline.py`, `tests/test_migrations.py`,
  `tests/test_database_operations.py`
- `CONTENT_PIPELINE_RUNBOOK.md`, `README.md` and this report

Migration 010 is a SQLite table-rebuild and is intentionally not sent verbatim to
PostgreSQL; the existing `tools/apply_postgres_placement_v2.py` provides its PostgreSQL
path. Phase-2 PostgreSQL scripts use PostgreSQL DDL/PLpgSQL, not SQLite `RAISE` syntax.

## Test evidence

- Focused content/migration/database tests: **18 passed**.
- Full pytest: **80 passed, 1 Starlette/httpx deprecation warning**.
- Browser E2E on a disposable seeded copy: **15/15 PASS**, zero JavaScript page errors.
  It covered registration, cookies/XSS, CSRF, 40-question placement, SRS, grammar,
  listening, reading, writing/speaking failure guards, disabled Gemini TTS, microphone
  guard, reload persistence, session rotation and 390px mobile layout.
- Staging SQLite: integrity `ok`, zero foreign-key errors, 45 application tables.
- PostgreSQL runtime migration test: **BLOCKED** because Docker daemon is unavailable
  and no authorized PostgreSQL staging URL was provided. No claim of runtime PASS is made.

## Remaining work before Phase 3

1. Human reviewers must inspect the 190 drafts, add/check the 40 missing Vietnamese
   explanations and record approve/reject reasons.
2. Add licensed, learner-appropriate sources for vocabulary multiple-choice and
   reading comprehension; do not derive arbitrary distractors.
3. Obtain reliable licensed data for the enrichment fields still absent.
4. Rehearse 011–014 on an authorized disposable PostgreSQL instance, verify table,
   index, trigger, FK and row counts, then test rollback from a backup.
5. A future publication command/API needs separate authorization and tests. It is
   intentionally absent from Phase 2.

## Safe Neon/Vercel order

1. Back up Neon and restore it to a disposable staging project; never use production
   credentials for rehearsal.
2. Verify schema through 010 and run the Phase-2 PostgreSQL migrator explicitly.
3. Verify `schema_migrations`, table/index/trigger presence, FK integrity and content
   counts. Do not copy local staging drafts into production before review approval.
4. Deploy application code only after the schema needed by that code exists. Current
   `app.py` requires 010, so it will not auto-run 011–014 in a Vercel cold start.
5. Keep migrations out of Vercel Functions. Roll back application code first if a
   deploy fails; restore the database only from a tested backup when required.
