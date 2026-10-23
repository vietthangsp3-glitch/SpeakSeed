CREATE TABLE IF NOT EXISTS content_license_decisions(
  id INTEGER PRIMARY KEY,
  source_key TEXT NOT NULL REFERENCES content_sources(source_key) ON DELETE RESTRICT,
  decision TEXT NOT NULL CHECK(decision IN ('pass','blocked')),
  evidence_url TEXT NOT NULL,
  reason TEXT NOT NULL,
  actor_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  actor_name TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_license_decisions_source
  ON content_license_decisions(source_key,occurred_at,id);
CREATE TRIGGER IF NOT EXISTS immutable_content_license_decisions_update
BEFORE UPDATE ON content_license_decisions BEGIN SELECT RAISE(ABORT,'license decision log is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_content_license_decisions_delete
BEFORE DELETE ON content_license_decisions BEGIN SELECT RAISE(ABORT,'license decision log is immutable'); END;
