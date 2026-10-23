# SpeakSeed Phase 6 — Data provenance recovery and first vocabulary release

Date: 2026-10-23
Scope: local SQLite staging only; no Neon, deployment, Gemini, fake reviewer, or publication.

## Outcome

Phase 6 identified the root provenance failure and prepared one real 100-word review
queue. The 4,213 published words and all existing learning data were preserved. No
new word is reported as published.

| Result | Exact count |
|---|---:|
| Candidates audited | 2,485 |
| Existing candidates with Vietnamese meaning audited | 2,220 |
| Existing candidates with IPA audited | 2,220 |
| Meaning fields `VERIFIED` | 0 |
| IPA fields `VERIFIED` | 0 |
| Candidates `CONDITIONAL` with replacement evidence | 100 |
| Candidates still `UNVERIFIED` | 2,120 |
| Candidates `RESTRICTED` | 0 |
| Candidates requiring a source/replacement because meaning is missing | 265 |
| Vietnamese meaning fields replaced | 100 |
| IPA fields replaced | 0 |
| Core-ready / review-ready | 100 |
| First real review batch | 100 |
| Human-reviewed in this phase | 0 |
| Newly published in this phase | 0 |
| Learnable published vocabulary before / after | 4,213 / 4,213 |

The primary candidate categories are mutually exclusive: 100 `CONDITIONAL`, 2,120
`UNVERIFIED`, 265 `REPLACE/needs source`, 0 `VERIFIED`, and 0 `RESTRICTED`.
`UNVERIFIED` rows also carry a non-destructive replacement recommendation.

## Root cause and evidence

The Skypedia database is labeled CC BY-SA 4.0 at repository/database level, but its
SQLite schema does not identify the upstream source of an individual definition or
IPA. Its attribution file describes multiple definition sources and an IPA correction/
G2P fallback pipeline. Therefore 2,220 meanings and 2,220 IPAs cannot honestly be
called field-level verified. Hashes and the dataset claim remain in each candidate's
audit trail; none was silently promoted.

The replacement source is the vi.wiktionary dump dated 2026-10-02, extracted by
Kaikki on 2026-10-21. The downloaded gzip SHA-256 is
`dcdaf93d642ae1d1c4d495b68d90eb572fac86d00281044cf804e0d98147a25e`.
The stream contained 425,353 records, including 133,548 English records. There were
2,127 structurally usable exact word/POS matches; 62 matched records failed the
conservative gloss checks. After requiring an existing topic proposal, one staged
WordNet sense, and lexical agreement with the legacy value as a QA witness, 251
candidates remained eligible. The first 100 were written to the review queue.

The imported meaning is `CONDITIONAL`, not `VERIFIED`: Wikimedia permits commercial
reuse under the selected CC BY-SA 4.0 path, provided attribution, change indication,
ShareAlike, and no extra restrictions are honored. SpeakSeed now stores the exact
snapshot line and page URL per meaning and exposes `/data-attribution`. A human must
still inspect the page/sense and any page-specific notice before approval.

Primary evidence:

