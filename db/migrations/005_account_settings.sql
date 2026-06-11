-- Migration: Account Settings
-- Adds autonomy_level to workspaces and notification_preferences to users

-- Create autonomy_level enum
CREATE TYPE autonomy_level AS ENUM ('full_auto', 'smart_auto', 'supervised');

-- Add autonomy_level to workspaces (controls agent behavior)
ALTER TABLE workspaces ADD COLUMN autonomy_level autonomy_level NOT NULL DEFAULT 'smart_auto';

-- Add notification_preferences to users
ALTER TABLE users ADD COLUMN notification_preferences JSONB DEFAULT '{"email": true, "in_app": true}'::jsonb;

-- Add avatar_seed to users (for deterministic DiceBear avatars)
ALTER TABLE users ADD COLUMN avatar_seed TEXT;
