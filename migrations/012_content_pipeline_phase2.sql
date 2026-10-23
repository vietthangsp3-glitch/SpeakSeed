CREATE TABLE IF NOT EXISTS content_import_rejections(
  id INTEGER PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES content_import_batches(id) ON DELETE CASCADE,
  source_record_id TEXT NOT NULL,
  content_type TEXT NOT NULL,
  reason TEXT NOT NULL,
  payload_hash TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE(batch_id,source_record_id,content_type,reason)
);

CREATE TABLE IF NOT EXISTS word_enrichment_candidates(
  id INTEGER PRIMARY KEY,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE CASCADE,
  staging_record_id INTEGER NOT NULL REFERENCES content_staging_records(id) ON DELETE CASCADE,
  field_name TEXT NOT NULL CHECK(field_name IN (
    'cefr','ipa_uk','ipa_us','pos','definition_en','meaning_vi','example_en',
    'example_vi','word_form','collocation','synonym','antonym'
  )),
  value_json TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  source_key TEXT NOT NULL REFERENCES content_sources(source_key),
  source_record_id TEXT NOT NULL,
  confidence INTEGER NOT NULL CHECK(confidence BETWEEN 0 AND 100),
  quality_status TEXT NOT NULL CHECK(quality_status IN ('unverified','automated_checked','needs_review')),
  review_status TEXT NOT NULL CHECK(review_status IN ('pending','human_reviewed','rejected')) DEFAULT 'pending',
  applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(word_id,field_name,normalized_value,source_key)
);

CREATE TABLE IF NOT EXISTS word_enrichment_values(
  id INTEGER PRIMARY KEY,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE CASCADE,
  candidate_id INTEGER NOT NULL UNIQUE REFERENCES word_enrichment_candidates(id) ON DELETE RESTRICT,
  field_name TEXT NOT NULL,
  value_json TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  source_key TEXT NOT NULL REFERENCES content_sources(source_key),
  source_record_id TEXT NOT NULL,
  quality_status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  UNIQUE(word_id,field_name,normalized_value,source_key)
);

CREATE TABLE IF NOT EXISTS word_enrichment_events(
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES word_enrichment_candidates(id) ON DELETE CASCADE,
  reviewer_name TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL CHECK(action IN ('apply_automated','approve','reject','supersede')),
  reason TEXT NOT NULL DEFAULT '',
  occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_import_rejections_batch
  ON content_import_rejections(batch_id,reason);
CREATE INDEX IF NOT EXISTS idx_enrichment_candidates_word
  ON word_enrichment_candidates(word_id,field_name,review_status,applied);
CREATE INDEX IF NOT EXISTS idx_enrichment_values_word
  ON word_enrichment_values(word_id,field_name);
CREATE INDEX IF NOT EXISTS idx_enrichment_events_candidate
  ON word_enrichment_events(candidate_id,occurred_at);

CREATE TRIGGER IF NOT EXISTS validate_review_event_identity_insert
BEFORE INSERT ON content_review_events
WHEN trim(NEW.reviewer_name)=''
BEGIN
  SELECT RAISE(ABORT, 'reviewer identity is required');
END;

CREATE TRIGGER IF NOT EXISTS validate_staging_human_review_update
BEFORE UPDATE OF review_status ON content_staging_records
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT CASE WHEN NEW.validation_status<>'valid'
    OR NOT EXISTS(
      SELECT 1 FROM content_review_events e
      WHERE e.staging_record_id=NEW.id AND e.decision='approve'
        AND trim(e.reviewer_name)<>''
    )
    THEN RAISE(ABORT, 'human review evidence is required') END;
END;

CREATE TRIGGER IF NOT EXISTS validate_staging_human_review_insert
BEFORE INSERT ON content_staging_records
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT RAISE(ABORT, 'human review evidence is required');
END;

CREATE TRIGGER IF NOT EXISTS validate_draft_human_review_update
BEFORE UPDATE OF review_status ON question_bank_drafts
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT CASE WHEN trim(NEW.explanation_vi)=''
    OR trim(NEW.answer_key_json) IN ('','[]','{}','null')
    OR NOT EXISTS(
      SELECT 1 FROM content_review_events e
      WHERE e.staging_record_id=NEW.staging_record_id AND e.decision='approve'
        AND trim(e.reviewer_name)<>''
    )
    THEN RAISE(ABORT, 'complete human review evidence is required') END;
END;

CREATE TRIGGER IF NOT EXISTS validate_draft_human_review_insert
BEFORE INSERT ON question_bank_drafts
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT CASE WHEN trim(NEW.explanation_vi)=''
    OR trim(NEW.answer_key_json) IN ('','[]','{}','null')
    OR NOT EXISTS(
      SELECT 1 FROM content_review_events e
      WHERE e.staging_record_id=NEW.staging_record_id AND e.decision='approve'
        AND trim(e.reviewer_name)<>''
    )
    THEN RAISE(ABORT, 'complete human review evidence is required') END;
END;

CREATE TRIGGER IF NOT EXISTS validate_question_source_on_publish_insert
BEFORE INSERT ON question_bank_drafts
WHEN NEW.published=1
BEGIN
  SELECT CASE WHEN NOT EXISTS(
    SELECT 1 FROM content_sources s
    WHERE s.source_key=NEW.source_key
      AND s.audit_status IN ('approved','conditional')
      AND s.commercial_use IN ('allowed','conditional')
      AND trim(s.license_name)<>'' AND trim(s.evidence_url)<>''
  ) THEN RAISE(ABORT, 'source license is not publishable') END;
END;

CREATE TRIGGER IF NOT EXISTS validate_question_source_on_publish
BEFORE UPDATE OF published ON question_bank_drafts
WHEN NEW.published=1
BEGIN
  SELECT CASE WHEN NOT EXISTS(
    SELECT 1 FROM content_sources s
    WHERE s.source_key=NEW.source_key
      AND s.audit_status IN ('approved','conditional')
      AND s.commercial_use IN ('allowed','conditional')
      AND trim(s.license_name)<>'' AND trim(s.evidence_url)<>''
  ) THEN RAISE(ABORT, 'source license is not publishable') END;
END;
