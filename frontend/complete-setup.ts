#!/usr/bin/env npx tsx
/**
 * Mark workspace setup as complete
 * Run with: npx tsx complete-setup.ts <workspace-id>
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { completeWorkspaceSetup } from '@herofy/dataconnect';

const workspaceId = process.argv[2] || '360f25d26f4f4df8aeedb8e4607e1103';

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

async function complete() {
  console.log(`Marking workspace ${workspaceId} as setup complete...\n`);

  try {
    await completeWorkspaceSetup({ workspaceId });
    console.log('✅ Setup marked as complete!');
    console.log('\nNow refresh your browser.');
  } catch (e: any) {
    console.error('❌ Failed:', e.message);
    process.exit(1);
  }
}

complete()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error('❌ Failed:', error);
    process.exit(1);
  });
