#!/usr/bin/env npx tsx
import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import { getCustomers } from '@herofy/dataconnect';

const app = initializeApp({ projectId: 'herofy-496505' });
const dc = getDataConnect(app, { connector: 'herofy', location: 'us-central1', service: 'herofy-prod-service' });
connectDataConnectEmulator(dc, 'localhost', 9399);

async function check() {
  try {
    // Check customers in the seeded workspace
    const customers = await getCustomers(dc, { workspaceId: '360f25d26f4f4df8aeedb8e4607e1103' });
    console.log(`Customers in 360f25d26f4f4df8aeedb8e4607e1103: ${customers.data.customers?.length || 0}`);
    if (customers.data.customers?.length) {
      console.log('Customer names:', customers.data.customers.map(c => c.name).join(', '));
    }
  } catch (e: any) {
    console.error('Error:', e.message);
  }
}

check();
