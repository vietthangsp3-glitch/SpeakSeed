ALTER TABLE question_bank_drafts ADD COLUMN IF NOT EXISTS placement_eligible BIGINT NOT NULL DEFAULT 0 CHECK(placement_eligible IN (0,1));
ALTER TABLE question_bank_drafts ADD COLUMN IF NOT EXISTS lesson_contexts_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE question_bank_drafts ADD COLUMN IF NOT EXISTS published_at TEXT;
ALTER TABLE question_bank_drafts ADD COLUMN IF NOT EXISTS published_by TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS question_qa_results(question_id BIGINT PRIMARY KEY REFERENCES question_bank_drafts(id) ON DELETE CASCADE,tool_version TEXT NOT NULL,overall_status TEXT NOT NULL CHECK(overall_status IN ('pass','warn','fail')),issues_json TEXT NOT NULL DEFAULT '[]',checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS question_draft_revisions(id BIGSERIAL PRIMARY KEY,question_id BIGINT NOT NULL REFERENCES question_bank_drafts(id) ON DELETE CASCADE,editor_name TEXT NOT NULL,reason TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,edited_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS question_publication_batches(id BIGSERIAL PRIMARY KEY,publisher_name TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('publishing','published','failed','rolled_back')),created_at TEXT NOT NULL,finished_at TEXT,item_count BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS question_publication_items(batch_id BIGINT NOT NULL REFERENCES question_publication_batches(id) ON DELETE RESTRICT,question_id BIGINT NOT NULL REFERENCES question_bank_drafts(id) ON DELETE RESTRICT,published_hash TEXT NOT NULL,PRIMARY KEY(batch_id,question_id));
CREATE TABLE IF NOT EXISTS question_bank_attempts(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,question_id BIGINT NOT NULL REFERENCES question_bank_drafts(id) ON DELETE RESTRICT,learning_context TEXT NOT NULL CHECK(learning_context IN ('placement','vocabulary','grammar','listening','reading','daily_review')),answer TEXT NOT NULL,correct BIGINT NOT NULL CHECK(correct IN (0,1)),submitted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS question_bank_links(question_id BIGINT NOT NULL REFERENCES question_bank_drafts(id) ON DELETE CASCADE,learning_context TEXT NOT NULL CHECK(learning_context IN ('placement','vocabulary','grammar','listening','reading','daily_review')),ref_type TEXT NOT NULL DEFAULT '',ref_id BIGINT NOT NULL DEFAULT 0,PRIMARY KEY(question_id,learning_context,ref_type,ref_id));
CREATE INDEX IF NOT EXISTS idx_question_qa_status ON question_qa_results(overall_status,question_id);
CREATE INDEX IF NOT EXISTS idx_question_revisions_question ON question_draft_revisions(question_id,edited_at);
CREATE INDEX IF NOT EXISTS idx_question_attempts_user ON question_bank_attempts(user_id,learning_context,submitted_at);
CREATE INDEX IF NOT EXISTS idx_question_links_context ON question_bank_links(learning_context,ref_type,ref_id);
CREATE OR REPLACE FUNCTION immutable_content_review_events_fn() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'review audit log is immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_content_review_events_update ON content_review_events;
CREATE TRIGGER immutable_content_review_events_update BEFORE UPDATE ON content_review_events FOR EACH ROW EXECUTE FUNCTION immutable_content_review_events_fn();
DROP TRIGGER IF EXISTS immutable_content_review_events_delete ON content_review_events;
CREATE TRIGGER immutable_content_review_events_delete BEFORE DELETE ON content_review_events FOR EACH ROW EXECUTE FUNCTION immutable_content_review_events_fn();
CREATE OR REPLACE FUNCTION validate_fresh_draft_review_evidence_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.review_status='human_reviewed' AND NOT EXISTS(SELECT 1 FROM content_review_events e WHERE e.staging_record_id=NEW.staging_record_id AND e.decision='approve' AND btrim(e.reviewer_name)<>'' AND e.reviewed_at>=NEW.updated_at) THEN RAISE EXCEPTION 'fresh human review evidence is required after editing'; END IF; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS validate_fresh_draft_review_evidence ON question_bank_drafts;
CREATE TRIGGER validate_fresh_draft_review_evidence BEFORE UPDATE OF review_status ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_fresh_draft_review_evidence_fn();
CREATE OR REPLACE FUNCTION validate_question_publish_phase3_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.published=1 AND OLD.published=0 AND (NEW.review_status<>'human_reviewed'
   OR NOT EXISTS(SELECT 1 FROM question_qa_results q WHERE q.question_id=NEW.id AND q.overall_status='pass')
   OR NOT EXISTS(SELECT 1 FROM question_publication_items i JOIN question_publication_batches b ON b.id=i.batch_id WHERE i.question_id=NEW.id AND b.status='publishing' AND btrim(b.publisher_name)<>''))
 THEN RAISE EXCEPTION 'Phase 3 review, QA and publication evidence are required'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_question_publish_phase3 ON question_bank_drafts;
CREATE TRIGGER validate_question_publish_phase3 BEFORE UPDATE OF published ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_question_publish_phase3_fn();
CREATE OR REPLACE FUNCTION freeze_published_question_content_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF OLD.published=1 THEN RAISE EXCEPTION 'published question content is immutable'; END IF; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS freeze_published_question_content ON question_bank_drafts;
CREATE TRIGGER freeze_published_question_content BEFORE UPDATE OF prompt,answer_key_json,accepted_answers_json,explanation_vi,payload_json,cefr_level,question_type ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION freeze_published_question_content_fn();
