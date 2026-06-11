#!/usr/bin/env npx tsx
/**
 * Fix workspace mismatch by creating the workspace that localStorage expects
 * Run with: npx tsx fix-workspace.ts <workspace-id>
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  createWorkspaceWithId,
  createUserWithId,
  addWorkspaceMemberPublic,
} from '@herofy/dataconnect';

const workspaceId = process.argv[2];
const userId = process.argv[3] || 'rk07bQuUP7PbwFInqX0QWI23jKE3';

if (!workspaceId) {
  console.error('Usage: npx tsx fix-workspace.ts <workspace-id> [user-id]');
  process.exit(1);
}

const firebaseConfig = {
  projectId: 'herofy-496505',
};

const app = initializeApp(firebaseConfig);
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});

connectDataConnectEmulator(dc, 'localhost', 9399);

async function fixWorkspace() {
  console.log(`Creating workspace: ${workspaceId}`);
  console.log(`For user: ${userId}\n`);

  try {
    // Create the workspace
    await createWorkspaceWithId({
      id: workspaceId,
      name: "Scott's Workspace",
      slug: `scotts-workspace-${Math.random().toString(36).substring(2, 6)}`,
    });
    console.log('✓ Workspace created');
  } catch (e: any) {
    if (e.message?.includes('duplicate')) {
      console.log('✓ Workspace already exists');
    } else {
      console.error('✗ Failed to create workspace:', e.message);
    }
  }

  try {
    // Create the user
    await createUserWithId({
      id: userId,
      displayName: 'Scott Key',
      email: 'scott@driftline.ai',
    });
    console.log('✓ User created');
  } catch (e: any) {
    if (e.message?.includes('duplicate')) {
      console.log('✓ User already exists');
    } else {
      console.error('✗ Failed to create user:', e.message);
    }
  }

  try {
    // Add user to workspace
    await addWorkspaceMemberPublic({
      workspaceId: workspaceId,
      userId: userId,
      role: 'owner',
    });
    console.log('✓ User added to workspace');
  } catch (e: any) {
    if (e.message?.includes('duplicate')) {
      console.log('✓ User already in workspace');
    } else {
      console.error('✗ Failed to add user to workspace:', e.message);
    }
  }

  console.log('\n✅ Done! Refresh your browser.');
}

fixWorkspace()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error('❌ Failed:', error);
    process.exit(1);
  });
