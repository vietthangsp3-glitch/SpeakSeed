# SpeakSeed — Automated vocabulary release

Date: 2026-10-23
Scope: local SQLite only; no Neon, deploy, push, Gemini call, fake reviewer, or account changes.

## Result

| Metric | Exact count |
|---|---:|
| Previously published words | 4,213 |
| Candidate rows inspected | 2,485 |
| Duplicate candidate rows by normalized headword | 0 |
| Candidate headwords already in the published library | 0 |
| Actually new normalized headwords | 2,485 |
| Eligible for automated release | 2,067 |
| Published successfully | 2,067 |
| Published library after release | 6,280 |
| Remaining blocked | 418 |

All 6,280 published rows have distinct `normalized_word` values. The original 4,213
rows and IDs were not updated. The 2,067 new rows use new IDs and contain a Vietnamese
meaning, POS, CEFR, source and minimum Core learning metadata. Of those rows, 929 have
source-provided IPA, 7 have a topic proposal with confidence at least 70, and 2,060
remain explicitly `Unclassified`. Missing IPA, example, or topic mapping is not treated
as fabricated data and does not block Core flashcards.

No row was marked `human_reviewed`. Each new row has immutable `auto-core-v1`
evidence in `vocabulary_automated_releases`; `checks_json.human_reviewed` is false for
all 2,067 rows.

## Automated release gate

A candidate was released only when all of these checks passed:

1. Exact normalized headword and POS match in the pinned Vietnamese Wiktionary
   snapshot extracted by Kaikki.
2. A conservative Vietnamese primary gloss passed structural and restricted-tag
   filtering.
3. The replacement meaning had lexical agreement with the existing candidate meaning,
   or matched the exact Phase 6 record-level evidence already stored for that row.
4. POS and CEFR A0–B2 were present and the headword format was valid.
5. The source registry had license evidence, commercial-use conditions and attribution.
6. No published row with the same normalized headword existed.

The source snapshot SHA-256 is
`dcdaf93d642ae1d1c4d495b68d90eb572fac86d00281044cf804e0d98147a25e`.
The reused fields remain subject to CC BY-SA 4.0 attribution, change indication and
ShareAlike obligations. `/data-attribution` exposes the public attribution notice.

## Blocked candidates

The 418 blocked rows are mutually exclusive:

- 358: no clean, exact, POS-matched record from the pinned licensed snapshot. This
  includes absent matches and records rejected by conservative gloss/tag validation.
- 52: a clean record existed, but its Vietnamese sense was not independently
  corroborated by the existing candidate meaning.
- 8: a source spot-check had already identified an obsolete, specialist, or unsuitable
  primary sense for the first learner-facing release.

These rows remain outside the published library. Their unresolved legacy meaning/IPA
is not silently treated as licensed evidence.

## Preservation and rollback

Before the production-local transaction, the verified backup and manifest were written
to `qa_artifacts/speakseed-pre-auto-release-20261023.db` and its `.manifest.json`.
The source candidate database and source snapshot were opened read-only. Publication
was one SQLite transaction. User and progress counts were unchanged (both were zero in
this local database); grammar, skills, placement, SRS schema and existing word IDs were
preserved.

The final local database reports schema `020_automated_vocabulary_release.sql`, 6,280
published/unique normalized words, zero missing Core rows, `PRAGMA integrity_check=ok`,
and zero foreign-key errors. PostgreSQL/Neon was not modified. Do not deploy the code or
database migration until migration 020 and the 6,280-row data copy have been verified on
an authorized PostgreSQL staging database.

## Verification

- Full pytest: **110 passed**, one Starlette/httpx dependency deprecation warning.
- Browser E2E on an isolated copy: **16/16 PASS**, desktop and mobile 390 px, no
  JavaScript exceptions.
- Learner API: `/api/words` returned 6,280 rows.
- A newly released word successfully accepted a per-account SRS progress write on the
  isolated QA copy.
- Second execution: 0 rows published; all 2,067 were detected as already published,
  proving idempotency.
- Export `speakseed_vocabulary_export.csv` was refreshed to 6,280 data rows.

## Main implementation files

- `tools/publish_vocabulary_automatic.py`
- `migrations/020_automated_vocabulary_release.sql`
- `deploy/postgres/020_automated_vocabulary_release.sql`
- `tests/test_vocabulary_automatic_release.py`
- `tools/recover_vocabulary_phase6.py`
- `README.md`

The detailed machine-readable plan/result is intentionally gitignored at
`qa_artifacts/vocabulary-auto-release-final.json`.
