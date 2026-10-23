# SpeakSeed open-data pipeline — Phase 1 report

Date: **2026-10-23**

## Outcome

Phase 1 is implemented and tested locally. It adds a license-gated, idempotent staging layer and a deterministic dry-run importer without changing published learning content or user progress. No network dataset was bulk-downloaded; Neon and Vercel were not modified.

## Baseline verified before changes

| Item | Actual local value |
|---|---:|
| SQLite application tables before Phase 1 migration | 36 |
| Applied schema before Phase 1 | `010_placement_order_drafts.sql` |
| Published vocabulary | 4,213 |
| Distinct normalized published vocabulary | 4,213 |
| Published vocabulary complete in all required legacy fields | 4,213 |
| Unpublished vocabulary | 3 |
| Grammar lessons / exercises | 100 / 1,000 |
| Grammar examples | 200 |
| Four-skills lessons / questions | 60 / 90 |
| Word attribution rows | 12,639 (three provenance groups per published word) |
| Users/progress in the inspected local SQLite | 0 / 0 |

The production Neon database was not queried or written during this phase. Its contents are therefore not claimed by this report.

## Implemented

- `DATA_SOURCE_AUDIT.md` records decision, license evidence, commercial-use status, obligations, available fields and integration limits for 12 source entries.
- `data/source_registry.json` is a machine-readable allow/condition/deny registry. A rejected or commercially unverified source is blocked before parsing.
- Migration `011_content_import_pipeline.sql` adds five tables for source audits, batches, staging records, review evidence and unpublished question drafts.
- The new CLI supports source audit, dry-run, staging and batch rollback. It streams source input through adapters and does not load a large source file into a single raw string.
- CEFR-J 1.5 CSV and Elispeak JSONL adapters normalize deterministically and never invent missing Vietnamese, IPA, CEFR or explanations.
- Identical source version + SHA-256 + importer version reuses the completed batch instead of duplicating records.
- Question-draft database triggers reject publication when human-review evidence, answer, Vietnamese explanation, source or license is missing.
- The legacy importer can no longer publish directly. Higher-risk legacy source routes are blocked and point operators to the audited pipeline.
- Windows PowerShell output falls back to escaped JSON when the console exposes a legacy code page; UTF-8 report files retain Vietnamese correctly.

## Real dry-run evidence

The complete pre-existing CEFR-J 1.5 CSV was parsed locally:

| Metric | Count |
|---|---:|
| Processed rows | 7,799 |
| Valid staging candidates | 7,627 |
| Rejected | 172 |
| Invalid conservative headword format | 171 |
| Duplicate stable key | 1 |
| Published | 0 |
| Marked human-reviewed | 0 |

SHA-256: `b0dd3c635f1c9a4fdf1490c7e5b7c48e8bbe55b652ad0c9860a95f98e10ae498`.

A 250-row real sample was staged into an ignored disposable SQLite database: 244 valid, 6 rejected. Re-running the same command returned `idempotent_reuse: true`, with one batch and 250 staging rows. Nothing was written to `library_words`.

The existing vocabulary builder was also run in dry-run mode and still produced exactly **4,213** complete candidates: A1 959, A2 972, B1 1,331, B2 951. No vocabulary was added or replaced.

## Not implemented / intentionally blocked

- No automatic publication workflow or public admin API exists yet.
- No source can be marked `human_reviewed` by import.
- Kaikki, Tatoeba, Common Voice, Openjam, QuALITY, WordNet and Words-CEFR adapters are not implemented in the new pipeline yet. Auditing a source is not equivalent to importing it.
- No new question, translation, explanation, audio or vocabulary record was published.
- No PostgreSQL migration 011 was applied to Neon. The web application continues to require schema 010, so the existing deployment is not broken by this offline work.
- No attempt was made to claim human validation of the existing 4,213 vocabulary items or 1,000 grammar exercises.
- A content-review CLI/UI and an authenticated publish command remain Phase 2/3 work.

## Data and license risks still open

1. The existing Vietnamese dictionary is CC BY-SA and aggregates upstream resources; expansion should wait for a deeper field-level provenance/legal review.
2. Tatoeba audio licenses are independent from text licenses and must be checked per clip.
3. Common Voice access/re-hosting terms must be honored even where a release is CC0.
4. Openjam translations are described as AI-generated/community-reviewed; row-level review evidence is not available from the repository description alone.
5. QuALITY article licenses are record-specific and its long passages are generally unsuitable for direct A0–B2 use.
6. Words-CEFR's compiled-data relicensing and upstream chain are not sufficiently established, so it is blocked.

## Test evidence

Focused Phase 1 suite:

```text
13 passed in 1.44s
```

This covers migration repeatability, real-format dry-run behavior, idempotent staging, license rejection, conditional-source acknowledgement, publication guards, rollback isolation, Windows console output and the existing vocabulary importer/data-quality checks.

Full project suite after updating the PostgreSQL preflight to schema 011:

```text
76 passed, 1 warning in 54.83s
```

The warning is Starlette's deprecation notice for its current `httpx` TestClient bridge; it is not a failed behavior test.

Browser E2E against an isolated copy of the seeded SQLite release:

```text
15/15 steps PASS
0 JavaScript page errors
```

Covered desktop load, registration/cookies/XSS, CSRF, the 40-question placement flow, vocabulary SRS, grammar, Listening, Reading/save-word, Writing and Speaking failure safety, disabled Gemini TTS, microphone/Live guard, reload persistence, login/session rotation and a 390px mobile viewport. Gemini credentials were blank and no real AI call was made. The E2E report is in ignored QA artifacts, not committed learning data.

Two setup attempts were not counted as application PASS: the first was intentionally rejected by the origin allowlist because the non-default test port was not configured; the second used an empty database and correctly exposed that Placement requires seeded vocabulary. The final run used a disposable copy of the seeded database and passed all 15 steps.

Final canonical SQLite verification after tests:

```text
PRAGMA integrity_check: ok
PRAGMA foreign_key_check: 0 errors
schema: 011_content_import_pipeline.sql
tables: 41
published vocabulary: 4,213
published grammar: 100 lessons / 1,000 exercises
staging records: 0
users: 0
```

## Safe operating instructions

See `CONTENT_PIPELINE_RUNBOOK.md`. All examples use an ignored disposable database. A future PostgreSQL publish requires a separate backup, migration rehearsal, content review and explicit authorization; it must not run from FastAPI startup or a Vercel Function.
