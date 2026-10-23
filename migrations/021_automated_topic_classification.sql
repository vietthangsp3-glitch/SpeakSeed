CREATE TABLE IF NOT EXISTS vocabulary_automated_topic_releases(
  id INTEGER PRIMARY KEY,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE RESTRICT,
  topic_id INTEGER NOT NULL REFERENCES vocabulary_topics(id) ON DELETE RESTRICT,
  rule_version TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  released_at TEXT NOT NULL,
  UNIQUE(word_id,topic_id,rule_version)
);

CREATE INDEX IF NOT EXISTS idx_vocabulary_auto_topic_rule
  ON vocabulary_automated_topic_releases(rule_version,topic_id,word_id);

DROP TRIGGER IF EXISTS validate_vocabulary_topic_publish;
CREATE TRIGGER validate_vocabulary_topic_publish
BEFORE UPDATE OF published ON vocabulary_topic_words
WHEN NEW.published=1 AND OLD.published=0
BEGIN
  SELECT CASE WHEN NOT EXISTS(
      SELECT 1 FROM library_words w WHERE w.id=NEW.word_id AND w.reviewed=1
    ) OR NOT (
      (NEW.review_status='human_reviewed' AND EXISTS(
        SELECT 1 FROM vocabulary_topic_reviews r
        WHERE r.word_id=NEW.word_id AND r.topic_id=NEW.topic_id
          AND r.sense_key=NEW.sense_key AND r.decision='approve'
          AND trim(r.reviewer_name)<>''
      )) OR
      (NEW.review_status='pending' AND NEW.source_key='automated-release-v1'
        AND NEW.confidence>=70 AND EXISTS(
          SELECT 1 FROM vocabulary_automated_releases a
          WHERE a.word_id=NEW.word_id AND a.rule_version='auto-core-v1'
        )) OR
      (NEW.review_status='pending' AND NEW.source_key='automated-topic-v1'
        AND NEW.confidence>=85 AND EXISTS(
          SELECT 1 FROM vocabulary_automated_topic_releases a
          WHERE a.word_id=NEW.word_id AND a.topic_id=NEW.topic_id
            AND a.rule_version='topic-core-v1'
        ))
    ) THEN RAISE(ABORT,'Human review or immutable automated evidence is required for a topic mapping') END;
END;

DROP TRIGGER IF EXISTS validate_vocabulary_topic_publish_insert;
CREATE TRIGGER validate_vocabulary_topic_publish_insert
BEFORE INSERT ON vocabulary_topic_words
WHEN NEW.published=1 AND NEW.review_status<>'existing_published'
BEGIN
  SELECT CASE WHEN NOT (
      (NEW.review_status='human_reviewed' AND EXISTS(
        SELECT 1 FROM vocabulary_topic_reviews r
        WHERE r.word_id=NEW.word_id AND r.topic_id=NEW.topic_id
          AND r.sense_key=NEW.sense_key AND r.decision='approve'
          AND trim(r.reviewer_name)<>''
      )) OR
      (NEW.review_status='pending' AND NEW.source_key='automated-release-v1'
        AND NEW.confidence>=70 AND EXISTS(
          SELECT 1 FROM vocabulary_automated_releases a
          WHERE a.word_id=NEW.word_id AND a.rule_version='auto-core-v1'
        )) OR
      (NEW.review_status='pending' AND NEW.source_key='automated-topic-v1'
        AND NEW.confidence>=85 AND EXISTS(
          SELECT 1 FROM vocabulary_automated_topic_releases a
          WHERE a.word_id=NEW.word_id AND a.topic_id=NEW.topic_id
            AND a.rule_version='topic-core-v1'
        ))
    ) THEN RAISE(ABORT,'Human review or immutable automated evidence is required for a published topic mapping') END;
END;

CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_auto_topic_update
BEFORE UPDATE ON vocabulary_automated_topic_releases
BEGIN SELECT RAISE(ABORT,'automated topic evidence is immutable'); END;

CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_auto_topic_delete
BEFORE DELETE ON vocabulary_automated_topic_releases
BEGIN SELECT RAISE(ABORT,'automated topic evidence is immutable'); END;
