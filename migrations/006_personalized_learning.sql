CREATE TABLE IF NOT EXISTS learner_profiles(
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  recommended_level TEXT CHECK(recommended_level IN ('A0','A1','A2','B1','B2')),
  current_level TEXT NOT NULL DEFAULT 'A0' CHECK(current_level IN ('A0','A1','A2','B1','B2')),
  daily_goal_minutes INTEGER NOT NULL DEFAULT 15 CHECK(daily_goal_minutes BETWEEN 5 AND 180),
  timezone TEXT NOT NULL DEFAULT 'Asia/Bangkok',
  placement_completed_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS placement_attempts(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'started' CHECK(status IN ('started','completed')),
  questions_json TEXT NOT NULL CHECK(json_valid(questions_json)),
  answers_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(answers_json)),
  score_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(score_json)),
  recommended_level TEXT CHECK(recommended_level IN ('A0','A1','A2','B1','B2')),
  started_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS learning_events(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK(event_type IN (
    'vocabulary_learning','vocabulary_review','grammar_answer',
    'listening_answer','exercise_answer','speaking_turn','speaking_live'
  )),
  skill TEXT NOT NULL,
  ref_type TEXT NOT NULL DEFAULT '',
  ref_id INTEGER,
  correct INTEGER CHECK(correct IS NULL OR correct IN (0,1)),
  duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds>=0),
  evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_plans(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_date TEXT NOT NULL,
  level TEXT NOT NULL CHECK(level IN ('A0','A1','A2','B1','B2')),
  items_json TEXT NOT NULL CHECK(json_valid(items_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id,plan_date)
);

CREATE INDEX IF NOT EXISTS idx_placement_attempts_user ON placement_attempts(user_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_learning_events_user_date ON learning_events(user_id,occurred_at);
CREATE INDEX IF NOT EXISTS idx_learning_events_user_skill ON learning_events(user_id,skill,event_type);
