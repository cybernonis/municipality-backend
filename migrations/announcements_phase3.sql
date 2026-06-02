-- Phase 3: Announcements table enhancements
-- Run this in the Supabase SQL Editor before deploying the updated code.

ALTER TABLE announcements
  ADD COLUMN IF NOT EXISTS is_important BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_urgent    BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS priority     INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS expires_at   TIMESTAMP NULL,
  ADD COLUMN IF NOT EXISTS category     VARCHAR(50) DEFAULT 'general',
  ADD COLUMN IF NOT EXISTS image_url    TEXT NULL;

-- Index for fast urgent/important queries
CREATE INDEX IF NOT EXISTS idx_announcements_urgent    ON announcements (is_urgent)    WHERE is_urgent = TRUE;
CREATE INDEX IF NOT EXISTS idx_announcements_important ON announcements (is_important) WHERE is_important = TRUE;
CREATE INDEX IF NOT EXISTS idx_announcements_expires   ON announcements (expires_at)   WHERE expires_at IS NOT NULL;
