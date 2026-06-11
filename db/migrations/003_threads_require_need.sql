-- Migration: 003_threads_require_need.sql
-- Fixes the relationship: Threads belong to Needs, not the other way around
--
-- The model:
--   Need (the "why" - something requires attention)
--     └── Thread(s) (the "how" - conversations about it)
--           └── Interactions (individual messages)
--
-- A Need can have multiple Threads (e.g., CEO emailing + Engineer Slacking about same issue)
-- Every Thread must have a Need (no orphan conversations)

-- ============================================================================
-- ADD need_id TO THREADS
-- ============================================================================

-- Add need_id column to threads (nullable first for migration)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS need_id UUID REFERENCES needs(id);

-- Create index for looking up threads by need
CREATE INDEX IF NOT EXISTS idx_threads_need ON threads(need_id);

-- ============================================================================
-- BACKFILL: Create needs for orphan threads
-- ============================================================================

-- For any threads without a need, create one
-- This handles legacy data where threads existed without needs
INSERT INTO needs (
  workspace_id,
  customer_id,
  type,
  headline,
  lede,
  priority_rank,
  agent_reasoning,
  handbook_version_id,
  created_at
)
SELECT
  t.workspace_id,
  t.customer_id,
  CASE t.category
    WHEN 'support' THEN 'urgent_support'::need_type
    WHEN 'onboarding' THEN 'onboarding_behind'::need_type
    ELSE 'uncategorized'::need_type
  END,
  COALESCE(t.subject, 'Conversation'),
  'Migrated from legacy thread',
  100,
  'Auto-created during migration - thread existed without need',
  (SELECT id FROM handbook_versions ORDER BY created_at DESC LIMIT 1),
  t.created_at
FROM threads t
WHERE NOT EXISTS (
  SELECT 1 FROM needs n WHERE n.thread_id = t.id
)
AND t.need_id IS NULL;

-- Update threads to point to their needs (from the old needs.thread_id relationship)
UPDATE threads t
SET need_id = n.id
FROM needs n
WHERE n.thread_id = t.id
AND t.need_id IS NULL;

-- Update threads to point to newly created needs (from backfill above)
UPDATE threads t
SET need_id = n.id
FROM needs n
WHERE n.customer_id = t.customer_id
AND n.headline = COALESCE(t.subject, 'Conversation')
AND n.lede = 'Migrated from legacy thread'
AND t.need_id IS NULL;

-- ============================================================================
-- MAKE need_id REQUIRED (after backfill)
-- ============================================================================

-- Now that all threads have needs, make it required
-- Note: Run this only after verifying backfill worked
-- ALTER TABLE threads ALTER COLUMN need_id SET NOT NULL;

-- ============================================================================
-- ADD sidekick_question TO need_type ENUM
-- ============================================================================

-- Check if sidekick_question already exists in the enum
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'sidekick_question'
    AND enumtypid = 'need_type'::regtype
  ) THEN
    ALTER TYPE need_type ADD VALUE 'sidekick_question';
  END IF;
END
$$;

-- ============================================================================
-- UPDATE VIEWS
-- ============================================================================

-- Drop and recreate today_queue view to include thread count
DROP VIEW IF EXISTS today_queue;

CREATE VIEW today_queue AS
SELECT
  n.id,
  n.workspace_id,
  n.customer_id,
  n.type,
  n.headline,
  n.lede,
  n.priority_rank,
  n.agent_run_id,
  n.milestone_id,
  n.meeting_id,
  n.focus_section,
  n.snoozed_until,
  n.resolved_at,
  n.agent_reasoning,
  n.created_at,
  c.name AS customer_name,
  c.lifecycle AS customer_lifecycle,
  c.arr_cents AS customer_arr_cents,
  nr.primary_action AS recommendation_primary,
  nr.secondary_action AS recommendation_secondary,
  nr.rationale AS recommendation_rationale,
  (SELECT COUNT(*) FROM threads t WHERE t.need_id = n.id) AS thread_count,
  (SELECT id FROM threads t WHERE t.need_id = n.id ORDER BY updated_at DESC LIMIT 1) AS latest_thread_id
FROM needs n
JOIN customers c ON n.customer_id = c.id
LEFT JOIN need_recommendations nr ON nr.need_id = n.id
WHERE n.resolved_at IS NULL
  AND (n.snoozed_until IS NULL OR n.snoozed_until < NOW())
ORDER BY n.priority_rank ASC, n.created_at ASC;

-- ============================================================================
-- DEPRECATE needs.thread_id
-- ============================================================================

-- The old needs.thread_id is now deprecated
-- Threads point to needs, not the other way around
-- We keep it for backwards compatibility but it should not be used

COMMENT ON COLUMN needs.thread_id IS 'DEPRECATED: Use threads.need_id instead. Kept for backwards compatibility.';

-- ============================================================================
-- ADD THREAD TYPE FOR SIDEKICK
-- ============================================================================

-- Add a thread_type to distinguish sidekick conversations from customer conversations
-- This helps the UI know how to render the thread

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'thread_type') THEN
    CREATE TYPE thread_type AS ENUM ('customer', 'sidekick', 'internal');
  END IF;
END
$$;

ALTER TABLE threads ADD COLUMN IF NOT EXISTS thread_type thread_type DEFAULT 'customer';

-- Index for filtering by thread type
CREATE INDEX IF NOT EXISTS idx_threads_type ON threads(need_id, thread_type);
