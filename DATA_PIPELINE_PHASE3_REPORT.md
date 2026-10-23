# SpeakSeed question bank and lesson integration — Phase 3 report

Date: **2026-10-23**

## Outcome

Phase 3 was implemented and exercised only against the ignored local database
`qa_artifacts/phase2-staging.db`. No Neon migration, production write, content
publication, Git push, Vercel deployment or Gemini request was made.

The existing release remains unchanged at **4,213 published words**, **100 published
grammar lessons** and **1,000 published grammar exercises**. The Phase 3 bank contains
**500 unpublished staging candidates**. This is not a claim that 500 questions have
been checked by a teacher: **human-reviewed: 0; published: 0**.

## Verified staging inventory

Phase 2 contributed 190 drafts. Phase 3 staged 310 candidates derived from existing
SpeakSeed content: 160 grammar multiple-choice questions, 90 vocabulary
multiple-choice questions, 45 reading questions and 15 listening questions. Stable
source/ref IDs make reruns idempotent. Existing content did not inherit a human-review
label, and project ownership must be confirmed before external publication.

| Type | A0 | A1 | A2 | B1 | B2 | Total |
|---|---:|---:|---:|---:|---:|---:|
| Error correction | 0 | 0 | 10 | 24 | 6 | 40 |
| Fill in the blank | 0 | 46 | 3 | 1 | 0 | 50 |
| Listening | 3 | 46 | 8 | 3 | 5 | 65 |
| Multiple-choice grammar | 20 | 20 | 40 | 40 | 40 | 160 |
| Multiple-choice vocabulary | 0 | 0 | 30 | 30 | 30 | 90 |
| Reading comprehension | 9 | 9 | 9 | 9 | 9 | 45 |
| Sentence ordering | 0 | 39 | 6 | 3 | 2 | 50 |
| **Total** | **32** | **160** | **106** | **110** | **92** | **500** |

Source totals are SpeakSeed existing content 310, Tatoeba text 150, and Elispeak 40.
No new external source was downloaded in Phase 3.

## Automated QA and review status

All 500 candidates have a Vietnamese explanation. Forty Elispeak explanations are
clearly prefixed as automated drafts awaiting a reviewer. The current automated audit
result is:

| Result | Questions |
|---|---:|
| PASS | 458 |
| WARN | 42 |
| FAIL | 0 |
| Structurally ready to enter review | 500 |
| Human-reviewed | 0 |
| Rejected by a human | 0 |
| Published | 0 |

Warnings overlap on some questions: 40 draft explanations require human review, 40
error-correction items need a reviewer to check equivalent corrections, two ordering
items may allow another valid order, and one source sentence has potentially unsuitable
tone (`Shut up and eat.`). A warning is not approval. Naturalness, CEFR suitability and
pedagogical value still require a qualified human review, especially at B1–B2.

## Review and publication controls

The local CLI now supports level/type/source filters, full draft view, learner preview,
editing, approve/reject reasons and an immutable audit log. Editing resets the draft to
pending and removes stale automated QA. A direct database change cannot create valid
human-review evidence.

Batch publication requires all of the following: explicit confirmation, named
publisher, reason, fresh human approval, automated QA `PASS`, source/license evidence
and a stored publication snapshot hash. Migration 016 adds a second explicit
confirmation for a source whose license audit is conditional. Published question
content and review events are immutable. No public admin review endpoint was added.

## Placement Test integration

The adapter selects only questions that are published, human-reviewed, QA `PASS`,
linked to `placement`, and marked placement-eligible. It returns a bank form only when
the exact existing 40-question CEFR/skill quota can be satisfied; otherwise the legacy
placement form remains active. The feature flag
`QUESTION_BANK_PLACEMENT_ENABLED` is off by default.

Answers and explanations are removed from the start/list payload. Scoring happens on
the backend. Correct answers, Vietnamese explanation and listening transcript are
returned only after submission. Existing placement attempts retain their own question
snapshot and are not rewritten.

Because no bank item has real human approval or publication, the new adapter is
currently **inactive by design** and the tested legacy Placement Test remains the
fallback.

## Lesson integration

