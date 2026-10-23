CREATE OR REPLACE FUNCTION validate_speakseed_content_review() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='content_review_events' AND btrim(NEW.reviewer_name)='' THEN RAISE EXCEPTION 'reviewer identity is required'; END IF;
 IF TG_TABLE_NAME='content_staging_records' AND NEW.review_status='human_reviewed' AND
   (TG_OP='INSERT' OR NEW.validation_status<>'valid' OR NOT EXISTS(SELECT 1 FROM content_review_events e WHERE e.staging_record_id=NEW.id AND e.decision='approve' AND btrim(e.reviewer_name)<>''))
 THEN RAISE EXCEPTION 'human review evidence is required'; END IF;
 IF TG_TABLE_NAME='question_bank_drafts' AND NEW.review_status='human_reviewed' AND
   (btrim(NEW.explanation_vi)='' OR btrim(NEW.answer_key_json) IN ('','[]','{}','null') OR NOT EXISTS(SELECT 1 FROM content_review_events e WHERE e.staging_record_id=NEW.staging_record_id AND e.decision='approve' AND btrim(e.reviewer_name)<>''))
 THEN RAISE EXCEPTION 'complete human review evidence is required'; END IF;
 IF TG_TABLE_NAME='question_bank_drafts' AND NEW.published=1 AND
   NOT EXISTS(SELECT 1 FROM content_sources s WHERE s.source_key=NEW.source_key AND s.audit_status IN ('approved','conditional') AND s.commercial_use IN ('allowed','conditional') AND btrim(s.license_name)<>'' AND btrim(s.evidence_url)<>'')
 THEN RAISE EXCEPTION 'source license is not publishable'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_staging_human_review_insert ON content_staging_records;
CREATE TRIGGER validate_staging_human_review_insert BEFORE INSERT ON content_staging_records FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_draft_human_review_insert ON question_bank_drafts;
CREATE TRIGGER validate_draft_human_review_insert BEFORE INSERT ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_question_source_on_publish_insert ON question_bank_drafts;
CREATE TRIGGER validate_question_source_on_publish_insert BEFORE INSERT ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
DROP TRIGGER IF EXISTS validate_question_source_on_publish_update ON question_bank_drafts;
CREATE TRIGGER validate_question_source_on_publish_update BEFORE UPDATE OF published ON question_bank_drafts FOR EACH ROW EXECUTE FUNCTION validate_speakseed_content_review();
