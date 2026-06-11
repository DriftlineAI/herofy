-- Migration: Rename workspace roles
-- csm -> admin, viewer -> member
--
-- NOTE: Firebase SQL Connect uses enum values directly. This migration updates
-- existing data to use the new role names: owner | admin | member

-- Update csm -> admin
UPDATE workspace_members SET role = 'admin' WHERE role = 'csm';

-- Update viewer -> member
UPDATE workspace_members SET role = 'member' WHERE role = 'viewer';

-- Note: The WorkspaceInvitation table is created automatically by Firebase SQL Connect
-- based on the schema.gql definition. No explicit CREATE TABLE needed here.
