ALTER TABLE question_bank_drafts ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE question_bank_drafts ADD COLUMN attribution TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_question_drafts_source_type
  ON question_bank_drafts(source_key,question_type,cefr_level);
