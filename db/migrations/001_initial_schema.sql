-- Herofy Database Schema
-- Version: 1.0.0
-- Description: Full schema for customer success workspace

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE workspace_role AS ENUM ('owner', 'csm', 'viewer');
CREATE TYPE customer_lifecycle AS ENUM ('prospect', 'handoff', 'onboarding', 'active', 'renewing', 'at_risk', 'churned');
CREATE TYPE renewal_readiness AS ENUM ('not_started', 'tracking', 'ready', 'at_risk');
CREATE TYPE stakeholder_status AS ENUM ('active', 'departed');
CREATE TYPE goal_status AS ENUM ('active', 'achieved', 'dropped');
CREATE TYPE interaction_channel AS ENUM ('email', 'slack', 'meeting', 'in_app', 'sms_screenshot', 'note');
CREATE TYPE interaction_direction AS ENUM ('us', 'customer', 'internal');
CREATE TYPE thread_status AS ENUM ('open', 'resolved', 'archived');
CREATE TYPE thread_category AS ENUM ('support', 'onboarding', 'success', 'uncategorized');
CREATE TYPE meeting_source AS ENUM ('manual', 'google_calendar', 'mcp_sync');
CREATE TYPE milestone_status AS ENUM ('not_started', 'in_progress', 'blocked', 'done', 'skipped');
CREATE TYPE owner_side AS ENUM ('us', 'customer', 'joint');
CREATE TYPE commitment_status AS ENUM ('in_progress', 'done', 'overdue');
CREATE TYPE commitment_side AS ENUM ('us', 'them');
CREATE TYPE signal_kind AS ENUM ('engagement', 'sentiment', 'commitments');
CREATE TYPE signal_state AS ENUM ('ok', 'warn', 'risk');
CREATE TYPE risk_level AS ENUM ('low', 'medium', 'high');
CREATE TYPE blast_radius AS ENUM ('low', 'medium', 'high');

-- HITL-specific enums
CREATE TYPE approval_status AS ENUM ('pending_approval', 'approved', 'rejected', 'superseded');
CREATE TYPE handoff_status AS ENUM ('draft', 'confirmed', 'needs_correction');
CREATE TYPE draft_response_status AS ENUM ('pending_review', 'approved', 'sent', 'discarded', 'edited');

-- Need types (comprehensive list)
CREATE TYPE need_type AS ENUM (
  'urgent_support',
  'going_dark',
  'stalled_milestone',
  'approaching_renewal',
  'open_commitment_overdue',
  'frustrated_signal',
  'champion_departed',
  'onboarding_behind',
  'renewal_at_risk',
  'new_handoff',
  'meeting_prep_ready',
  'positive_signal',
  'expansion_signal',
  'check_in_due',
  'escalation',
  'plan_approval_required',
  'draft_response_ready',
  'uncategorized'
);

-- ============================================================================
-- CORE TENANCY
-- ============================================================================

CREATE TABLE workspaces (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
  id TEXT PRIMARY KEY, -- Matches Firebase Auth UID
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE workspace_members (
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role workspace_role NOT NULL DEFAULT 'csm',
  joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (workspace_id, user_id)
);

-- ============================================================================
-- CUSTOMERS
-- ============================================================================

CREATE TABLE customers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  one_liner TEXT,
  tier TEXT,
  arr_cents BIGINT,
  lifecycle customer_lifecycle NOT NULL DEFAULT 'prospect',
  days_to_renewal INTEGER,
  onboarding_day_current INTEGER,
  onboarding_day_total INTEGER,
  renewal_readiness renewal_readiness DEFAULT 'not_started',
  value_realization_text TEXT,
  adapted_from_playbook_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(workspace_id, slug)
);

CREATE TABLE stakeholders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  email TEXT,
  role TEXT,
  status stakeholder_status NOT NULL DEFAULT 'active',
  sentiment_note TEXT,
  last_interaction_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE goals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  status goal_status NOT NULL DEFAULT 'active',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- INTERACTIONS (The Spine)
-- ============================================================================

