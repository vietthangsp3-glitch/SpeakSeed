# SpeakSeed content-pipeline runbook (Windows PowerShell)

The content pipeline is an **offline local staging tool**. It does not connect to Neon, publish questions, update user progress, call Gemini, or download a dataset during a web request.

## 1. Inspect the audited registry

```powershell
Set-Location 'E:\app\THANG\luyện tiếng anh\speakseed-learning-v3\speakseed-learning-v3'
python .\tools\content_pipeline.py audit --report .\qa_artifacts\source-audit.json
```

Review `DATA_SOURCE_AUDIT.md`, `data/source_registry.json`, the source's exact release and its license before continuing.

## 2. Dry-run a real CEFR-J snapshot

Dry-run parses and validates but does not create or write a database:

```powershell
python .\tools\content_pipeline.py stage `
  --source cefr-j-1.5 `
  --input '.\.source-cache\cefrj\olp-en-cefrj-master\cefrj-vocabulary-profile-1.5.csv' `
  --dry-run `
  --report '.\qa_artifacts\cefrj-dry-run.json'
```

Use `--limit 250` for a quick sample. Files under `.source-cache` and `qa_artifacts` are ignored by Git.

## 3. Stage into a disposable local database

Do this before considering the working SQLite database:

```powershell
python .\tools\content_pipeline.py stage `
  --source cefr-j-1.5 `
  --input '.\.source-cache\cefrj\olp-en-cefrj-master\cefrj-vocabulary-profile-1.5.csv' `
  --database '.\qa_artifacts\content-staging.db' `
  --batch-size 500 `
  --report '.\qa_artifacts\cefrj-stage.json'
```

The checkpoint is committed with every batch. If a run is interrupted, repeat the
same command with `--resume`. Running an already completed command reuses the batch.

Conditional sources require `--accept-conditions`. That flag only acknowledges that the operator has reviewed the conditions; it does not authorize publication:

```powershell
python .\tools\content_pipeline.py stage `
  --source elispeak-common-mistakes `
  --input 'C:\datasets\elispeak\data\common-english-mistakes.jsonl' `
  --database '.\qa_artifacts\content-staging.db'
```

Elispeak is approved for staging and does not need `--accept-conditions`. Its English explanation remains `needs_review`; the importer never creates a Vietnamese explanation.

WordNet and Tatoeba examples:

```powershell
python .\tools\content_pipeline.py stage --source princeton-wordnet-3.0 `
  --input '.\.source-cache\WordNet-3.0.tar.gz' `
  --database '.\qa_artifacts\content-staging.db' --batch-size 1000 --limit 300000

python .\tools\content_pipeline.py stage --source tatoeba-text `
  --input '.\.source-cache\tatoeba\vie.txt' `
  --database '.\qa_artifacts\content-staging.db' --batch-size 500 `
  --accept-conditions
```

## 4. Inspect staged records

Use Python's standard SQLite module if the `sqlite3` executable is not installed:

```powershell
@'
import sqlite3
con = sqlite3.connect(r'.\qa_artifacts\content-staging.db')
for row in con.execute('''
    SELECT b.id,b.source_key,b.status,b.processed,b.accepted,b.rejected
    FROM content_import_batches b ORDER BY b.id
'''):
    print(row)
for row in con.execute('''
    SELECT content_type,validation_status,quality_status,review_status,COUNT(*)
    FROM content_staging_records GROUP BY 1,2,3,4 ORDER BY 1,2,3,4
'''):
    print(row)
con.close()
'@ | python -
```

## 5. Roll back a staging batch

Rollback affects only records linked to the chosen staging batch. It refuses to remove a batch that already has linked question drafts.

```powershell
python .\tools\content_pipeline.py rollback `
  --database '.\qa_artifacts\content-staging.db' `
  --batch-id 1 `
  --report '.\qa_artifacts\rollback-batch-1.json'
```

## 6. Enrichment and draft review

```powershell
python .\tools\enrich_vocabulary.py --database '.\qa_artifacts\content-staging.db'
python .\tools\content_review.py materialize --database '.\qa_artifacts\content-staging.db'
python .\tools\content_review.py materialize-sentences `
  --database '.\qa_artifacts\content-staging.db' --per-type 50
python .\tools\content_review.py list --database '.\qa_artifacts\content-staging.db'
python .\tools\content_review.py show --database '.\qa_artifacts\content-staging.db' --draft-id 1
python .\tools\content_review.py edit --database '.\qa_artifacts\content-staging.db' `
  --draft-id 1 --editor 'Full editor name' --reason 'Rewrite Vietnamese explanation' `
  --explanation-vi 'Giải thích đã được người biên tập viết.'
