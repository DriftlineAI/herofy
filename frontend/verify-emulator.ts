import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { getCustomersPublic } from '@herofy/dataconnect';

const firebaseConfig = { projectId: 'herofy-496505' };
const app = initializeApp(firebaseConfig);
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});

connectDataConnectEmulator(dc, 'localhost', 9399);

async function verify() {
  console.log('Querying emulator...');

  try {
    const result = await getCustomersPublic(dc, {
      workspaceId: '11111111-1111-1111-1111-111111111111'
    });

    const customers = result.data.customers;
    console.log(`Found ${customers.length} customers in emulator`);

    if (customers.length > 0) {
      customers.forEach((c) => {
        console.log(`  - ${c.name} (id: ${c.id}, workspaceId: ${c.workspaceId})`);
      });
    } else {
      console.log('❌ No customers found in emulator database!');
    }
  } catch (e) {
    console.error('Query failed:', e);
  }
}

verify();