Authenticated published-only APIs are prepared for `vocabulary`, `grammar`,
`listening`, `reading` and `daily_review`. Each submitted answer is stored with
`user_id`; another account cannot access that record through these APIs. Listening
text is delivered privately with `no-store` only when needed by browser Web Speech;
the learner payload does not render the transcript until submission. No Gemini TTS is
used.

Existing lesson screens were not switched to the new bank because published eligible
content is zero. This prevents staging material from replacing working lessons or
changing existing progress.

## Schema and data evidence

- Latest local schema: `016_question_publication_license_gate.sql`.
- Application tables: 51; SQLite integrity: `ok`; foreign-key errors: 0.
- Migrations 015–016 are additive and preserve question IDs, user data and progress.
- PostgreSQL equivalents exist under `deploy/postgres`; the explicit migrator now
  covers 011–016 and never runs from FastAPI startup.
- `app.py` still requires only schema 010 at PostgreSQL startup, so Vercel cold starts
  do not auto-run or prematurely demand the Phase 3 migration.

PostgreSQL runtime test: **BLOCKED**. Docker daemon is unavailable and no authorized
PostgreSQL staging URL was supplied. Static PostgreSQL SQL and adapter paths are covered
by tests, but this is not reported as a live PostgreSQL PASS.

## Test results

- Full pytest after final Phase 3 hardening: **88 passed**, one third-party
  Starlette/httpx deprecation warning, **0 failed** (53.72 seconds).
- Browser E2E desktop/mobile emulations: **15/15 passed**, with zero captured JavaScript
  errors, on a disposable local database. The harness used the tested local origin in
  `ALLOWED_ORIGINS`; an initial run without that origin was correctly rejected with
  HTTP 403 and was not counted as a pass.
- No real Gemini API request was made.

Coverage includes staging visibility, answer-key hiding, post-submit explanations,
published-only selection, backend scoring, user-scoped attempts, edit/review
invalidation, immutable evidence, explicit publish/license gates, listening Web Speech
fallback, old progress preservation and repeatable SQLite migrations.

## Phase 3 files

Added:

- `question_bank.py`
- `tools/question_bank_phase3.py`, `tools/report_question_bank_phase3.py`
- `tests/test_question_bank_phase3.py`
- `migrations/015_question_bank_integration.sql`
- `migrations/016_question_publication_license_gate.sql`
- `deploy/postgres/015_question_bank_integration.sql`
- `deploy/postgres/016_question_publication_license_gate.sql`
- `DATA_PIPELINE_PHASE3_REPORT.md`

Updated for Phase 3:

- `app.py`, `personalization.py`
- `tools/content_review.py`, `tools/apply_postgres_content_phase2.py`,
  `tools/migrate_to_postgres.py`
- `data/source_registry.json`
- `tests/test_migrations.py`, `tests/test_database_operations.py`,
  `tests/test_content_pipeline.py`
- `CONTENT_PIPELINE_RUNBOOK.md`, `README.md`

The working tree also contains earlier uncommitted Phase 1/2 and Placement Test work;
the list above identifies the files materially added or changed for this phase and does
not claim unrelated pre-existing edits.

## Safe deployment order

1. Back up and verify the target; use an authorized PostgreSQL **staging** URL only.
2. Run the explicit 011–016 migrator and verify schema/table/count/foreign-key results.
3. Deploy code while leaving `QUESTION_BANK_PLACEMENT_ENABLED` unset/false.
4. Review drafts with named humans; edit, rerun QA, then approve with reasons.
5. Confirm each conditional license/ownership obligation before an explicit batch
   publish. Do not publish warnings merely to reach a count.
6. Test published-only lesson APIs and a complete 40-item placement matrix in staging.
7. Enable the placement adapter only after those checks. Roll back the application flag
   first if any issue appears; do not rewrite old attempts or delete the SQLite source.

See [CONTENT_PIPELINE_RUNBOOK.md](CONTENT_PIPELINE_RUNBOOK.md) for exact PowerShell
commands. Remaining Phase 4 prerequisites are qualified human review, ownership/license
confirmation for conditional sources, a live PostgreSQL staging run, and learner UI
activation only after reviewed content exists.
