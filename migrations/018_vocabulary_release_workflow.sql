CREATE TABLE IF NOT EXISTS content_reviewer_roles(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('reviewer','publisher','admin')),
  granted_by TEXT NOT NULL,
  granted_at TEXT NOT NULL,
  PRIMARY KEY(user_id,role)
);

CREATE TABLE IF NOT EXISTS vocabulary_quality_policies(
  version TEXT PRIMARY KEY,
  core_requirements_json TEXT NOT NULL,
  enriched_fields_json TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO vocabulary_quality_policies VALUES(
  'core-v1',
  '["headword","part_of_speech","meaning_vi","cefr","topic","field_provenance","publishable_license","automated_qa","human_review"]',
  '["ipa","example_en","example_vi","definition_en","synonym","antonym","word_form","collocation","multiple_senses"]',
  1,CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vocabulary_candidates(
  id INTEGER PRIMARY KEY,
  stable_key TEXT NOT NULL UNIQUE,
  normalized_word TEXT NOT NULL,
  word TEXT NOT NULL,
  pos TEXT NOT NULL,
  meaning_vi TEXT NOT NULL DEFAULT '',
  ipa TEXT NOT NULL DEFAULT '',
  cefr_level TEXT NOT NULL CHECK(cefr_level IN ('A0','A1','A2','B1','B2','unverified')),
  definition_en TEXT NOT NULL DEFAULT '',
  example_en TEXT NOT NULL DEFAULT '',
  example_vi TEXT NOT NULL DEFAULT '',
  source_key TEXT NOT NULL REFERENCES content_sources(source_key),
  source_record_id TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  license_status TEXT NOT NULL CHECK(license_status IN ('pass','conditional','blocked')),
  qa_status TEXT NOT NULL CHECK(qa_status IN ('pass','warn','fail')),
  core_status TEXT NOT NULL CHECK(core_status IN ('review_ready','needs_data','license_blocked','duplicate','invalid')),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','needs_revision','human_reviewed','rejected')),
  policy_version TEXT NOT NULL REFERENCES vocabulary_quality_policies(version),
  content_revision INTEGER NOT NULL DEFAULT 1 CHECK(content_revision>0),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  reviewed_at TEXT,
  reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  published_word_id INTEGER REFERENCES library_words(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS vocabulary_candidate_topics(
  candidate_id INTEGER NOT NULL REFERENCES vocabulary_candidates(id) ON DELETE CASCADE,
  topic_id INTEGER NOT NULL REFERENCES vocabulary_topics(id) ON DELETE CASCADE,
  confidence INTEGER NOT NULL CHECK(confidence BETWEEN 0 AND 100),
  source_key TEXT NOT NULL,
  rationale TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','human_reviewed','rejected')),
  PRIMARY KEY(candidate_id,topic_id)
);

CREATE TABLE IF NOT EXISTS vocabulary_candidate_events(
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES vocabulary_candidates(id) ON DELETE CASCADE,
  actor_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  actor_name TEXT NOT NULL,
  action TEXT NOT NULL CHECK(action IN ('approve','reject','needs_revision','edit','publish','rollback')),
  reason TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  content_revision INTEGER NOT NULL,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocabulary_publish_batches(
  id INTEGER PRIMARY KEY,
  publisher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  publisher_name TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('running','published','rolled_back','failed')),
  created_at TEXT NOT NULL,
  finished_at TEXT,
  report_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS vocabulary_publish_items(
  batch_id INTEGER NOT NULL REFERENCES vocabulary_publish_batches(id) ON DELETE RESTRICT,
  candidate_id INTEGER NOT NULL UNIQUE REFERENCES vocabulary_candidates(id) ON DELETE RESTRICT,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE RESTRICT,
  content_revision INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(batch_id,candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_vocabulary_candidates_queue
  ON vocabulary_candidates(review_status,core_status,cefr_level,source_key,id);
CREATE INDEX IF NOT EXISTS idx_vocabulary_candidate_topics_topic
  ON vocabulary_candidate_topics(topic_id,review_status,candidate_id);
CREATE INDEX IF NOT EXISTS idx_vocabulary_candidate_events_candidate
  ON vocabulary_candidate_events(candidate_id,occurred_at,id);

CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_candidate_events_update
BEFORE UPDATE ON vocabulary_candidate_events BEGIN
  SELECT RAISE(ABORT,'vocabulary candidate audit log is immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_vocabulary_candidate_events_delete
BEFORE DELETE ON vocabulary_candidate_events BEGIN
  SELECT RAISE(ABORT,'vocabulary candidate audit log is immutable');
END;

CREATE TRIGGER IF NOT EXISTS invalidate_vocabulary_candidate_approval
AFTER UPDATE OF word,pos,meaning_vi,ipa,cefr_level,definition_en,example_en,example_vi,
  provenance_json,license_status,qa_status,core_status ON vocabulary_candidates
WHEN OLD.review_status='human_reviewed'
BEGIN
  UPDATE vocabulary_candidates SET review_status='needs_revision',reviewed_at=NULL,
    reviewed_by_user_id=NULL,content_revision=OLD.content_revision+1,
    updated_at=CURRENT_TIMESTAMP WHERE id=NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS validate_vocabulary_candidate_human_review
BEFORE UPDATE OF review_status ON vocabulary_candidates
WHEN NEW.review_status='human_reviewed'
BEGIN
  SELECT CASE WHEN NEW.core_status<>'review_ready' OR NEW.qa_status<>'pass'
    OR NEW.license_status<>'pass' OR trim(NEW.meaning_vi)='' OR trim(NEW.pos)=''
    OR NEW.cefr_level='unverified'
    OR NOT EXISTS(SELECT 1 FROM vocabulary_candidate_topics t
      WHERE t.candidate_id=NEW.id AND t.review_status='human_reviewed')
    OR NOT EXISTS(SELECT 1 FROM vocabulary_candidate_events e
      WHERE e.candidate_id=NEW.id AND e.action='approve'
        AND e.content_revision=NEW.content_revision AND trim(e.actor_name)<>'')
    THEN RAISE(ABORT,'Core validation and current human review evidence are required') END;
END;

CREATE TRIGGER IF NOT EXISTS validate_vocabulary_topic_publish_insert
BEFORE INSERT ON vocabulary_topic_words
WHEN NEW.published=1 AND NEW.review_status<>'existing_published'
BEGIN
  SELECT CASE WHEN NEW.review_status<>'human_reviewed'
    OR NOT EXISTS(SELECT 1 FROM vocabulary_topic_reviews r WHERE r.word_id=NEW.word_id
      AND r.topic_id=NEW.topic_id AND r.sense_key=NEW.sense_key
      AND r.decision='approve' AND trim(r.reviewer_name)<>'')
    THEN RAISE(ABORT,'Human review evidence is required for a published topic mapping') END;
END;

-- Core-v1 deliberately supersedes the original all-enrichment publication gate.
-- IPA and bilingual examples remain desirable but are no longer mandatory Core fields.
DROP TRIGGER IF EXISTS validate_library_word_insert;
DROP TRIGGER IF EXISTS validate_library_word_update;
CREATE TRIGGER validate_library_word_insert BEFORE INSERT ON library_words WHEN NEW.reviewed=1 BEGIN
  SELECT CASE WHEN trim(NEW.normalized_word)='' OR trim(NEW.meaning)='' OR trim(NEW.pos)=''
    OR NEW.stage NOT IN ('A0','A1','A2','B1','B2') OR trim(NEW.topic)='' OR trim(NEW.source)=''
    THEN RAISE(ABORT,'published Core vocabulary is incomplete under core-v1') END;
END;
CREATE TRIGGER validate_library_word_update BEFORE UPDATE ON library_words WHEN NEW.reviewed=1 BEGIN
  SELECT CASE WHEN trim(NEW.normalized_word)='' OR trim(NEW.meaning)='' OR trim(NEW.pos)=''
    OR NEW.stage NOT IN ('A0','A1','A2','B1','B2') OR trim(NEW.topic)='' OR trim(NEW.source)=''
    THEN RAISE(ABORT,'published Core vocabulary is incomplete under core-v1') END;
END;
