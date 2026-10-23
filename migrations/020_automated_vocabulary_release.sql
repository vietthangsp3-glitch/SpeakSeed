CREATE TABLE IF NOT EXISTS vocabulary_automated_releases(
  id INTEGER PRIMARY KEY,
  word_id INTEGER NOT NULL UNIQUE REFERENCES library_words(id) ON DELETE RESTRICT,
  source_candidate_ids_json TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_snapshot_sha256 TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  checks_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  released_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vocabulary_automated_releases_rule
  ON vocabulary_automated_releases(rule_version,released_at,word_id);

-- One learnable row per normalized headword. Different POS/senses are merged by
-- the release tool instead of producing duplicate flashcards.
CREATE UNIQUE INDEX IF NOT EXISTS uq_library_words_published_normalized
  ON library_words(normalized_word) WHERE reviewed=1;

INSERT OR IGNORE INTO vocabulary_quality_policies(
  version,core_requirements_json,enriched_fields_json,active,created_at
) VALUES(
  'auto-core-v1',
  '["headword","part_of_speech","meaning_vi","cefr","field_provenance","publishable_license","automated_qa","deduplication"]',
  '["topic","ipa","example_en","example_vi","definition_en","synonym","antonym","word_form","collocation","multiple_senses"]',
  1,CURRENT_TIMESTAMP
);

-- Existing human-review publication remains valid. Automated mappings are
-- allowed only after a matching immutable release-evidence row exists.
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
        ))
    ) THEN RAISE(ABORT,'Human review or automated release evidence is required for a new topic mapping') END;
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
        ))
    ) THEN RAISE(ABORT,'Human review or automated release evidence is required for a published topic mapping') END;
END;

CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_automated_releases_update
BEFORE UPDATE ON vocabulary_automated_releases
BEGIN SELECT RAISE(ABORT,'automated release evidence is immutable'); END;

CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_automated_releases_delete
BEFORE DELETE ON vocabulary_automated_releases
BEGIN SELECT RAISE(ABORT,'automated release evidence is immutable'); END;
