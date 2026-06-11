-- Migration: 004_meetings_need_id.sql
-- Adds need_id to meetings table
--
-- The model:
--   Need (the "why" - something requires attention)
--     ├── Thread(s) - conversations about it
--     ├── Meeting(s) - calls to address it
--     ├── Milestones - plan steps for it
--     └── Commitments - promises made about it
--
-- Note: This is different from needs.meeting_id which means
-- "this need is about preparing for this meeting" (meeting_prep_ready type)
--
-- meetings.need_id means "this meeting is to address this need"
-- It's nullable for ad hoc meetings that don't relate to a specific need

-- ============================================================================
-- ADD need_id TO MEETINGS
-- ============================================================================

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS need_id UUID REFERENCES needs(id);

-- Index for looking up meetings by need
CREATE INDEX IF NOT EXISTS idx_meetings_need ON meetings(need_id) WHERE need_id IS NOT NULL;

-- ============================================================================
-- UPDATE VIEWS (if any reference meetings)
-- ============================================================================

-- No views currently need updating for this change

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON COLUMN meetings.need_id IS 'The need this meeting addresses. NULL for ad hoc meetings.';
COMMENT ON COLUMN needs.meeting_id IS 'The meeting this need is about (e.g., meeting_prep_ready). Different from meetings.need_id.';
