CREATE TRIGGER IF NOT EXISTS validate_staging_human_review_insert
BEFORE INSERT ON content_staging_records
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT RAISE(ABORT, 'human review evidence is required');
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
