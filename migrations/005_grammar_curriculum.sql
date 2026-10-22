CREATE TABLE IF NOT EXISTS grammar_units(
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  level TEXT NOT NULL CHECK(level IN ('A0','A1','A2','B1','B2')),
  sequence INTEGER NOT NULL,
  title TEXT NOT NULL,
  description_vi TEXT NOT NULL,
  published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
  UNIQUE(level, sequence)
);

CREATE TABLE IF NOT EXISTS grammar_lessons(
  id INTEGER PRIMARY KEY,
  unit_id INTEGER NOT NULL REFERENCES grammar_units(id) ON DELETE CASCADE,
  slug TEXT NOT NULL UNIQUE,
  level TEXT NOT NULL CHECK(level IN ('A0','A1','A2','B1','B2')),
  sequence INTEGER NOT NULL,
  title TEXT NOT NULL,
  topic TEXT NOT NULL,
  explanation_vi TEXT NOT NULL,
  formula TEXT NOT NULL,
  common_errors_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(common_errors_json)),
  source TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK(review_status IN ('automated_checked','human_reviewed')),
  published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
  updated_at TEXT NOT NULL,
  UNIQUE(unit_id, sequence)
);

CREATE TABLE IF NOT EXISTS grammar_examples(
  id INTEGER PRIMARY KEY,
  lesson_id INTEGER NOT NULL REFERENCES grammar_lessons(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  english TEXT NOT NULL,
  vietnamese TEXT NOT NULL,
  focus TEXT NOT NULL DEFAULT '',
  UNIQUE(lesson_id, sequence)
);

CREATE TABLE IF NOT EXISTS grammar_exercises(
  id INTEGER PRIMARY KEY,
  lesson_id INTEGER NOT NULL REFERENCES grammar_lessons(id) ON DELETE CASCADE,
  unit_id INTEGER NOT NULL REFERENCES grammar_units(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL UNIQUE,
  level TEXT NOT NULL CHECK(level IN ('A0','A1','A2','B1','B2')),
  kind TEXT NOT NULL CHECK(kind IN ('multiple_choice','fill_blank','sentence_ordering','error_correction','vi_to_en')),
  sequence INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(options_json)),
  answers_json TEXT NOT NULL CHECK(json_valid(answers_json)),
  explanation_vi TEXT NOT NULL,
  is_unit_test INTEGER NOT NULL DEFAULT 0 CHECK(is_unit_test IN (0,1)),
  source TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK(review_status IN ('automated_checked','human_reviewed')),
  published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
  updated_at TEXT NOT NULL,
  UNIQUE(lesson_id, sequence)
);

CREATE TABLE IF NOT EXISTS grammar_exercise_words(
  exercise_id INTEGER NOT NULL REFERENCES grammar_exercises(id) ON DELETE CASCADE,
  word_id INTEGER NOT NULL REFERENCES library_words(id) ON DELETE CASCADE,
  PRIMARY KEY(exercise_id, word_id)
);

CREATE TABLE IF NOT EXISTS grammar_attempts(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id INTEGER NOT NULL REFERENCES grammar_exercises(id) ON DELETE CASCADE,
  attempts INTEGER NOT NULL DEFAULT 0,
  correct INTEGER NOT NULL DEFAULT 0,
  wrong INTEGER NOT NULL DEFAULT 0,
  last_answer TEXT NOT NULL DEFAULT '',
  completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, exercise_id)
);

CREATE TABLE IF NOT EXISTS grammar_lesson_progress(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id INTEGER NOT NULL REFERENCES grammar_lessons(id) ON DELETE CASCADE,
  attempted INTEGER NOT NULL DEFAULT 0,
  correct INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS grammar_unit_progress(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  unit_id INTEGER NOT NULL REFERENCES grammar_units(id) ON DELETE CASCADE,
  attempted INTEGER NOT NULL DEFAULT 0,
  correct INTEGER NOT NULL DEFAULT 0,
  test_completed INTEGER NOT NULL DEFAULT 0 CHECK(test_completed IN (0,1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_grammar_units_level ON grammar_units(level, sequence, published);
CREATE INDEX IF NOT EXISTS idx_grammar_lessons_unit ON grammar_lessons(unit_id, sequence, published);
CREATE INDEX IF NOT EXISTS idx_grammar_exercises_lesson ON grammar_exercises(lesson_id, sequence, published);
CREATE INDEX IF NOT EXISTS idx_grammar_exercises_unit_test ON grammar_exercises(unit_id, is_unit_test, published);
CREATE INDEX IF NOT EXISTS idx_grammar_attempts_user ON grammar_attempts(user_id, completed);
