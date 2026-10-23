# SpeakSeed Phase 5 — Vocabulary growth and safe content release

Date: **2026-10-23**

## Outcome

Phase 5 implements the versioned `core-v1` quality policy, protected batch-review UI,
isolated internal preview, immutable review/license evidence, transactional publication
and controlled rollback. It does not claim unverified content as released. No Neon,
Vercel, Git push, production migration or Gemini request was used.

The canonical database contains released content only. The Phase 2/3 staging assets
(500 question drafts and 83,861 enrichment values) are in
`qa_artifacts/phase2-staging.db`; they were never mixed into `speakseed.db`.

## Vocabulary audit

| Measure | Before | After |
|---|---:|---:|
| Published vocabulary | 4,213 | **4,213** |
| New CEFR-J headwords found | — | 2,485 |
| Candidates with Vietnamese meaning and IPA | — | 2,220 |
| Candidates with bilingual example | — | 105 |
| Candidates with a semantic topic proposal | — | 1,269 |
| Otherwise Core-complete except license/human review | — | 1,141 |
| Core-ready for human review now | — | **0** |
| Human-reviewed candidates | — | **0** |
| Newly published words | — | **0** |
| Internal-preview candidates | — | 2,485 |
| License-blocked candidates | — | 2,485 |
| Missing Vietnamese meaning | — | 265 |
| Missing CEFR | — | 0 |
| Missing topic proposal | — | 1,216 |
| Duplicate/invalid new candidates | — | 0 |

The 2,220 dictionary matches are not considered verified merely because they are
non-empty. Their Skypedia fields remain blocked until the upstream provenance/license
review recorded in the source audit is genuinely resolved. Of these, 1,141 already
have automated QA and at least one WordNet-based topic proposal; a valid recorded
license decision would make them review-ready, not human-reviewed.

Candidate distribution:

| CEFR | Candidates | Meaning + IPA | Bilingual example | Topic proposal |
|---|---:|---:|---:|---:|
| A1 | 80 | 48 | 27 | 51 |
| A2 | 240 | 195 | 22 | 159 |
| B1 | 771 | 677 | 37 | 414 |
| B2 | 1,394 | 1,300 | 19 | 645 |

## Core and Enriched policy

Migration 018 records `core-v1`. Core requires a normalized headword, POS, trusted
Vietnamese meaning, sourced CEFR, confirmed topic, field provenance, publishable
license, automated QA PASS and current human review. IPA and bilingual examples are
Enriched fields and may be added later. Blank optional fields are never replaced with
fabricated text; learner UI continues to use browser speech for the English headword.

Every approval is tied to a content revision. Editing content or topics invalidates
the approval. QA PASS never changes `review_status` to `human_reviewed`.

## Topic classification

There are still 24 topics. Published mappings remain **1,244 words (29.53%)**. Exact-
token semantic analysis of WordNet definitions/synonyms produced **2,917 pending
mappings for 1,913 additional words**. If reviewed and published, combined coverage
would be **3,157/4,213 (74.92%)**.

| CEFR | Words | Published classified | With pending proposals |
|---|---:|---:|---:|
| A1 | 959 | 259 | 758 |
| A2 | 972 | 235 | 720 |
| B1 | 1,331 | 417 | 1,000 |
| B2 | 951 | 333 | 679 |

The 80–90% goal was not claimed: 1,056 broad/function/abstract words lack sufficiently
specific semantic evidence for one of the 24 topics. Proposed mappings are invisible
to learners, human-reviewed mappings: 0, newly published mappings: 0. No word id or SRS
row was duplicated.

## Review UI and internal preview

`/internal/vocabulary-review` requires a server-side `reviewer`, `publisher` or `admin`
role. No account receives a role automatically. Cookie writes require CSRF protection.
The UI supports filters for CEFR, topic, source, license, QA/review/Core status and
missing fields; it displays provenance, warnings, preview, draft editing, topic editing,
batch approve/reject/needs-revision and separate publish confirmation.

