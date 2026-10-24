ALTER TABLE ai_usage ADD COLUMN request_fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_usage ADD COLUMN result_json TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_usage_user_pronunciation_request
ON ai_usage(user_id,feature,request_fingerprint)
WHERE user_id IS NOT NULL AND feature='pronunciation' AND request_fingerprint<>'';
