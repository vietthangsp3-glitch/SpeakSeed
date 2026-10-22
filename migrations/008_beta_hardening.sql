ALTER TABLE sessions ADD COLUMN csrf_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT '';
ALTER TABLE sessions ADD COLUMN ip_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE sessions ADD COLUMN user_agent_hash TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS auth_rate_limits(
  subject_hash TEXT NOT NULL,
  action TEXT NOT NULL,
  window_started_at TEXT NOT NULL,
  hits INTEGER NOT NULL DEFAULT 0 CHECK(hits>=0),
  blocked_until TEXT,
  PRIMARY KEY(subject_hash,action)
);

CREATE TABLE IF NOT EXISTS ai_usage(
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  ip_hash TEXT NOT NULL,
  feature TEXT NOT NULL CHECK(feature IN (
    'speaking_turn','speaking_live','speaking_evaluation','writing_feedback',
    'tts','tutor','pronunciation'
  )),
  status TEXT NOT NULL CHECK(status IN ('started','succeeded','failed','quota_rejected')),
  model TEXT NOT NULL DEFAULT '',
  input_units INTEGER NOT NULL DEFAULT 0 CHECK(input_units>=0),
  output_units INTEGER NOT NULL DEFAULT 0 CHECK(output_units>=0),
  estimated_cost_usd REAL NOT NULL DEFAULT 0 CHECK(estimated_cost_usd>=0),
  latency_ms INTEGER NOT NULL DEFAULT 0 CHECK(latency_ms>=0),
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires);
CREATE INDEX IF NOT EXISTS idx_auth_limits_window ON auth_rate_limits(action,window_started_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_feature_time ON ai_usage(user_id,feature,created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_ip_feature_time ON ai_usage(ip_hash,feature,created_at);
CREATE INDEX IF NOT EXISTS idx_library_words_stage_reviewed ON library_words(stage,reviewed,id);
CREATE INDEX IF NOT EXISTS idx_grammar_lessons_level_published ON grammar_lessons(level,published,unit_id,sequence);
CREATE INDEX IF NOT EXISTS idx_grammar_exercises_lesson_published ON grammar_exercises(lesson_id,published,sequence);
CREATE INDEX IF NOT EXISTS idx_skill_lessons_path ON skill_lessons(skill,level,published,sequence);
CREATE INDEX IF NOT EXISTS idx_learning_events_type_time ON learning_events(user_id,event_type,occurred_at);
CREATE INDEX IF NOT EXISTS idx_writing_drafts_owner_status ON writing_drafts(user_id,status,updated_at);
