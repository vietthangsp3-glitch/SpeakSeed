ALTER TABLE question_publication_batches ADD COLUMN license_conditions_confirmed INTEGER NOT NULL DEFAULT 0
  CHECK(license_conditions_confirmed IN (0,1));

DROP TRIGGER IF EXISTS validate_question_publish_phase3;
CREATE TRIGGER validate_question_publish_phase3
BEFORE UPDATE OF published ON question_bank_drafts
WHEN NEW.published=1 AND OLD.published=0
BEGIN
  SELECT CASE WHEN NEW.review_status<>'human_reviewed'
    OR NOT EXISTS(SELECT 1 FROM question_qa_results q WHERE q.question_id=NEW.id AND q.overall_status='pass')
    OR NOT EXISTS(
      SELECT 1 FROM question_publication_items i
      JOIN question_publication_batches b ON b.id=i.batch_id
      JOIN content_sources s ON s.source_key=NEW.source_key
      WHERE i.question_id=NEW.id AND b.status='publishing' AND trim(b.publisher_name)<>''
        AND s.audit_status IN ('approved','conditional') AND trim(s.evidence_url)<>''
        AND (s.audit_status='approved' OR b.license_conditions_confirmed=1)
    )
    THEN RAISE(ABORT, 'Phase 3 review, QA, license and publication evidence are required') END;
END;
