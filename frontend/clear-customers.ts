/**
 * Clear all customers for testing the Notion import flow
 * Run with: cd frontend && npx tsx clear-customers.ts
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { deleteAllCustomersForWorkspacePublic } from '@herofy/dataconnect';

const firebaseConfig = {
  projectId: 'herofy-496505',
};

const app = initializeApp(firebaseConfig);
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});

// Connect to emulator
connectDataConnectEmulator(dc, 'localhost', 9399);

// Scott's workspace ID (from backend logs)
const WORKSPACE_ID = '2abefbc3e50544cd95898dbfd9c0cd7e';

async function clearCustomers() {
  console.log('🧹 Clearing all customers for workspace:', WORKSPACE_ID);

  try {
    await deleteAllCustomersForWorkspacePublic({ workspaceId: WORKSPACE_ID });
    console.log('✓ All customers cleared!');
    console.log('\nYou can now test the Notion import flow from scratch.');
  } catch (e: any) {
    console.error('Failed to clear customers:', e.message);
  }
}

clearCustomers();
