CREATE TABLE IF NOT EXISTS content_sources(
  source_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, owner_name TEXT NOT NULL,
  source_url TEXT NOT NULL, dataset_version TEXT NOT NULL, license_name TEXT NOT NULL,
  license_url TEXT NOT NULL, commercial_use TEXT NOT NULL CHECK(commercial_use IN ('allowed','conditional','prohibited','unverified')),
  attribution TEXT NOT NULL, obligations TEXT NOT NULL DEFAULT '', audit_status TEXT NOT NULL CHECK(audit_status IN ('approved','conditional','rejected')),
  evidence_url TEXT NOT NULL, audited_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS content_import_batches(
  id BIGSERIAL PRIMARY KEY, source_key TEXT NOT NULL REFERENCES content_sources(source_key), source_version TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, importer_version TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','staged','failed','rolled_back')),
  started_at TEXT NOT NULL, finished_at TEXT, checkpoint TEXT NOT NULL DEFAULT '', processed BIGINT NOT NULL DEFAULT 0,
  accepted BIGINT NOT NULL DEFAULT 0, rejected BIGINT NOT NULL DEFAULT 0, report_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(source_key,source_version,source_sha256,importer_version)
);
CREATE TABLE IF NOT EXISTS content_staging_records(
  id BIGSERIAL PRIMARY KEY, batch_id BIGINT NOT NULL REFERENCES content_import_batches(id) ON DELETE CASCADE,
  content_type TEXT NOT NULL CHECK(content_type IN ('vocabulary','grammar','sentence','question','audio')),
  source_record_id TEXT NOT NULL, stable_key TEXT NOT NULL, normalized_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
  validation_status TEXT NOT NULL CHECK(validation_status IN ('valid','rejected')), validation_errors_json TEXT NOT NULL DEFAULT '[]',
  quality_status TEXT NOT NULL CHECK(quality_status IN ('unverified','automated_checked','needs_review')),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','human_reviewed','rejected')), created_at TEXT NOT NULL,
  UNIQUE(batch_id,content_type,source_record_id), UNIQUE(batch_id,content_type,stable_key)
);
CREATE TABLE IF NOT EXISTS content_review_events(
  id BIGSERIAL PRIMARY KEY, staging_record_id BIGINT NOT NULL REFERENCES content_staging_records(id) ON DELETE CASCADE,
  reviewer_id BIGINT REFERENCES users(id) ON DELETE SET NULL, reviewer_name TEXT NOT NULL DEFAULT '',
  decision TEXT NOT NULL CHECK(decision IN ('approve','reject','request_changes')), notes TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS question_bank_drafts(
  id BIGSERIAL PRIMARY KEY, staging_record_id BIGINT NOT NULL UNIQUE REFERENCES content_staging_records(id) ON DELETE RESTRICT,
  stable_id TEXT NOT NULL UNIQUE, question_type TEXT NOT NULL CHECK(question_type IN ('multiple_choice','fill_blank','sentence_ordering','listening','reading','error_correction','translation')),
  cefr_level TEXT NOT NULL CHECK(cefr_level IN ('A0','A1','A2','B1','B2','unverified')), skill TEXT NOT NULL, topic TEXT NOT NULL,
  difficulty BIGINT NOT NULL CHECK(difficulty BETWEEN 1 AND 5), prompt TEXT NOT NULL, answer_key_json TEXT NOT NULL,
  accepted_answers_json TEXT NOT NULL DEFAULT '[]', explanation_vi TEXT NOT NULL, explanation_en TEXT NOT NULL DEFAULT '', context_text TEXT NOT NULL DEFAULT '',
  source_key TEXT NOT NULL REFERENCES content_sources(source_key), source_record_id TEXT NOT NULL, license_name TEXT NOT NULL,
  quality_status TEXT NOT NULL CHECK(quality_status IN ('unverified','automated_checked','needs_review')),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','human_reviewed','rejected')),
  published BIGINT NOT NULL DEFAULT 0 CHECK(published IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_batches_source_status ON content_import_batches(source_key,status,started_at);
CREATE INDEX IF NOT EXISTS idx_content_staging_review ON content_staging_records(content_type,review_status,validation_status,id);
CREATE INDEX IF NOT EXISTS idx_content_staging_hash ON content_staging_records(content_type,normalized_hash);
CREATE INDEX IF NOT EXISTS idx_content_reviews_record ON content_review_events(staging_record_id,reviewed_at);
CREATE INDEX IF NOT EXISTS idx_question_drafts_catalog ON question_bank_drafts(cefr_level,question_type,review_status,published);