- [Skypedia attribution and derivation chain](https://github.com/skypediacode/english-vietnamese-dictionary/blob/main/ATTRIBUTION.md)
- [Kaikki vi.wiktionary snapshot metadata](https://kaikki.org/viwiktionary/rawdata.html)
- [Wikimedia licensing and reuse terms](https://foundation.wikimedia.org/wiki/Terms_of_Use#7._Licensing_of_Content)
- [CC BY-SA 4.0 deed](https://creativecommons.org/licenses/by-sa/4.0/)

This is an engineering provenance self-audit, not independent legal advice.

## Core and topic status

The review batch contains 7 A1, 36 A2, and 57 B1 candidates. Every row passes the
server `core_errors` gate and remains `review_status=pending`. IPA is blank for these
rows because the old IPA chain is unknown and Core v1 does not require it.

Topic mappings were kept separate:

- Published mappings: 1,244 for 1,244 words.
- Pending proposals: 2,917.
- Separate high-confidence review artifact: 200 pending proposals with confidence
  at least 45; no proposal was approved or published.
- Topic mappings human-verified in Phase 6: 0.
- Published coverage before/after: 29.53% / 29.53%.
- Potential coverage including pending proposals: 3,157 / 4,213 = 74.93%; this is
  not published coverage.

## Preservation evidence

The staging database reports `PRAGMA integrity_check=ok` and zero foreign-key
errors. It still contains 24 vocabulary topics, 100 grammar lessons, 1,000 grammar exercises, 500
review-eligible question drafts, and 83,861 enrichment values. It has zero users and
zero progress because it is the Phase 5 staging copy. The canonical `speakseed.db`
was not modified. Schema remains `019_content_license_decisions.sql`; no schema
migration was needed.

The canonical database was rechecked after the staging run. Its SHA-256 is
`0dbdfe614b1e5215113c2c8619c591215e88bf08fc95e8f1b6ac64bae3dd354a`;
`PRAGMA integrity_check` is `ok`, the foreign-key error count is zero, and it still
contains 4,213 published vocabulary entries. No command in this phase opened the
canonical database for writing.

## Test evidence

| Check | Result | Evidence |
|---|---|---|
| Full pytest suite | **PASS** | 105 passed, 1 dependency deprecation warning, 73.53 s |
| Desktop/mobile browser E2E | **PASS** | 16/16 flows passed; no JavaScript exception; mobile viewport 390 px |
| Protected review UI E2E | **PASS** | 200 cards loaded; unauthorized and invalid-CSRF requests both rejected with 403 |
| Import/recovery idempotency | **PASS** | Re-running the recovery tool keeps the same 100 pending rows and creates no publication or review evidence |
| SQLite integrity / foreign keys | **PASS** | `ok` / 0 errors on the Phase 5 staging copy |
| PostgreSQL staging | **BLOCKED** | No separately authorized PostgreSQL staging URL was supplied |

The full E2E run covered placement, vocabulary/SRS, topic learning, grammar,
listening, reading, writing failure preservation, speaking failure behavior,
disabled Gemini TTS, microphone guard, reload persistence, session rotation, and
mobile layout. The run used an isolated local QA database and did not call Gemini.
Artifacts are `qa_artifacts/phase6-first-review-batch.json`,
`qa_artifacts/phase6-topic-review-batch.json`,
`qa_artifacts/phase6-review-e2e.json`, and
`qa_artifacts/phase6-e2e/stage6_e2e_result.json` (the QA directory is intentionally
gitignored).

## Files changed for Phase 6

- Provenance and licensing: `data/source_registry.json`, `ATTRIBUTION.md`,
  `DATA_SOURCE_AUDIT.md`, `static/data-attribution.html`.
- Recovery and release gates: `tools/recover_vocabulary_phase6.py`,
  `vocabulary_release.py`, `tools/vocabulary_topics.py`.
- Learner/admin exposure: `app.py`, `static/index.html`.
- Verification: `tests/test_vocabulary_provenance_phase6.py`,
  `e2e/run_stage6.py`.
- Operations and evidence: `CONTENT_PIPELINE_RUNBOOK.md`, this report, and the
  gitignored QA artifacts listed above.

No migration was added in Phase 6. Schema `019_content_license_decisions.sql`
already stores the required source, decision, audit, review, and publication data.

## Review and publication procedure

1. Follow section 12 of `CONTENT_PIPELINE_RUNBOOK.md` to reproduce the snapshot and
   batch on a verified staging copy.
2. Register real reviewer/publisher accounts normally, then grant explicit roles via
   `tools/vocabulary_review_admin.py`; the tool does not create accounts.
3. Start against the staging DB and open `/internal/vocabulary-review`.
4. Filter source `kaikki-viwiktionary-en-2026-10-02`, license `pass`, QA `pass`, Core
   `review_ready`, review `pending`.
5. Inspect the exact vi.wiktionary page, meaning, CEFR, and proposed topic. Approve
   only rows actually checked, with a specific reason.
6. A publisher performs the separate publish confirmation.
7. Verify search, CEFR/topic learning, flashcards, EN→VI, VI→EN, Web Speech, and SRS.
8. Back up and apply to PostgreSQL staging only after explicit authorization. Neon
   production remains untouched.

## Open blockers

- 2,120 meanings and all 2,220 legacy IPA fields still lack row-level provenance.
- 265 candidates have no Vietnamese meaning.
- The 100-word queue needs real human linguistic and page-specific license review.
- All 2,917 topic proposals still need human sense review.
- PostgreSQL staging is `BLOCKED`: no separately authorized staging URL was supplied.
- Publication remains blocked until real reviewer and publisher actions occur.
