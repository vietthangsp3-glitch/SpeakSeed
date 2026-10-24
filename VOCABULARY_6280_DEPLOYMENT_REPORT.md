# SpeakSeed 6,280 vocabulary release

Date: 2026-10-24

## Verified local result

- Published vocabulary: **6,280**; unique normalized headwords: **6,280**.
- Missing Vietnamese meaning / POS / CEFR: **0 / 0 / 0**.
- Original release: 4,213; automatically released candidates: 2,067; newly released from the remaining 418 in this run: **0**.
- Published topic mappings: 1,513 across 1,481 words. The new 2,067-word release has 153 classified and 1,914 without a sufficiently reliable mapping. This run added 262 mappings and classified 230 previously unmapped words (146 from the new release).
- Topic automation is recorded as `automated-topic-v1` with immutable evidence; it is not labelled `human_reviewed`.
- SQLite integrity check: `ok`; foreign-key violations: 0; schema: `021_automated_topic_classification.sql`.
- Grammar preserved: 100 lessons and 1,000 exercises. Local user records after removing the E2E-only `.invalid` account: 0 (same as before the test).

## Tests

- Pytest: **111 passed**, 1 third-party Starlette deprecation warning.
- Browser E2E: **16/16 PASS**, desktop and 390 px mobile; no JavaScript exceptions. Covered account/session, CSRF, placement, vocabulary/SRS/topic learning, grammar, listening, reading, writing failure preservation, speaking failure guard, browser speech and reload persistence.
- PostgreSQL migration plan: 64 tables, 29,812 rows, 80 foreign keys, 6,280/100/1,000 content counts.

## Production status

- Neon production was backed up and verified before mutation: 35 tables, 20,833 rows,
  archive SHA-256 `f0ec1c1ce1a8d5278f196fbd1b2232848068681399b61c197f825e14725a367c`.
- Migrations 009–021 and the content sync completed successfully. Neon now has 64
  tables, schema 021, **6,280** unique published words, 15,635 attributions, 24
  topics and 1,513 published topic mappings.
- Preservation checks passed: 1 user, 1 session and 2 placement attempts remained
  unchanged; 100 lessons and 1,000 exercises remain published; no SRS orphan or
  unvalidated foreign-key constraint was found.
- Before the new application commit was pushed, the live website already returned
  6,280 words from Neon but correctly reported degraded health because the old
  deployed code only recognized the previous schema count. The post-deploy result
  is recorded in the final task report.
- Sync tooling is dry-run by default, requires exact host/database confirmation for writes, exports a content-only rollback snapshot, refuses ID collisions, does not update existing words, and never reads or writes account/progress/SRS tables.

## Authorized production sequence

With the authorized Neon pooled URL in the current PowerShell session as `DATABASE_URL`:

```powershell
python tools/apply_postgres_placement_v2.py
python tools/apply_postgres_placement_v2.py --apply
python tools/apply_postgres_content_phase2.py
python tools/apply_postgres_content_phase2.py --apply
python tools/sync_published_vocabulary_to_postgres.py
python tools/sync_published_vocabulary_to_postgres.py --apply --confirm-host "<exact-neon-host>" --confirm-database "<exact-database-name>"
python tools/verify_postgres_migration.py --target-url $env:DATABASE_URL --source speakseed.db
```

No Gemini API was used by any migration, backup, verification or deployment step.
