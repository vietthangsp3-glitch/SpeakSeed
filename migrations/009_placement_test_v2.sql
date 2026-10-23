CREATE TABLE IF NOT EXISTS placement_responses(
  attempt_id INTEGER NOT NULL REFERENCES placement_attempts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_key TEXT NOT NULL,
  answer TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'answered' CHECK(state IN ('in_progress','answered','skipped','audio_unavailable')),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(attempt_id,question_key)
);

CREATE INDEX IF NOT EXISTS idx_placement_responses_owner
  ON placement_responses(user_id,attempt_id,updated_at);
