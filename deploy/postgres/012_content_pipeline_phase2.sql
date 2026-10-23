CREATE TABLE IF NOT EXISTS content_import_rejections(
 id BIGSERIAL PRIMARY KEY,batch_id BIGINT NOT NULL REFERENCES content_import_batches(id) ON DELETE CASCADE,
 source_record_id TEXT NOT NULL,content_type TEXT NOT NULL,reason TEXT NOT NULL,payload_hash TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
 UNIQUE(batch_id,source_record_id,content_type,reason));
CREATE TABLE IF NOT EXISTS word_enrichment_candidates(
 id BIGSERIAL PRIMARY KEY,word_id BIGINT NOT NULL REFERENCES library_words(id) ON DELETE CASCADE,
 staging_record_id BIGINT NOT NULL REFERENCES content_staging_records(id) ON DELETE CASCADE,field_name TEXT NOT NULL,
 value_json TEXT NOT NULL,normalized_value TEXT NOT NULL,source_key TEXT NOT NULL REFERENCES content_sources(source_key),source_record_id TEXT NOT NULL,
 confidence BIGINT NOT NULL CHECK(confidence BETWEEN 0 AND 100),quality_status TEXT NOT NULL CHECK(quality_status IN ('unverified','automated_checked','needs_review')),
 review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','human_reviewed','rejected')),applied BIGINT NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(word_id,field_name,normalized_value,source_key));
CREATE TABLE IF NOT EXISTS word_enrichment_values(
 id BIGSERIAL PRIMARY KEY,word_id BIGINT NOT NULL REFERENCES library_words(id) ON DELETE CASCADE,
 candidate_id BIGINT NOT NULL UNIQUE REFERENCES word_enrichment_candidates(id) ON DELETE RESTRICT,field_name TEXT NOT NULL,value_json TEXT NOT NULL,
 normalized_value TEXT NOT NULL,source_key TEXT NOT NULL REFERENCES content_sources(source_key),source_record_id TEXT NOT NULL,
 quality_status TEXT NOT NULL,review_status TEXT NOT NULL,applied_at TEXT NOT NULL,UNIQUE(word_id,field_name,normalized_value,source_key));
CREATE TABLE IF NOT EXISTS word_enrichment_events(
 id BIGSERIAL PRIMARY KEY,candidate_id BIGINT NOT NULL REFERENCES word_enrichment_candidates(id) ON DELETE CASCADE,
 reviewer_name TEXT NOT NULL DEFAULT '',action TEXT NOT NULL CHECK(action IN ('apply_automated','approve','reject','supersede')),reason TEXT NOT NULL DEFAULT '',occurred_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_import_rejections_batch ON content_import_rejections(batch_id,reason);
CREATE INDEX IF NOT EXISTS idx_enrichment_candidates_word ON word_enrichment_candidates(word_id,field_name,review_status,applied);
CREATE INDEX IF NOT EXISTS idx_enrichment_values_word ON word_enrichment_values(word_id,field_name);
CREATE INDEX IF NOT EXISTS idx_enrichment_events_candidate ON word_enrichment_events(candidate_id,occurred_at);

CREATE OR REPLACE FUNCTION validate_speakseed_content_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='content_review_events' AND btrim(NEW.reviewer_name)='' THEN RAISE EXCEPTION 'reviewer identity is required'; END IF;
 IF TG_TABLE_NAME='content_staging_records' AND NEW.review_status='human_reviewed' AND
   (NEW.validation_status<>'valid' OR NOT EXISTS(SELECT 1 FROM content_review_events e WHERE e.staging_record_id=NEW.id AND e.decision='approve' AND btrim(e.reviewer_name)<>''))
 THEN RAISE EXCEPTION 'human review evidence is required'; END IF;
 IF TG_TABLE_NAME='question_bank_drafts' AND NEW.review_status='human_reviewed' AND
   (btrim(NEW.explanation_vi)='' OR btrim(NEW.answer_key_json) IN ('','[]','{}','null') OR NOT EXISTS(SELECT 1 FROM content_review_events e WHERE e.staging_record_id=NEW.staging_record_id AND e.decision='approve' AND btrim(e.reviewer_name)<>''))
 THEN RAISE EXCEPTION 'complete human review evidence is required'; END IF;
 IF TG_TABLE_NAME='question_bank_drafts' AND NEW.published=1 AND
   NOT EXISTS(SELECT 1 FROM content_sources s WHERE s.source_key=NEW.source_key AND s.audit_status IN ('approved','conditional') AND s.commercial_use IN ('allowed','conditional') AND btrim(s.license_name)<>'' AND btrim(s.evidence_url)<>'')
 THEN RAISE EXCEPTION 'source license is not publishable'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_review_event_identity_insert ON content_review_events;
CREATE TRIGGER validate_review_event_identity_insert BEFORE INSERT ON content_review_events FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_staging_human_review_update ON content_staging_records;
CREATE TRIGGER validate_staging_human_review_update BEFORE UPDATE OF review_status ON content_staging_records FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_staging_human_review_insert ON content_staging_records;
CREATE TRIGGER validate_staging_human_review_insert BEFORE INSERT ON content_staging_records FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_draft_human_review_update ON question_bank_drafts;
CREATE TRIGGER validate_draft_human_review_update BEFORE UPDATE OF review_status ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_draft_human_review_insert ON question_bank_drafts;
CREATE TRIGGER validate_draft_human_review_insert BEFORE INSERT ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_question_source_on_publish_insert ON question_bank_drafts;
CREATE TRIGGER validate_question_source_on_publish_insert BEFORE INSERT ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_question_source_on_publish_update ON question_bank_drafts;
CREATE TRIGGER validate_question_source_on_publish_update BEFORE UPDATE OF published ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