Preview is explicitly labeled `CHƯA KIỂM DUYỆT / INTERNAL PREVIEW`, is unavailable to
public APIs and never writes official SRS progress. In production it additionally
requires `INTERNAL_REVIEW_ENABLED=true`; authorization is still mandatory.

Batch size is limited to 200. Approval requires every Core gate, reviewer-selected
topics and a reason. Publication is transactional and requires a publisher/admin.
Controlled rollback refuses to proceed once learner progress references a new word;
it never deletes the word row.

## How to review the first 100 words

1. Work on a backup-derived staging database and register the real reviewer normally.
2. Grant `reviewer` and `publisher` explicitly with `tools/vocabulary_review_admin.py`.
3. Complete the Skypedia upstream provenance/license review. Do not continue if it is
   unresolved.
4. An existing admin records the decision with `license-decision`, evidence URL and
   reason. The immutable log changes eligible records to `review_ready`, never to
   `human_reviewed`.
5. Open the internal UI, filter A1 then A2, inspect meaning/POS/CEFR/provenance, confirm
   topics and approve at most 100–200 records with a real reason.
6. Preview them, then use the separate Publish action. Verify counts, word attribution,
   topic mappings and FK integrity before any deployment.

Exact PowerShell commands are in `CONTENT_PIPELINE_RUNBOOK.md`.

## Migrations and preservation

- `018_vocabulary_release_workflow.sql`: policy, roles, candidates, candidate topics,
  immutable events, publication batches/items and Core publication gate.
- `019_content_license_decisions.sql`: immutable evidence-backed source decisions.
- SQLite → PostgreSQL preflight now requires schema 019 and 62 application tables.
- Backups with checksum were created before schema changes. Migration was tested first
  on a restored staging copy, then applied additively to canonical SQLite.

Canonical post-migration evidence: integrity `ok`, foreign-key violations 0, 62 tables,
4,213 published words, 100 grammar lessons and 1,000 grammar exercises. The browser QA
account/progress created by E2E was isolated and the canonical database was restored
from its verified backup before reapplying migrations 018–019.

PostgreSQL staging remains **BLOCKED**: no authorized staging URL was supplied and no
live PostgreSQL migration was run. Apply 011–019 before deploying code; FastAPI does
not run them automatically.

## Tests

- Full pytest: **101 passed**, 0 failed; one third-party Starlette/httpx warning.
- Focused Phase 5/migration tests: **15 passed**, 0 failed.
- Main browser E2E: **16/16 passed**, including 390px mobile and zero JavaScript errors.
- Protected review UI browser smoke: **PASS** at 390px, 200 cards loaded, zero overflow,
  unauthorized access 403 and missing/invalid CSRF 403.
- JavaScript syntax, Python compilation and `git diff --check`: PASS.

PostgreSQL runtime behavior is not marked PASS.

## Phase 5 files

- Migrations: `migrations/018_vocabulary_release_workflow.sql`,
  `migrations/019_content_license_decisions.sql` and PostgreSQL-native counterparts.
- Backend: `vocabulary_release.py`, protected routes in `app.py`, identity-table support
  in `database.py`.
- Pipeline/admin: `tools/prepare_vocabulary_phase5.py`,
  `tools/vocabulary_review_admin.py`, updated PostgreSQL migration tools.
- Internal UI: `static/vocabulary-review.html`, `static/vocabulary-review.js`,
  responsive styles in `static/style.css`.
- Tests: `tests/test_vocabulary_release_phase5.py`, migration/database regressions and
  `e2e/run_vocabulary_review_phase5.py`.

## Remaining blockers and Phase 6 direction

1. Resolve or replace the Skypedia upstream provenance chain before any candidate can
   become Core-ready.
2. Human reviewers must validate the 2,917 topic proposals and candidate meanings;
   automated proposals are not review evidence.
3. Acquire a clearly licensed Vietnamese meaning source for the 265 missing records.
4. Extend the 24-topic taxonomy only if reviewers find repeated legitimate gaps; do not
   force abstract/function words into unrelated topics.
5. Run migrations 018–019, publish fixtures and rollback tests on an authorized
   PostgreSQL staging database before deployment.
