/**
 * Clear Notion integration from database
 * Run with: npx tsx clear-notion.ts
 */

import { initializeApp } from 'firebase/app';
import { connectDataConnectEmulator, getDataConnect } from 'firebase/data-connect';
import { connectorConfig } from './src/dataconnect-generated/connector/connector';

// Initialize Firebase (emulator mode)
const app = initializeApp({
  projectId: 'herofy-496505',
  apiKey: 'fake-api-key',
});

const dataConnect = getDataConnect(app, connectorConfig);
connectDataConnectEmulator(dataConnect, 'localhost', 9399);

async function clearNotion() {
  console.log('🔄 Clearing Notion integration from database...');

  try {
    // Delete all Notion integrations
    const result = await dataConnect.executeMutation({
      query: `
        mutation DeleteNotionIntegrations {
          workspace_integrations_deleteMany(
            where: { integrationType: { eq: NOTION } }
          ) {
            rows_affected
          }
        }
      `,
      variables: {},
    });

    console.log('✅ Deleted integrations:', result.data);

    // Also clear OAuth connections
    const oauthResult = await dataConnect.executeMutation({
      query: `
        mutation DeleteNotionOAuthConnections {
          oauth_connections_deleteMany(
            where: { provider: { eq: NOTION } }
          ) {
            rows_affected
          }
        }
      `,
      variables: {},
    });

    console.log('✅ Deleted OAuth connections:', oauthResult.data);

    console.log('\n✅ Database cleared! You can now:');
    console.log('1. Clear browser storage (run /tmp/clear_storage.js in console)');
    console.log('2. Refresh the page');
    console.log('3. Try connecting to Notion again');

  } catch (error) {
    console.error('❌ Error clearing database:', error);
    throw error;
  }
}

clearNotion().then(() => process.exit(0)).catch(() => process.exit(1));