python .\tools\question_bank_phase3.py audit --database '.\qa_artifacts\content-staging.db'
python .\tools\content_review.py approve --database '.\qa_artifacts\content-staging.db' `
  --draft-id 1 --reviewer 'Full reviewer name' --reason 'Checked prompt, answer, CEFR and explanation'
```

Editing invalidates the previous QA/review state. Run the automated audit again before
approval. Approval writes an immutable audit event but never publishes. There is
intentionally no public admin API and no automatic `human_reviewed` action.

## 7. Phase 3 question-bank workflow

Work only on a disposable staging copy. These commands are idempotent and never
connect to Neon:

```powershell
python .\tools\question_bank_phase3.py stage-existing `
  --database '.\qa_artifacts\phase2-staging.db'
python .\tools\question_bank_phase3.py draft-explanations `
  --database '.\qa_artifacts\phase2-staging.db'
python .\tools\question_bank_phase3.py audit `
  --database '.\qa_artifacts\phase2-staging.db'
python .\tools\report_question_bank_phase3.py `
  '.\qa_artifacts\phase2-staging.db' `
  --output '.\qa_artifacts\phase3-summary.json'
```

Filter, inspect and preview without revealing the answer in learner view:

```powershell
python .\tools\content_review.py list --database '.\qa_artifacts\phase2-staging.db' `
  --level B1 --type error_correction --source elispeak-common-mistakes --limit 20
python .\tools\content_review.py show --database '.\qa_artifacts\phase2-staging.db' --draft-id 1
python .\tools\content_review.py preview --database '.\qa_artifacts\phase2-staging.db' --draft-id 1
python .\tools\content_review.py audit-log --database '.\qa_artifacts\phase2-staging.db' --draft-id 1
```

Publishing is a separate, explicit local operation. Every selected item must have a
fresh human approval and automated QA `PASS`. Sources marked `conditional` also require
the publisher to verify their obligations and pass `--confirm-license-conditions`.
Do not run this example until real review evidence exists:

```powershell
python .\tools\content_review.py publish-batch `
  --database '.\qa_artifacts\phase2-staging.db' `
  --draft-ids '1,2,3' --reviewer 'Full publisher name' `
  --reason 'Release ticket and license evidence reference' `
  --confirm-license-conditions --confirm-publish
```

The Placement Test adapter is disabled by default and falls back to the existing
40-question form. Only after a complete, reviewed, published bank has been verified may
staging set `QUESTION_BANK_PLACEMENT_ENABLED=true`. Never set it merely because drafts
exist.

## 8. PostgreSQL staging (explicit authorization only)

Migration 009/010 uses `tools/apply_postgres_placement_v2.py`; migrations 011–019 use:

```powershell
python .\tools\apply_postgres_content_phase2.py
$env:DATABASE_URL = 'postgresql://...authorized-staging-only...'
python .\tools\apply_postgres_content_phase2.py --apply
Remove-Item Env:DATABASE_URL
```

The default command is a read-only plan. `--apply` is never called by FastAPI startup.
Back up and verify the target first. Do not use the production URL without separate authorization.

## 9. Tests

```powershell
python -m pytest .\tests\test_content_pipeline.py .\tests\test_question_bank_phase3.py .\tests\test_migrations.py -q
python -m pytest -q
```

The canonical database and Neon must be backed up and separately authorized before any future publish/migration step. The importer has no publish or PostgreSQL path.

## 10. Vocabulary topic review

The 24-topic catalog and mappings inherited from already-published vocabulary are
created by migration 017. A new automatic mapping always starts unpublished and cannot
be shown to learners until a named human reviews it:

```powershell
python .\tools\vocabulary_topics.py report --database .\speakseed.db
python .\tools\vocabulary_topics.py propose --database .\speakseed.db `
  --word-id 123 --topic food-drinks --source 'review research reference' `
  --rationale 'This reviewed sense denotes a food item.' --confidence 90
python .\tools\vocabulary_topics.py list --database .\speakseed.db --status pending
python .\tools\vocabulary_topics.py approve --database .\speakseed.db `
  --word-id 123 --topic food-drinks --reviewer 'Full reviewer name' `
  --reason 'Checked this sense and topic'
python .\tools\vocabulary_topics.py publish --database .\speakseed.db `
  --word-id 123 --topic food-drinks --confirm-publish
```

Do not use an automated identity as the reviewer. Rejected or pending mappings are
never returned by learner APIs. Audit the expansion gap without writing data:

```powershell
python .\tools\audit_vocabulary_phase4.py --database .\speakseed.db `
  --output .\qa_artifacts\phase4-vocabulary-audit.json
```

## 11. Phase 5 Core vocabulary review and release

