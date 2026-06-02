-- Closed Roads system
-- Run this in the Supabase SQL Editor before deploying.

CREATE TABLE IF NOT EXISTS closed_roads (
  id          UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  road_name   TEXT      NOT NULL,
  reason      TEXT,
  start_date  TIMESTAMP NOT NULL DEFAULT NOW(),
  end_date    TIMESTAMP,
  status      TEXT      DEFAULT 'active',
  coordinates JSONB,
  created_by  UUID      REFERENCES auth.users(id),
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_closed_roads_status     ON closed_roads (status);
CREATE INDEX IF NOT EXISTS idx_closed_roads_end_date   ON closed_roads (end_date) WHERE end_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_closed_roads_start_date ON closed_roads (start_date DESC);