CREATE TABLE threads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  subject TEXT,
  status thread_status NOT NULL DEFAULT 'open',
  channel interaction_channel,
  assigned_user_id TEXT REFERENCES users(id),
  category thread_category NOT NULL DEFAULT 'uncategorized',
  ai_category_suggestion thread_category,
  origin_detail TEXT,
  archived_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE interactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  thread_id UUID REFERENCES threads(id) ON DELETE SET NULL,
  channel interaction_channel NOT NULL,
  origin_kind TEXT,
  direction interaction_direction NOT NULL,
  sender_name TEXT,
  sender_user_id TEXT REFERENCES users(id),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  subject TEXT,
  -- TODO: Add pgcrypto encryption for production
  body_encrypted TEXT,
  summary_ai TEXT,
  external_ref JSONB, -- {system, thread_id, message_id}
  body_stored_at TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- MEETINGS
-- ============================================================================

CREATE TABLE meetings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  type TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  duration_minutes INTEGER,
  source meeting_source NOT NULL DEFAULT 'manual',
  external_event_id TEXT, -- Google Calendar event ID for dedup
  attendees_ours JSONB,
  attendees_theirs JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE meeting_briefs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  progress_narrative TEXT,
  progress_facts JSONB,
  friction TEXT,
  talking_points JSONB,
  value_delivered TEXT,
  risk_to_renewal TEXT,
  expansion_signals TEXT,
  pricing_context TEXT,
  followup_email JSONB,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- COMMITMENTS & MILESTONES
-- ============================================================================

