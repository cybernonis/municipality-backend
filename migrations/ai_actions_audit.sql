-- AI Admin Actions Audit Log
-- Run this in the Supabase SQL Editor before deploying.

CREATE TABLE IF NOT EXISTS ai_action_logs (
  id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID,
  user_email    TEXT,
  action_type   TEXT      NOT NULL,
  user_message  TEXT      NOT NULL,
  ai_intent     JSONB,
  params        JSONB,
  status        TEXT      DEFAULT 'pending',
  result        JSONB,
  error_message TEXT,
  confirmed     BOOLEAN   DEFAULT FALSE,
  created_at    TIMESTAMP DEFAULT NOW(),
  executed_at   TIMESTAMP,
  duration_ms   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ai_actions_user   ON ai_action_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_actions_type   ON ai_action_logs (action_type);
CREATE INDEX IF NOT EXISTS idx_ai_actions_status ON ai_action_logs (status);
