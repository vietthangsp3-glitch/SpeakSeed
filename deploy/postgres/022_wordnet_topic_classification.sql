CREATE TABLE IF NOT EXISTS vocabulary_topic_corrections(
  id BIGSERIAL PRIMARY KEY,
  word_id BIGINT NOT NULL REFERENCES library_words(id) ON DELETE RESTRICT,
  old_topic_id BIGINT NOT NULL REFERENCES vocabulary_topics(id) ON DELETE RESTRICT,
  new_topic_id BIGINT NOT NULL REFERENCES vocabulary_topics(id) ON DELETE RESTRICT,
  rule_version TEXT NOT NULL,
  rationale TEXT NOT NULL,
  corrected_at TEXT NOT NULL,
  UNIQUE(word_id,old_topic_id,new_topic_id,rule_version)
);
CREATE OR REPLACE FUNCTION reject_vocabulary_topic_correction_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'automated topic correction evidence is immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_vocabulary_topic_correction_update ON vocabulary_topic_corrections;
CREATE TRIGGER immutable_vocabulary_topic_correction_update BEFORE UPDATE ON vocabulary_topic_corrections
FOR EACH ROW EXECUTE FUNCTION reject_vocabulary_topic_correction_mutation();
DROP TRIGGER IF EXISTS immutable_vocabulary_topic_correction_delete ON vocabulary_topic_corrections;
CREATE TRIGGER immutable_vocabulary_topic_correction_delete BEFORE DELETE ON vocabulary_topic_corrections
FOR EACH ROW EXECUTE FUNCTION reject_vocabulary_topic_correction_mutation();

CREATE OR REPLACE FUNCTION validate_vocabulary_topic_publish_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.published=1 AND OLD.published=0 AND (
   NOT EXISTS(SELECT 1 FROM library_words w WHERE w.id=NEW.word_id AND w.reviewed=1)
   OR NOT (
     (NEW.review_status='human_reviewed' AND EXISTS(SELECT 1 FROM vocabulary_topic_reviews r
       WHERE r.word_id=NEW.word_id AND r.topic_id=NEW.topic_id AND r.sense_key=NEW.sense_key
         AND r.decision='approve' AND btrim(r.reviewer_name)<>''))
     OR (NEW.review_status='pending' AND NEW.source_key='automated-release-v1' AND NEW.confidence>=70
       AND EXISTS(SELECT 1 FROM vocabulary_automated_releases a
         WHERE a.word_id=NEW.word_id AND a.rule_version='auto-core-v1'))
     OR (NEW.review_status='pending' AND NEW.source_key='automated-topic-v1' AND NEW.confidence>=85
       AND EXISTS(SELECT 1 FROM vocabulary_automated_topic_releases a
         WHERE a.word_id=NEW.word_id AND a.topic_id=NEW.topic_id
           AND a.rule_version IN ('topic-core-v1','wordnet-domain-v1')))
   )) THEN RAISE EXCEPTION 'Human review or immutable automated evidence is required for a topic mapping'; END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION validate_vocabulary_topic_publish_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.published=1 AND NEW.review_status<>'existing_published' AND NOT (
   (NEW.review_status='human_reviewed' AND EXISTS(SELECT 1 FROM vocabulary_topic_reviews r
     WHERE r.word_id=NEW.word_id AND r.topic_id=NEW.topic_id AND r.sense_key=NEW.sense_key
       AND r.decision='approve' AND btrim(r.reviewer_name)<>''))
   OR (NEW.review_status='pending' AND NEW.source_key='automated-release-v1' AND NEW.confidence>=70
     AND EXISTS(SELECT 1 FROM vocabulary_automated_releases a
       WHERE a.word_id=NEW.word_id AND a.rule_version='auto-core-v1'))
   OR (NEW.review_status='pending' AND NEW.source_key='automated-topic-v1' AND NEW.confidence>=85
     AND EXISTS(SELECT 1 FROM vocabulary_automated_topic_releases a
       WHERE a.word_id=NEW.word_id AND a.topic_id=NEW.topic_id
         AND a.rule_version IN ('topic-core-v1','wordnet-domain-v1')))
 ) THEN RAISE EXCEPTION 'Human review or immutable automated evidence is required for a published topic mapping'; END IF;
 RETURN NEW;
END $$;