CREATE TABLE milestones (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  owner_label TEXT,
  owner_side owner_side NOT NULL DEFAULT 'joint',
  target_date DATE,
  status milestone_status NOT NULL DEFAULT 'not_started',
  description TEXT,
  blocked_reason TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  adapted_from_playbook_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE commitments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  side commitment_side NOT NULL,
  text TEXT NOT NULL,
  due_label TEXT,
  status commitment_status NOT NULL DEFAULT 'in_progress',
  source_interaction_id UUID REFERENCES interactions(id),
  source_meeting_id UUID REFERENCES meetings(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- SIGNALS & NEEDS
-- ============================================================================

CREATE TABLE signals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  kind signal_kind NOT NULL,
  state signal_state NOT NULL,
  sentence TEXT,
  evidence_text TEXT,
  next_action TEXT,
  superseded_at TIMESTAMPTZ, -- When a newer signal replaced this one
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE needs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  type need_type NOT NULL,
  headline TEXT NOT NULL,
  lede TEXT,
  priority_rank INTEGER NOT NULL DEFAULT 100,
  thread_id UUID REFERENCES threads(id),
  milestone_id UUID REFERENCES milestones(id),
  meeting_id UUID REFERENCES meetings(id),
  focus_section TEXT,
  snoozed_until TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  source JSONB, -- {channel, from, quote}
  agent_reasoning TEXT NOT NULL, -- REQUIRED: explains why this was surfaced
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE need_recommendations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  need_id UUID NOT NULL REFERENCES needs(id) ON DELETE CASCADE,
  rationale TEXT,
  primary_action TEXT,
  secondary_action TEXT,
  confidence_text TEXT,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE need_evidence (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  need_id UUID NOT NULL REFERENCES needs(id) ON DELETE CASCADE,
  interaction_id UUID REFERENCES interactions(id),
  meeting_id UUID REFERENCES meetings(id),
  commitment_id UUID REFERENCES commitments(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- RISK MANAGEMENT
-- ============================================================================

CREATE TABLE risk_briefs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  what_changed TEXT,
  evidence_text TEXT,
  play TEXT,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE risk_play_steps (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  brief_id UUID NOT NULL REFERENCES risk_briefs(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  rationale TEXT,
  done BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE renewal_risks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  risk_level risk_level NOT NULL,
  summary TEXT,
  evidence_ids JSONB,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- HANDOFFS (HITL)
-- ============================================================================

CREATE TABLE handoff_briefs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL, -- NULL if customer not yet created
  captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  day_current INTEGER,
  day_total INTEGER,
  sales_commitments JSONB,
  technical_context JSONB,
  reality_check_confidence TEXT,
  reality_check_risks TEXT,
  -- HITL fields
  status handoff_status NOT NULL DEFAULT 'draft',
  user_corrections JSONB, -- User can annotate what was wrong
  confirmed_by_user_id TEXT REFERENCES users(id),
  confirmed_at TIMESTAMPTZ,
  -- External reference
  notion_deal_id TEXT,
  notion_deal_url TEXT,
  -- AI metadata
  handbook_version_id UUID NOT NULL,
  model TEXT,
  prompt_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE handoff_open_questions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  brief_id UUID NOT NULL REFERENCES handoff_briefs(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  resolved BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- AI PLANS (HITL)
-- ============================================================================

CREATE TABLE ai_plans (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
  brief_id UUID REFERENCES handoff_briefs(id) ON DELETE SET NULL,
  archetype_name TEXT,
  milestone_count INTEGER,
  duration_label TEXT,
  rationale TEXT,
  headline TEXT,
  milestones JSONB, -- Array of milestone objects
  -- HITL approval workflow
  status approval_status NOT NULL DEFAULT 'pending_approval',
  approved_by_user_id TEXT REFERENCES users(id),
  approved_at TIMESTAMPTZ,
  rejection_reason TEXT, -- Feeds into regeneration
  regenerated_from_plan_id UUID REFERENCES ai_plans(id),
  human_edited BOOLEAN NOT NULL DEFAULT FALSE, -- Track if user modified
  regeneration_count INTEGER NOT NULL DEFAULT 0, -- Analytics
  -- AI metadata
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  inputs_hash TEXT NOT NULL,
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- DRAFT RESPONSES (HITL)
-- ============================================================================

CREATE TABLE draft_responses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  thread_id UUID REFERENCES threads(id) ON DELETE SET NULL,
  subject TEXT,
  body TEXT NOT NULL,
  -- HITL approval workflow
  status draft_response_status NOT NULL DEFAULT 'pending_review',
  edited_body TEXT, -- User's edited version
  approved_by_user_id TEXT REFERENCES users(id),
  approved_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  auto_send_after TIMESTAMPTZ, -- Future: auto-send if user doesn't respond
  -- Link to surfaced need
  surfaced_in_need_id UUID REFERENCES needs(id),
  -- AI metadata
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  handbook_version_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- CAPTURED ITEMS
-- ============================================================================

CREATE TABLE captured_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  meeting_id UUID REFERENCES meetings(id),
  tag TEXT NOT NULL, -- commitment, goal, risk, followup, decision
  text TEXT NOT NULL,
  due_label TEXT,
  published BOOLEAN NOT NULL DEFAULT FALSE,
  captured_by_user_id TEXT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- HANDBOOK
-- ============================================================================

CREATE TABLE handbook_docs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  body TEXT NOT NULL,
  blast_radius blast_radius NOT NULL DEFAULT 'low',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(workspace_id, slug)
);

CREATE TABLE handbook_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  doc_id UUID NOT NULL REFERENCES handbook_docs(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  edited_by_user_id TEXT REFERENCES users(id),
  edited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- PLAYBOOKS
-- ============================================================================

CREATE TABLE playbooks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  archetype TEXT,
  fit_note TEXT,
  drawn_from_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE playbook_milestones (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  playbook_id UUID NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  owner_side owner_side NOT NULL DEFAULT 'joint',
  duration_days INTEGER,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- AGENT STATE
-- ============================================================================

CREATE TABLE agent_state (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  key TEXT NOT NULL, -- gmail_watermark, slack_watermark, notion_watermark
  value TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(workspace_id, key)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Core lookups
CREATE INDEX idx_workspace_members_user ON workspace_members(user_id);
CREATE INDEX idx_customers_workspace ON customers(workspace_id);
CREATE INDEX idx_customers_lifecycle ON customers(workspace_id, lifecycle);
CREATE INDEX idx_stakeholders_customer ON stakeholders(customer_id);
CREATE INDEX idx_stakeholders_email_domain ON stakeholders(workspace_id, (split_part(email, '@', 2)));

-- Interactions & threads
CREATE INDEX idx_interactions_customer ON interactions(customer_id);
CREATE INDEX idx_interactions_occurred ON interactions(workspace_id, occurred_at DESC);
CREATE INDEX idx_interactions_thread ON interactions(thread_id);
CREATE INDEX idx_threads_customer ON threads(customer_id);
CREATE INDEX idx_threads_status ON threads(workspace_id, status);

-- Meetings
CREATE INDEX idx_meetings_customer ON meetings(customer_id);
CREATE INDEX idx_meetings_scheduled ON meetings(workspace_id, scheduled_at);

-- Needs (today queue)
CREATE INDEX idx_needs_workspace ON needs(workspace_id);
CREATE INDEX idx_needs_customer ON needs(customer_id);
CREATE INDEX idx_needs_resolved ON needs(workspace_id, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX idx_needs_snoozed ON needs(workspace_id, snoozed_until) WHERE snoozed_until IS NOT NULL;
CREATE INDEX idx_needs_priority ON needs(workspace_id, priority_rank, created_at);

-- Signals
CREATE INDEX idx_signals_customer_kind ON signals(customer_id, kind);
CREATE INDEX idx_signals_active ON signals(customer_id, kind) WHERE superseded_at IS NULL;

-- AI Plans (HITL)
CREATE INDEX idx_ai_plans_status ON ai_plans(workspace_id, status);
CREATE INDEX idx_ai_plans_customer ON ai_plans(customer_id);
CREATE INDEX idx_ai_plans_brief ON ai_plans(brief_id);

-- Handoff briefs
CREATE INDEX idx_handoff_briefs_status ON handoff_briefs(workspace_id, status);
CREATE INDEX idx_handoff_briefs_customer ON handoff_briefs(customer_id);

-- Draft responses
CREATE INDEX idx_draft_responses_status ON draft_responses(workspace_id, status);
CREATE INDEX idx_draft_responses_thread ON draft_responses(thread_id);

-- Milestones & commitments
CREATE INDEX idx_milestones_customer ON milestones(customer_id);
CREATE INDEX idx_milestones_status ON milestones(customer_id, status);
CREATE INDEX idx_commitments_customer ON commitments(customer_id);
CREATE INDEX idx_commitments_status ON commitments(customer_id, status);

-- Handbook
CREATE INDEX idx_handbook_versions_doc ON handbook_versions(doc_id, edited_at DESC);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Today Queue: Active needs that should be shown
CREATE VIEW today_queue AS
SELECT
  n.id,
  n.workspace_id,
  n.customer_id,
  n.type,
  n.headline,
  n.lede,
  n.priority_rank,
  n.thread_id,
  n.milestone_id,
  n.meeting_id,
  n.focus_section,
  n.snoozed_until,
  n.agent_reasoning,
  n.created_at,
  c.name AS customer_name,
  c.lifecycle AS customer_lifecycle,
  c.arr_cents AS customer_arr_cents,
  nr.primary_action AS recommendation_primary,
  nr.secondary_action AS recommendation_secondary,
  nr.rationale AS recommendation_rationale
FROM needs n
JOIN customers c ON n.customer_id = c.id
LEFT JOIN need_recommendations nr ON nr.need_id = n.id
WHERE n.resolved_at IS NULL
  AND (n.snoozed_until IS NULL OR n.snoozed_until < NOW())
ORDER BY n.priority_rank ASC, n.created_at ASC;

-- Renewals View: Customers with upcoming renewals
CREATE VIEW renewals_view AS
SELECT
  c.*,
  CASE
    WHEN c.days_to_renewal <= 30 THEN '0-30'
    WHEN c.days_to_renewal <= 60 THEN '31-60'
    WHEN c.days_to_renewal <= 90 THEN '61-90'
    ELSE '90+'
  END AS renewal_band,
  (
    SELECT jsonb_agg(jsonb_build_object('kind', s.kind, 'state', s.state, 'sentence', s.sentence))
    FROM signals s
    WHERE s.customer_id = c.id AND s.superseded_at IS NULL
  ) AS current_signals
FROM customers c
WHERE c.days_to_renewal IS NOT NULL AND c.days_to_renewal <= 90
ORDER BY c.days_to_renewal ASC;

-- ============================================================================
-- TRIGGERS: Auto-update updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_workspaces_updated_at BEFORE UPDATE ON workspaces FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_stakeholders_updated_at BEFORE UPDATE ON stakeholders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_goals_updated_at BEFORE UPDATE ON goals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON threads FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_interactions_updated_at BEFORE UPDATE ON interactions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_meetings_updated_at BEFORE UPDATE ON meetings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_meeting_briefs_updated_at BEFORE UPDATE ON meeting_briefs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_milestones_updated_at BEFORE UPDATE ON milestones FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_commitments_updated_at BEFORE UPDATE ON commitments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_signals_updated_at BEFORE UPDATE ON signals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_needs_updated_at BEFORE UPDATE ON needs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_risk_briefs_updated_at BEFORE UPDATE ON risk_briefs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_renewal_risks_updated_at BEFORE UPDATE ON renewal_risks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_handoff_briefs_updated_at BEFORE UPDATE ON handoff_briefs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_ai_plans_updated_at BEFORE UPDATE ON ai_plans FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_draft_responses_updated_at BEFORE UPDATE ON draft_responses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_captured_items_updated_at BEFORE UPDATE ON captured_items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_handbook_docs_updated_at BEFORE UPDATE ON handbook_docs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_playbooks_updated_at BEFORE UPDATE ON playbooks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
