-- Phase S1 Security: brute-force protection table
-- Run in Supabase SQL Editor before deploying.

CREATE TABLE IF NOT EXISTS login_attempts (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  ip_address    TEXT        NOT NULL,
  attempts      INTEGER     DEFAULT 1,
  blocked_until TIMESTAMPTZ,
  last_attempt  TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts (ip_address);
CREATE INDEX IF NOT EXISTS idx_login_attempts_blocked  ON login_attempts (blocked_until);

-- Ensure users table has role column (safe if already exists)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'citizen';
