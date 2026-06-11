-- Migration: 002_agent_runs.sql
-- Adds tables for autonomous agent execution tracking and workspace integrations

-- ============================================================================
-- AGENT EXECUTION STATE
-- ============================================================================

-- Agent execution status enum
CREATE TYPE agent_status AS ENUM (
  'initialized',
  'running',
  'waiting_for_input',
  'resuming',
  'completed',
  'failed'
);

-- Confidence level enum
CREATE TYPE confidence_level AS ENUM (
  'high',
  'medium',
  'low'
);

-- Track autonomous agent runs with pause/resume capability
CREATE TABLE agent_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  agent_name TEXT NOT NULL,  -- 'handoff_auto', 'signal_watcher', etc.
  status agent_status NOT NULL DEFAULT 'initialized',

  -- Trigger context
  trigger_type TEXT,  -- 'webhook', 'poll', 'manual'
  triggered_by TEXT,  -- 'scheduler', 'user:uuid', 'agent:signal_watcher'

  -- Input parameters (agent-specific)
  input_params JSONB NOT NULL DEFAULT '{}',

  -- Execution state for pause/resume
  current_step TEXT,  -- 'read_deal', 'gap_analysis', etc.
  context_snapshot JSONB,  -- Full serialized context for resume

  -- Confidence tracking
  confidence_level confidence_level,
  confidence_score NUMERIC(3,2),  -- 0.00 - 1.00
  confidence_reasons TEXT[],

  -- Pause state
  paused_at TIMESTAMPTZ,
  pause_reason TEXT,
  blocking_need_id UUID REFERENCES needs(id),
  clarifying_questions JSONB,  -- [{question, field, type, answer, answered_at}]

  -- Resume state
  resumed_at TIMESTAMPTZ,
  resume_answers JSONB,  -- Answers provided by human

  -- Output references
  customer_id UUID REFERENCES customers(id),
  brief_id UUID REFERENCES handoff_briefs(id),
  plan_id UUID REFERENCES ai_plans(id),

  -- Result
  result JSONB,  -- Final output data
  error_message TEXT,
  used_fallback BOOLEAN DEFAULT FALSE,
  fallback_reason TEXT,

  -- Timing
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  duration_ms INTEGER,

  -- Audit
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_agent_runs_workspace ON agent_runs(workspace_id);
CREATE INDEX idx_agent_runs_workspace_status ON agent_runs(workspace_id, status);
CREATE INDEX idx_agent_runs_waiting ON agent_runs(workspace_id, status)
  WHERE status = 'waiting_for_input';
CREATE INDEX idx_agent_runs_blocking_need ON agent_runs(blocking_need_id)
  WHERE blocking_need_id IS NOT NULL;
CREATE INDEX idx_agent_runs_agent_name ON agent_runs(agent_name, created_at DESC);

-- Updated_at trigger
CREATE TRIGGER update_agent_runs_updated_at
  BEFORE UPDATE ON agent_runs
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- WORKSPACE INTEGRATIONS (OAuth tokens, configs)
-- ============================================================================

-- Integration type enum
CREATE TYPE integration_type AS ENUM (
  'notion',
  'slack',
  'gmail',
  'hubspot',
  'calendar'
);

-- Integration status enum
CREATE TYPE integration_status AS ENUM (
  'pending',
  'active',
  'error',
  'revoked'
);

-- Store OAuth tokens and integration configs per workspace
CREATE TABLE workspace_integrations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  integration_type integration_type NOT NULL,

  -- OAuth tokens (should be encrypted in production)
  access_token TEXT,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,

  -- Integration-specific configuration
  config JSONB NOT NULL DEFAULT '{}',
  -- For Notion: {database_id, database_name, field_mappings}
  -- For Slack: {team_id, channel_id, bot_user_id}

  -- Status tracking
  status integration_status NOT NULL DEFAULT 'pending',
  last_sync_at TIMESTAMPTZ,
  last_error TEXT,
  error_count INTEGER DEFAULT 0,

  -- Audit
  connected_by_user_id TEXT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- One integration per type per workspace
  UNIQUE(workspace_id, integration_type)
);

-- Indexes
CREATE INDEX idx_workspace_integrations_workspace ON workspace_integrations(workspace_id);
CREATE INDEX idx_workspace_integrations_active ON workspace_integrations(workspace_id, integration_type)
  WHERE status = 'active';

-- Updated_at trigger
CREATE TRIGGER update_workspace_integrations_updated_at
  BEFORE UPDATE ON workspace_integrations
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- PROCESSED DEALS (Deduplication)
-- ============================================================================

-- Track which Notion deals we've already processed
CREATE TABLE processed_deals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  notion_deal_id TEXT NOT NULL,

  -- Processing result
  agent_run_id UUID REFERENCES agent_runs(id),
  customer_id UUID REFERENCES customers(id),
  brief_id UUID REFERENCES handoff_briefs(id),

  -- Status
  status TEXT NOT NULL DEFAULT 'processed',  -- 'processed', 'skipped', 'failed'
  skip_reason TEXT,

  -- Timing
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Prevent reprocessing same deal
  UNIQUE(workspace_id, notion_deal_id)
);

-- Index for lookups
CREATE INDEX idx_processed_deals_workspace ON processed_deals(workspace_id, processed_at DESC);


-- ============================================================================
-- WORKSPACE AGENT SETTINGS
-- ============================================================================

-- Agent configuration per workspace
CREATE TABLE workspace_agent_settings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  agent_name TEXT NOT NULL,  -- 'handoff_auto', 'signal_watcher', etc.

  -- Autonomy settings
  autonomy_mode TEXT NOT NULL DEFAULT 'smart_auto',  -- 'full_auto', 'smart_auto', 'supervised'
  pause_on_medium_confidence BOOLEAN DEFAULT TRUE,

  -- Timeout settings
  question_timeout_hours INTEGER DEFAULT 24,
  fallback_on_timeout BOOLEAN DEFAULT TRUE,

  -- Notification settings
  notify_on_pause BOOLEAN DEFAULT TRUE,
  notify_on_complete BOOLEAN DEFAULT FALSE,
  notification_channel TEXT DEFAULT 'app',  -- 'app', 'slack', 'email'

  -- Polling settings (for autonomous agents)
  poll_enabled BOOLEAN DEFAULT TRUE,
  poll_interval_minutes INTEGER DEFAULT 15,

  -- Feature flags
  enabled BOOLEAN DEFAULT TRUE,

  -- Audit
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- One config per agent per workspace
  UNIQUE(workspace_id, agent_name)
);

-- Updated_at trigger
CREATE TRIGGER update_workspace_agent_settings_updated_at
  BEFORE UPDATE ON workspace_agent_settings
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- EXTEND NEEDS TABLE
-- ============================================================================

-- Add agent_run_id to link needs to agent runs (for resume flow)
ALTER TABLE needs ADD COLUMN IF NOT EXISTS agent_run_id UUID REFERENCES agent_runs(id);

-- Index for finding needs linked to agent runs
CREATE INDEX IF NOT EXISTS idx_needs_agent_run ON needs(agent_run_id)
  WHERE agent_run_id IS NOT NULL;


-- ============================================================================
-- SEED DATA
-- ============================================================================

-- Add 'agent_clarification' to need types if not exists
-- (This would require altering the need_type enum - keeping as uncategorized for now)

-- Default agent settings for existing workspaces (optional, run manually)
-- INSERT INTO workspace_agent_settings (workspace_id, agent_name, autonomy_mode)
-- SELECT id, 'handoff_auto', 'smart_auto' FROM workspaces
-- ON CONFLICT DO NOTHING;
