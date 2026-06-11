import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { createUserWithId, addWorkspaceMemberPublic } from '@herofy/dataconnect';

const firebaseConfig = { projectId: 'herofy-496505' };
const app = initializeApp(firebaseConfig);
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});

connectDataConnectEmulator(dc, 'localhost', 9399);

const TEST_WORKSPACE_ID = '11111111111111111111111111111111';
const SCOTT_USER_ID = 'rk07bQuUP7PbwFInqX0QWI23jKE3';

async function addScott() {
  // 1. Create user record
  console.log('Creating user record...');
  try {
    await createUserWithId({
      id: SCOTT_USER_ID,
      email: 'scott@driftline.ai',
      displayName: 'Scott',
    });
    console.log('✓ User created');
  } catch (e: any) {
    if (e.message?.includes('ALREADY_EXISTS')) {
      console.log('✓ User already exists');
    } else {
      console.error('User creation failed:', e.message);
    }
  }

  // 2. Add to workspace
  console.log('\nAdding to test workspace...');
  try {
    await addWorkspaceMemberPublic(dc, {
      workspaceId: TEST_WORKSPACE_ID,
      userId: SCOTT_USER_ID,
      role: 'owner',
    });
    console.log('✓ Added to workspace successfully!');
  } catch (e: any) {
    if (e.message?.includes('ALREADY_EXISTS')) {
      console.log('✓ Already a member of workspace');
    } else {
      console.error('Failed:', e.message);
    }
  }

  console.log('\n✅ Done! Refresh your browser to see the test customers.');
}

addScott();
