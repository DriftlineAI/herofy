-- Migration: Add Slack team_id to workspace_integrations
-- Enables webhook routing (team_id -> workspace_id lookup)

-- Add slackTeamId column (nullable, only used by Slack integrations)
ALTER TABLE workspace_integrations ADD COLUMN slack_team_id TEXT;

-- Add index for team_id lookups (used by webhook handler)
CREATE INDEX idx_workspace_integrations_slack_team_id
ON workspace_integrations(slack_team_id)
WHERE slack_team_id IS NOT NULL;

-- Note: Column is nullable because only Slack integrations use it
-- Gmail, Calendar, Notion integrations will have NULL
