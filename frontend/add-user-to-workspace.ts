/**
 * Add current user to test workspace
 */
import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { addWorkspaceMember } from '@herofy/dataconnect';

const firebaseConfig = { projectId: 'herofy-496505' };
const app = initializeApp(firebaseConfig);
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});

connectDataConnectEmulator(dc, 'localhost', 9399);

const TEST_WORKSPACE_ID = '11111111111111111111111111111111';
const YOUR_USER_ID = 'rk07bQuUP7PbwFInqX0QWI23jKE3';

async function addUser() {
  console.log('Adding user to test workspace...');
  console.log('Workspace:', TEST_WORKSPACE_ID);
  console.log('User:', YOUR_USER_ID);

  try {
    await addWorkspaceMember(dc, {
      workspaceId: TEST_WORKSPACE_ID,
      userId: YOUR_USER_ID,
      role: 'owner',
    });

    console.log('✅ User added to workspace successfully!');
    console.log('Now refresh your browser and you should see the test customers.');
  } catch (e: any) {
    if (e.message?.includes('ALREADY_EXISTS')) {
      console.log('✅ User already member of workspace');
    } else {
      console.error('❌ Failed:', e.message);
    }
  }
}

addUser();
