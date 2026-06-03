-- Phase 12: Authentication & Authorization Hardening
-- Run in Supabase SQL Editor.  Additive only — no DROP on production columns.
--
-- IMPORTANT: If a login_attempts table already exists from Phase S1
-- (it has columns: ip_address, attempts, blocked_until, last_attempt),
-- its schema is incompatible with Phase 12.  Run this first:
--   DROP TABLE IF EXISTS login_attempts CASCADE;
-- Then execute the rest of this file.
-- ─────────────────────────────────────────────────────────────────────────────

-- B. Account lockout — one row per attempt (email + ip + success + timestamp)
CREATE TABLE IF NOT EXISTS login_attempts (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email      text,
  ip         text,
  success    boolean,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email_ts
  ON login_attempts (email, created_at DESC);

-- C. MFA recovery codes (Supabase does not provide these natively)
CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL,
  code_hash  text        NOT NULL,  -- SHA-256 of plaintext code; plaintext never stored
  used       boolean     DEFAULT false,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mfa_recovery_codes_user
  ON mfa_recovery_codes (user_id);

-- D. Login history
CREATE TABLE IF NOT EXISTS login_sessions (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL,
  ip           text,
  user_agent   text,
  device_label text,
  created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_sessions_user_ts
  ON login_sessions (user_id, created_at DESC);
