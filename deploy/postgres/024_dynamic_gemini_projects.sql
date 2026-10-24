ALTER TABLE ai_usage ADD COLUMN provider_project_id TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS gemini_project_state(
  project_id TEXT PRIMARY KEY,
  project_label TEXT NOT NULL,
  weight BIGINT NOT NULL DEFAULT 1 CHECK(weight>=1),
  selection_count BIGINT NOT NULL DEFAULT 0 CHECK(selection_count>=0),
  success_count BIGINT NOT NULL DEFAULT 0 CHECK(success_count>=0),
  failure_count BIGINT NOT NULL DEFAULT 0 CHECK(failure_count>=0),
  quota_failure_count BIGINT NOT NULL DEFAULT 0 CHECK(quota_failure_count>=0),
  cooldown_until TEXT,
  last_status TEXT NOT NULL DEFAULT '',
  last_selected_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gemini_project_state_cooldown
ON gemini_project_state(cooldown_until,last_selected_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_provider_project_time
ON ai_usage(provider_project_id,created_at);
