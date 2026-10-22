CREATE TABLE IF NOT EXISTS skill_lessons(
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  skill TEXT NOT NULL CHECK(skill IN ('listening','reading','speaking','writing')),
  level TEXT NOT NULL CHECK(level IN ('A0','A1','A2','B1','B2')),
  sequence INTEGER NOT NULL CHECK(sequence>0),
  title TEXT NOT NULL,
  instructions_vi TEXT NOT NULL,
  content_en TEXT NOT NULL DEFAULT '',
  transcript_en TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json)),
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK(review_status IN ('automated_checked','human_reviewed')),
  published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
  updated_at TEXT NOT NULL,
  UNIQUE(skill,level,sequence)
);

CREATE TABLE IF NOT EXISTS skill_questions(
  id INTEGER PRIMARY KEY,
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('multiple_choice','fill_blank','dictation','reading_comprehension')),
  sequence INTEGER NOT NULL CHECK(sequence>0),
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(options_json)),
  answers_json TEXT NOT NULL CHECK(json_valid(answers_json)),
  explanation_vi TEXT NOT NULL,
  UNIQUE(lesson_id,sequence)
);

CREATE TABLE IF NOT EXISTS skill_lesson_words(
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE CASCADE,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE RESTRICT,
  PRIMARY KEY(lesson_id,word_id)
);

CREATE TABLE IF NOT EXISTS skill_question_attempts(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_id INTEGER NOT NULL REFERENCES skill_questions(id) ON DELETE CASCADE,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
  correct INTEGER NOT NULL DEFAULT 0 CHECK(correct>=0),
  wrong INTEGER NOT NULL DEFAULT 0 CHECK(wrong>=0),
  completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
  last_answer TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id,question_id)
);

CREATE TABLE IF NOT EXISTS skill_progress(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE CASCADE,
  attempted INTEGER NOT NULL DEFAULT 0 CHECK(attempted>=0),
  correct INTEGER NOT NULL DEFAULT 0 CHECK(correct>=0),
  completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id,lesson_id)
);

CREATE TABLE IF NOT EXISTS reading_saved_words(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE CASCADE,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE RESTRICT,
  saved_at TEXT NOT NULL,
  PRIMARY KEY(user_id,lesson_id,word_id)
);

CREATE TABLE IF NOT EXISTS speaking_sessions(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE RESTRICT,
  mode TEXT NOT NULL CHECK(mode IN ('turn','live')),
  status TEXT NOT NULL DEFAULT 'started' CHECK(status IN ('started','evaluated')),
  turns INTEGER NOT NULL DEFAULT 0 CHECK(turns>=0),
  transcript_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(transcript_json)),
  feedback_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(feedback_json)),
  scores_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(scores_json)),
  audio_evidence INTEGER NOT NULL DEFAULT 0 CHECK(audio_evidence IN (0,1)),
  started_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS writing_drafts(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id INTEGER NOT NULL REFERENCES skill_lessons(id) ON DELETE RESTRICT,
  content TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted')),
  feedback_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(feedback_json)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  submitted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_skill_lessons_catalog ON skill_lessons(skill,level,sequence);
CREATE INDEX IF NOT EXISTS idx_skill_questions_lesson ON skill_questions(lesson_id,sequence);
CREATE INDEX IF NOT EXISTS idx_skill_attempts_user ON skill_question_attempts(user_id,updated_at);
CREATE INDEX IF NOT EXISTS idx_skill_progress_user ON skill_progress(user_id,lesson_id);
CREATE INDEX IF NOT EXISTS idx_speaking_sessions_user ON speaking_sessions(user_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_writing_drafts_user ON writing_drafts(user_id,updated_at DESC);

-- SQLite cannot extend a CHECK constraint in place. Rebuild this append-only table
-- transactionally and copy every existing event before replacing it.
CREATE TABLE learning_events_v4(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK(event_type IN (
    'vocabulary_learning','vocabulary_review','grammar_answer','listening_answer',
    'exercise_answer','speaking_turn','speaking_live','skill_listening_answer',
    'reading_answer','reading_word_saved','speaking_evaluation','writing_submission'
  )),
  skill TEXT NOT NULL,
  ref_type TEXT NOT NULL DEFAULT '',
  ref_id INTEGER,
  correct INTEGER CHECK(correct IS NULL OR correct IN (0,1)),
  duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds>=0),
  evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
  occurred_at TEXT NOT NULL
);
INSERT INTO learning_events_v4 SELECT * FROM learning_events;
DROP TABLE learning_events;
ALTER TABLE learning_events_v4 RENAME TO learning_events;
CREATE INDEX idx_learning_events_user_date ON learning_events(user_id,occurred_at);
CREATE INDEX idx_learning_events_user_skill ON learning_events(user_id,skill,event_type);