Always work on a verified staging copy, never directly on Neon production:

```powershell
python .\tools\db_backup.py create '.\qa_artifacts\phase2-staging.db' `
  '.\qa_artifacts\phase5-staging-backup.db'
python .\tools\db_backup.py restore '.\qa_artifacts\phase5-staging-backup.db' `
  '.\qa_artifacts\phase5-review.db'
python .\tools\prepare_vocabulary_phase5.py --database '.\qa_artifacts\phase5-review.db'
python .\tools\vocabulary_review_admin.py report --database '.\qa_artifacts\phase5-review.db'
```

Register the real reviewer through the normal application, then explicitly grant a
role. The command refuses to create an account or invent an identity:

```powershell
python .\tools\vocabulary_review_admin.py grant-role `
  --database '.\qa_artifacts\phase5-review.db' `
  --email 'reviewer@example.com' --role reviewer `
  --granted-by 'Full name of project owner'
python .\tools\vocabulary_review_admin.py grant-role `
  --database '.\qa_artifacts\phase5-review.db' `
  --email 'publisher@example.com' --role publisher `
  --granted-by 'Full name of project owner'
```

Run the internal UI with the staging database and visit
`http://127.0.0.1:8000/internal/vocabulary-review` after login:

```powershell
$env:DB_PATH = (Resolve-Path '.\qa_artifacts\phase5-review.db').Path
$env:AUTH_TRANSPORT = 'cookie'
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

No candidate using the current Skypedia-derived fields is license-ready. Only after a
real provenance/legal review may an existing admin record a source decision. This
action is immutable, requires an evidence URL, and does not create human approvals:

```powershell
python .\tools\vocabulary_review_admin.py license-decision `
  --database '.\qa_artifacts\phase5-review.db' `
  --source 'skypedia-en-vi' --decision pass `
  --evidence-url 'https://actual-evidence.example/license-review' `
  --reason 'Reference to the completed provenance and license review' `
  --actor-email 'admin@example.com'
```

Review batches of at most 200 words in the UI. Confirm topics and provide a reason.
Approval records the user id, name, policy `core-v1` and content revision. Publishing
is a second action available only to `publisher`/`admin`. Editing content or topics
invalidates approval. A batch can be rolled back only before any learner progress
references its new words; rollback unpublishes rather than deleting records.

For PostgreSQL staging, back up first, apply 011–019 before deploying code, verify all
counts and only then enable the internal review route. FastAPI startup never applies
these migrations automatically.

## 12. Phase 6 provenance recovery and first review batch

Download the audited vi.wiktionary snapshot only from the pinned Kaikki URL. The
recovery command verifies its SHA-256 and refuses to modify `speakseed.db`:

```powershell
curl.exe -L --fail --retry 2 `
  -o '.\.source-cache\viwiktionary-2026-10-02.jsonl.gz' `
  'https://kaikki.org/viwiktionary/raw-wiktextract-data.jsonl.gz'

python .\tools\recover_vocabulary_phase6.py `
  --database '.\qa_artifacts\phase5-staging-v2.db' `
  --snapshot '.\.source-cache\viwiktionary-2026-10-02.jsonl.gz' `
  --limit 100 --dry-run

python .\tools\recover_vocabulary_phase6.py `
  --database '.\qa_artifacts\phase5-staging-v2.db' `
  --snapshot '.\.source-cache\viwiktionary-2026-10-02.jsonl.gz' `
  --limit 100
```

The write command changes only candidates in the staging copy. It records the old
Skypedia meaning/IPA as `UNVERIFIED`, replaces 100 meanings with record-level
vi.wiktionary evidence, excludes old IPA from release, and leaves every candidate
`pending`. It creates neither users nor roles and never publishes.

For the separate topic-mapping queue:

```powershell
python .\tools\vocabulary_topics.py list `
  --database '.\qa_artifacts\phase5-staging-v2.db' `
  --status pending --min-confidence 45 --limit 200 `
  --output '.\qa_artifacts\phase6-topic-review-batch.json'
```

To review the new-word batch, start the application against the staging copy, sign
in with a real reviewer account, open `/internal/vocabulary-review`, and filter:

- Source: `kaikki-viwiktionary-en-2026-10-02`
- License: `pass`
- QA: `pass`
- Core: `review_ready`
- Review: `pending`

For each row, open the `page_url` in provenance, compare the exact sense, confirm one
topic, and approve with a concrete reason. Do not approve the batch blindly. A real
publisher then reloads with `review=human_reviewed`, checks the selected rows, and
uses the separate Publish action. Verify vocabulary search, CEFR/topic lists,
flashcards, both translation directions, Web Speech, and SRS with a test account.
The public attribution notice is `/data-attribution`.
