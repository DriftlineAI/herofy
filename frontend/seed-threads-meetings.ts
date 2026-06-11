/**
 * Additional seed script for threads and meetings
 * Run with: cd frontend && npx tsx seed-threads-meetings.ts
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  createThread,
  createMeeting,
  createInteraction,
} from '@herofy/dataconnect';

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

// IDs from main seed script
const WORKSPACE_ID = '11111111-1111-1111-1111-111111111111';
const CUSTOMER_IDS = {
  stripe: '66666666-6666-6666-6666-666666666661',
  globex: '66666666-6666-6666-6666-666666666665',
  acme: '66666666-6666-6666-6666-666666666666',
  techcorp: '66666666-6666-6666-6666-666666666668',
};

async function seed() {
  console.log('🌱 Seeding threads and meetings...\n');

  // Create threads
  console.log('Creating threads...');
  const threads = [
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.globex,
      subject: 'RE: Integration spec update?',
      channel: 'email' as const,
      threadType: 'customer' as const,
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.acme,
      subject: 'API key generation issue',
      channel: 'slack' as const,
      threadType: 'customer' as const,
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.stripe,
      subject: 'Monthly check-in notes',
      channel: 'email' as const,
      threadType: 'customer' as const,
    },
  ];

  const createdThreads: string[] = [];
  for (const t of threads) {
    try {
      const result = await createThread(t);
      createdThreads.push(result.data.thread_insert.id);
      console.log(`  ✓ Thread: ${t.subject}`);
    } catch (e: any) {
      console.log(`  Thread error:`, e.message?.substring(0, 60));
    }
  }

  // Create interactions (messages) for the first thread
  console.log('Creating interactions...');
  if (createdThreads[0]) {
    const interactions = [
      {
        workspaceId: WORKSPACE_ID,
        customerId: CUSTOMER_IDS.globex,
        threadId: createdThreads[0],
        channel: 'email' as const,
        direction: 'inbound' as const,
        senderName: 'Hank Scorpio',
        subject: 'RE: Integration spec update?',
        bodyEncrypted: 'Hi team,\n\nWe\'ve been waiting on the updated integration spec for over a week now. Our engineering team is blocked and this is becoming a serious issue.\n\nCan you please provide an update on when we can expect this?\n\nThanks,\nHank',
      },
      {
        workspaceId: WORKSPACE_ID,
        customerId: CUSTOMER_IDS.globex,
        threadId: createdThreads[0],
        channel: 'email' as const,
        direction: 'outbound' as const,
        senderName: 'Sarah Chen',
        subject: 'RE: Integration spec update?',
        bodyEncrypted: 'Hi Hank,\n\nI apologize for the delay. Our engineering team is finalizing the spec and we should have it to you by end of day tomorrow.\n\nI understand this has been frustrating and we appreciate your patience.\n\nBest,\nSarah',
      },
    ];

    for (const i of interactions) {
      try {
        await createInteraction(i);
        console.log(`  ✓ Message from ${i.senderName}`);
      } catch (e: any) {
        console.log(`  Interaction error:`, e.message?.substring(0, 60));
      }
    }
  }

  // Create meetings
  console.log('Creating meetings...');
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(14, 0, 0, 0);

  const nextWeek = new Date();
  nextWeek.setDate(nextWeek.getDate() + 7);
  nextWeek.setHours(10, 0, 0, 0);

  const meetings = [
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.stripe,
      title: 'Stripe Monthly Check-in',
      type: 'check_in',
      scheduledAt: nextWeek.toISOString(),
      durationMinutes: 30,
      attendeesOurs: JSON.stringify([{ name: 'Sarah Chen', email: 'sarah@herofy.com' }]),
      attendeesTheirs: JSON.stringify([{ name: 'Patrick Collison', email: 'patrick@stripe.com' }]),
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.globex,
      title: 'Globex Recovery Call',
      type: 'support',
      scheduledAt: tomorrow.toISOString(),
      durationMinutes: 45,
      attendeesOurs: JSON.stringify([{ name: 'Sarah Chen', email: 'sarah@herofy.com' }, { name: 'Demo User', email: 'dev@herofy.com' }]),
      attendeesTheirs: JSON.stringify([{ name: 'Hank Scorpio', email: 'hank@globex.com' }]),
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.acme,
      title: 'Acme Technical Review',
      type: 'onboarding',
      scheduledAt: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
      durationMinutes: 60,
      attendeesOurs: JSON.stringify([{ name: 'Demo User', email: 'dev@herofy.com' }]),
      attendeesTheirs: JSON.stringify([{ name: 'Wile E. Coyote', email: 'wile@acme-corp.com' }]),
    },
  ];

  for (const m of meetings) {
    try {
      await createMeeting(m);
      console.log(`  ✓ Meeting: ${m.title}`);
    } catch (e: any) {
      console.log(`  Meeting error:`, e.message?.substring(0, 60));
    }
  }

  console.log('\n✅ Additional seed complete!');
}

seed().catch(console.error);
