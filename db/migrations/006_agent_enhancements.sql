-- Migration 006: Agent Enhancements
-- Adds tables for signal deduplication and HITL answer tracking
--
-- Features:
-- 1. signal_fingerprints - Prevent duplicate signal processing
-- 2. agent_run_answers - Store HITL answers for paused agent runs

-- ============================================================================
-- Feature 5: Duplicate Signal Detection
-- ============================================================================

CREATE TABLE IF NOT EXISTS signal_fingerprints (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    fingerprint VARCHAR(64) NOT NULL, -- SHA256 hash (64 hex chars)
    signal_id UUID, -- Optional: link back to signal for debugging
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (workspace_id, fingerprint)
);

-- Index for cleanup queries (delete old fingerprints)
CREATE INDEX IF NOT EXISTS idx_signal_fingerprints_processed_at
ON signal_fingerprints(processed_at);

-- Index for workspace-scoped queries
CREATE INDEX IF NOT EXISTS idx_signal_fingerprints_workspace
ON signal_fingerprints(workspace_id);

COMMENT ON TABLE signal_fingerprints IS
'Stores fingerprints of processed signals to prevent duplicate processing across agent runs';

COMMENT ON COLUMN signal_fingerprints.fingerprint IS
'SHA256 hash of signal source + external_id + occurred_at + body_snippet';

-- ============================================================================
-- Feature 7: HITL Answer Extraction
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_run_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    question_id VARCHAR(100) NOT NULL, -- Matches question ID from clarifying_questions JSON
    answer_text TEXT NOT NULL,
    answered_by_user_id VARCHAR(128) REFERENCES users(id),
    answered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate answers for same question
    UNIQUE (agent_run_id, question_id)
);

-- Index for retrieving answers by agent run
CREATE INDEX IF NOT EXISTS idx_agent_run_answers_run
ON agent_run_answers(agent_run_id);

-- Index for workspace-scoped queries
CREATE INDEX IF NOT EXISTS idx_agent_run_answers_workspace
ON agent_run_answers(workspace_id);

-- Index for user answer history
CREATE INDEX IF NOT EXISTS idx_agent_run_answers_user
ON agent_run_answers(answered_by_user_id);

COMMENT ON TABLE agent_run_answers IS
'Stores answers to HITL clarifying questions for paused agent runs';

COMMENT ON COLUMN agent_run_answers.question_id IS
'Identifier matching the question in agent_runs.clarifying_questions JSON array';

-- ============================================================================
-- Grant permissions (adjust for your setup)
-- ============================================================================

-- If using a specific role for the application:
-- GRANT SELECT, INSERT, DELETE ON signal_fingerprints TO herofy_app;
-- GRANT SELECT, INSERT, UPDATE ON agent_run_answers TO herofy_app;
