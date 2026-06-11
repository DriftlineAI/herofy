#!/usr/bin/env npx tsx
/**
 * Robust Demo Seeding Script
 *
 * This script seeds demo data with the goal of exercising real code paths
 * rather than just stuffing fake data into the database.
 *
 * Usage:
 *   npx tsx seed-demo.ts              # Run all phases
 *   npx tsx seed-demo.ts --clean      # Clean then run all phases
 *   npx tsx seed-demo.ts --phase setup   # Just run setup phase
 *   npx tsx seed-demo.ts --phase handoff # Just run handoff phase
 *   npx tsx seed-demo.ts --phase signals # Just run signals phase
 *
 * Phases:
 * 1. Setup: Create workspace, users, playbooks, customers
 * 2. Handoff: Trigger handoff agents or seed briefs/plans
 * 3. Signals: Inject emails/slack to trigger signal processing
 *
 * Architecture:
 * - Fake the INPUTS (external data like emails, Notion pages)
 * - Run REAL agents and mutations where possible
 * - Fall back to direct seeding when agents aren't available
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  createWorkspaceWithId,
  createUserWithId,
  createCustomerWithId,
  createStakeholderPublic,
  createNeedWithId,
  createGoalPublic,
  createHandbookDocWithId,
  createHandbookVersionWithId,
  addWorkspaceMemberPublic,
  createPlaybookWithId,
  createPlaybookMilestoneWithId,
  deleteAllCustomersForWorkspacePublic,
  createHandoffBrief,
  // Enum types
  BlastRadius,
  WorkspaceRole,
  OwnerSide,
  CustomerLifecycle,
  HandoffStatus,
  NeedType,
} from '@herofy/dataconnect';

// Parse command line arguments
const args = process.argv.slice(2);
const cleanFlag = args.includes('--clean');
const phaseIndex = args.indexOf('--phase');
const selectedPhase = phaseIndex >= 0 ? args[phaseIndex + 1] : 'all';

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

// Python backend URL
const PYTHON_URL = process.env.PYTHON_URL || 'http://localhost:8081';

// =============================================================================
// CONSTANTS
// =============================================================================

// Use a fixed workspace ID for seeding
const WORKSPACE_ID = '00000000-0000-0000-0000-000000000001';

const USER_IDS = {
  marcus: 'marcus-lee-004',
  priya: 'priya-shah-004',
  devon: 'devon-patel-004',
  scott: 'rk07bQuUP7PbwFInqX0QWI23jKE3',
};

const HANDBOOK_DOC_ID = '33333333333333333333333333333334';
const HANDBOOK_VERSION_ID = '44444444444444444444444444444444';

const PLAYBOOK_IDS = {
  standard: 'bbbb22222222222222222222222221',
  enterprise: 'bbbb22222222222222222222222222',
  selfServe: 'bbbb22222222222222222222222223',
};

const CUSTOMER_IDS = {
  marlin: 'aaaa11111111111111111111111111d1',
  pinegrove: 'aaaa11111111111111111111111111d2',
  foldwise: 'aaaa11111111111111111111111111d3',
  bevelpoint: 'aaaa11111111111111111111111111d4',
  aperio: 'aaaa11111111111111111111111111d5',
  quietfield: 'aaaa11111111111111111111111111d6',
  bridgenote: 'aaaa11111111111111111111111111d7',
};

// =============================================================================
// DEMO CUSTOMERS (from DEMO_SCENARIO.md)
// =============================================================================

const DEMO_CUSTOMERS = [
  {
    id: CUSTOMER_IDS.marlin,
    name: 'Marlin Insights',
    slug: 'marlin-insights',
    domain: 'marlininsights.com',
    oneLiner: 'Series A product analytics for ecommerce',
    tier: 'Mid-Market',
    arrCents: 1800000, // $18k/year
    lifecycle: CustomerLifecycle.handoff,  // New handoff target
    onboardingDayCurrent: 0,
    onboardingDayTotal: 60,
    daysToRenewal: 360,
    dealNotes: `Use case: syncing HubSpot opportunity data into Snowflake and triggering Outreach sequences.
Evaluated: us vs Workato vs building in-house with Hightouch.
Why Northcrest: price point, no-code interface, promised Outreach connector (2 weeks).
Sarah's preferences: async, Slack > email, hates standing meetings.
Success criteria: 3 workflows in production in 60 days.
Watch: CEO is skeptical about integration tools — first impressions matter.`,
  },
  {
    id: CUSTOMER_IDS.pinegrove,
    name: 'Pinegrove HR',
    slug: 'pinegrove',
    domain: 'pinegrove.io',
    oneLiner: 'HR/payroll SaaS, healthy and expanding',
    tier: 'Growth',
    arrCents: 3200000, // $32k/year
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 210,
  },
  {
    id: CUSTOMER_IDS.foldwise,
    name: 'Foldwise',
    slug: 'foldwise',
    domain: 'foldwise.com',
    oneLiner: 'Contract lifecycle management, at-risk',
    tier: 'Growth',
    arrCents: 3600000, // $36k/year
    lifecycle: CustomerLifecycle.at_risk,  // Signal target
    daysToRenewal: 120,
  },
  {
    id: CUSTOMER_IDS.bevelpoint,
    name: 'Bevelpoint Logistics',
    slug: 'bevelpoint',
    domain: 'bevelpoint.com',
    oneLiner: 'Freight brokerage workflow, renewal approaching',
    tier: 'Mid-Market',
    arrCents: 2400000, // $24k/year
    lifecycle: CustomerLifecycle.renewing,
    daysToRenewal: 75,
  },
  {
    id: CUSTOMER_IDS.aperio,
    name: 'Aperio Analytics',
    slug: 'aperio',
    domain: 'aperioanalytics.com',
    oneLiner: 'Product analytics SaaS, active escalation',
    tier: 'Growth',
    arrCents: 3000000, // $30k/year
    lifecycle: CustomerLifecycle.at_risk,  // Cross-channel escalation
    daysToRenewal: 180,
  },
  {
    id: CUSTOMER_IDS.quietfield,
    name: 'Quietfield Software',
    slug: 'quietfield',
    domain: 'quietfield.com',
    oneLiner: 'DevOps platform, going dark',
    tier: 'Mid-Market',
    arrCents: 2000000, // $20k/year
    lifecycle: CustomerLifecycle.active,  // Going dark signal
    daysToRenewal: 180,
  },
  {
    id: CUSTOMER_IDS.bridgenote,
    name: 'Bridgenote',
    slug: 'bridgenote',
    domain: 'bridgenote.com',
    oneLiner: 'Revenue intelligence platform, expansion opportunity',
    tier: 'Growth',
    arrCents: 2600000, // $26k/year
    lifecycle: CustomerLifecycle.active,  // Expansion opportunity
    daysToRenewal: 240,
  },
];

// =============================================================================
// DEMO EMAILS TO INJECT (triggers SignalWatcher)
// =============================================================================

const DEMO_EMAILS = [
  // Aperio escalation thread
  {
    from: 'liam@aperioa.io',
    to: 'marcus@northcrest.io',
    subject: 'Two workflows went silent',
    body: `Marcus — we just noticed two of our production workflows haven't fired in 36 hours. The intent-signal-to-Outreach and the renewal-flag-to-Slack workflows. Both critical. What happened?`,
    customerSlug: 'aperio',
  },
  {
    from: 'liam@aperioa.io',
    to: 'marcus@northcrest.io',
    subject: 'Re: Confirming commitments',
    body: `Following up on Friday's call. Confirming the three commitments: postmortem doc by EOD Wednesday, webhook signature policy by next Friday, service credit on renewal. Nina is going to ask me about status next Monday — I need to give her real answers.`,
    customerSlug: 'aperio',
  },
  // Foldwise frustration
  {
    from: 'david@foldwise.com',
    to: 'marcus@northcrest.io',
    subject: 'Reliability concerns',
    body: `Marcus, the second rate-limit incident in 6 weeks. This took way longer to resolve than it should have. I'm starting to wonder if we made the right choice here. I've been looking at what Tray and Workato offer.`,
    customerSlug: 'foldwise',
  },
  // Bridgenote expansion opportunity
  {
    from: 'kavya@bridgenote.com',
    to: 'marcus@northcrest.io',
    subject: 'Gong connector question',
    body: `Hi Marcus, quick question - can Northcrest trigger workflows from Gong call data? We want to auto-create tasks in HubSpot when sales calls mention competitor names. Also, we just hired 2 more RevOps people — might need more seats.`,
    customerSlug: 'bridgenote',
  },
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function tryCreateWithLog(
  name: string,
  createFn: () => Promise<any>,
): Promise<boolean> {
  try {
    await createFn();
    console.log(`  ✓ ${name}`);
    return true;
  } catch (e: any) {
    if (e.message?.includes('already exists') || e.message?.includes('duplicate')) {
      console.log(`  · ${name} (already exists)`);
      return true;
    }
    console.log(`  ✗ ${name}: ${e.message?.substring(0, 50)}`);
    return false;
  }
}

async function triggerAgent(endpoint: string, body: Record<string, any>): Promise<any> {
  try {
    const response = await fetch(`${PYTHON_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Agent call failed: ${error}`);
    }

    return await response.json();
  } catch (e: any) {
    if (e.message?.includes('ECONNREFUSED')) {
      return { error: 'Backend not running' };
    }
    throw e;
  }
}

// =============================================================================
// PHASE 0: CLEAN
// =============================================================================

async function runClean() {
  console.log('\n🧹 Phase 0: Cleaning database...');

  try {
    await deleteAllCustomersForWorkspacePublic({ workspaceId: WORKSPACE_ID });
    console.log('  ✓ Customers cleared');
  } catch (e: any) {
    console.log(`  · Customers: ${e.message?.substring(0, 50)}`);
  }

  console.log('  Note: Workspace, users, and playbooks preserved for faster iteration');
}

// =============================================================================
// PHASE 1: SETUP
// =============================================================================

async function runSetup() {
  console.log('\n📦 Phase 1: Setup simulation...');

  // 1.1 Create handbook (needed for AI audit trail)
  console.log('\n Creating handbook...');
  await tryCreateWithLog('Handbook doc', () =>
    createHandbookDocWithId({
      id: HANDBOOK_DOC_ID,
      workspaceId: WORKSPACE_ID,
      slug: 'onboarding-guide',
      title: 'Customer Onboarding Guide',
      description: 'Standard procedures for customer onboarding',
      body: `# Customer Onboarding Guide

## Key Principles
1. Early Value Delivery: Get customers to their first "aha moment" within the first week
2. Clear Communication: Set expectations early, communicate proactively
3. Technical Excellence: Ensure smooth technical setup before moving forward
4. Human Touch: AI assists, but humans own the relationship

## Risk Signals During Onboarding
- No response for 3+ business days
- Missed kickoff call
- Technical blockers lasting >2 days
- Stakeholder changes mid-onboarding
- Scope creep on requirements`,
      blastRadius: BlastRadius.high,
    })
  );

  await tryCreateWithLog('Handbook version', () =>
    createHandbookVersionWithId({
      id: HANDBOOK_VERSION_ID,
      docId: HANDBOOK_DOC_ID,
      body: `# Customer Onboarding Guide v1.0`,
    })
  );

  // 1.2 Create workspace
  console.log('\n Creating workspace...');
  await tryCreateWithLog('Northcrest workspace (setupCompleted=true)', () =>
    createWorkspaceWithId({
      id: WORKSPACE_ID,
      name: 'Northcrest',
      slug: 'northcrest',
      domain: 'northcrest.io',
      valueProp: 'B2B SaaS workflow automation platform for operations and RevOps teams.',
      setupCompleted: true, // Mark setup as complete for seeded workspace
    })
  );

  // 1.3 Create users
  console.log('\n Creating team members...');
  const users = [
    { id: USER_IDS.marcus, email: 'marcus@northcrest.io', displayName: 'Marcus Lee' },
    { id: USER_IDS.priya, email: 'priya@northcrest.io', displayName: 'Priya Shah' },
    { id: USER_IDS.devon, email: 'devon@northcrest.io', displayName: 'Devon Patel' },
    { id: USER_IDS.scott, email: 'scott@driftline.ai', displayName: 'Scott' },
  ];

  for (const user of users) {
    await tryCreateWithLog(user.displayName, () => createUserWithId(user));
    await tryCreateWithLog(`${user.displayName} membership (hasCompletedSetup=true)`, () =>
      addWorkspaceMemberPublic({
        workspaceId: WORKSPACE_ID,
        userId: user.id,
        role: WorkspaceRole.owner,
        hasCompletedSetup: true, // Mark setup as complete for seeded users
      })
    );
  }

  // 1.4 Create playbooks (CRITICAL for agents to work)
  console.log('\n Creating playbooks...');

  // Standard Onboarding
  await tryCreateWithLog('Standard Onboarding playbook', () =>
    createPlaybookWithId({
      id: PLAYBOOK_IDS.standard,
      workspaceId: WORKSPACE_ID,
      name: 'Standard Onboarding',
      archetype: 'mid-market',
      fitNote: 'Best for customers with $25K-$100K ARR. Typical timeline: 30-45 days.',
    })
  );

  const standardMilestones = [
    { id: 'cccc55555555555555555555555501', title: 'Kickoff Call', ownerSide: OwnerSide.us, durationDays: 3, sortOrder: 1 },
    { id: 'cccc55555555555555555555555502', title: 'Technical Setup', ownerSide: OwnerSide.customer, durationDays: 7, sortOrder: 2 },
    { id: 'cccc55555555555555555555555503', title: 'Integration Configuration', ownerSide: OwnerSide.joint, durationDays: 7, sortOrder: 3 },
    { id: 'cccc55555555555555555555555504', title: 'Data Migration', ownerSide: OwnerSide.joint, durationDays: 5, sortOrder: 4 },
    { id: 'cccc55555555555555555555555505', title: 'User Training', ownerSide: OwnerSide.us, durationDays: 5, sortOrder: 5 },
    { id: 'cccc55555555555555555555555506', title: 'Go-Live', ownerSide: OwnerSide.joint, durationDays: 3, sortOrder: 6 },
    { id: 'cccc55555555555555555555555507', title: 'Post-Launch Review', ownerSide: OwnerSide.us, durationDays: 7, sortOrder: 7 },
  ];

  for (const m of standardMilestones) {
    await tryCreateWithLog(`  ${m.title}`, () =>
      createPlaybookMilestoneWithId({ ...m, playbookId: PLAYBOOK_IDS.standard, description: '' })
    );
  }

  // Enterprise Onboarding
  await tryCreateWithLog('Enterprise Onboarding playbook', () =>
    createPlaybookWithId({
      id: PLAYBOOK_IDS.enterprise,
      workspaceId: WORKSPACE_ID,
      name: 'Enterprise Onboarding',
      archetype: 'enterprise',
      fitNote: 'For customers with $100K+ ARR. Extended timeline: 60-90 days.',
    })
  );

  // Self-Serve
  await tryCreateWithLog('Self-Serve Quick Start playbook', () =>
    createPlaybookWithId({
      id: PLAYBOOK_IDS.selfServe,
      workspaceId: WORKSPACE_ID,
      name: 'Self-Serve Quick Start',
      archetype: 'self-serve',
      fitNote: 'For PLG customers under $25K ARR.',
    })
  );

  // 1.5 Create customers
  console.log('\n Creating customers...');
  for (const customer of DEMO_CUSTOMERS) {
    await tryCreateWithLog(customer.name, () =>
      createCustomerWithId({
        id: customer.id,
        workspaceId: WORKSPACE_ID,
        name: customer.name,
        slug: customer.slug,
        domain: customer.domain,
        oneLiner: customer.oneLiner,
        tier: customer.tier,
        arrCents: customer.arrCents?.toString(),
        lifecycle: customer.lifecycle,
        onboardingDayCurrent: customer.onboardingDayCurrent || 0,
        onboardingDayTotal: customer.onboardingDayTotal || 30,
        daysToRenewal: customer.daysToRenewal || 365,
      })
    );
  }

  // 1.6 Create stakeholders
  console.log('\n Creating stakeholders...');
  const stakeholders = [
    { customerId: CUSTOMER_IDS.marlin, name: 'Sarah Chen', role: 'Head of RevOps', email: 'sarah@marlininsights.com' },
    { customerId: CUSTOMER_IDS.pinegrove, name: 'Maya Brooks', role: 'Director of Operations', email: 'maya@pinegrovehr.com' },
    { customerId: CUSTOMER_IDS.foldwise, name: 'David Okonkwo', role: 'Head of RevOps', email: 'david@foldwise.com' },
    { customerId: CUSTOMER_IDS.bevelpoint, name: 'Reggie Vance', role: 'COO', email: 'reggie@bevelpoint.com' },
    { customerId: CUSTOMER_IDS.aperio, name: 'Liam Carter', role: 'VP Engineering', email: 'liam@aperioa.io' },
    { customerId: CUSTOMER_IDS.aperio, name: 'Nina Torres', role: 'CEO', email: 'nina@aperioa.io' },
    { customerId: CUSTOMER_IDS.quietfield, name: 'Hana Müller', role: 'Director of Engineering Ops', email: 'hana@quietfield.com' },
    { customerId: CUSTOMER_IDS.bridgenote, name: 'Kavya Reddy', role: 'RevOps Manager', email: 'kavya@bridgenote.com' },
  ];

  for (const s of stakeholders) {
    await tryCreateWithLog(`${s.name} (${s.role})`, () =>
      createStakeholderPublic({
        workspaceId: WORKSPACE_ID,
        customerId: s.customerId,
        name: s.name,
        role: s.role,
        email: s.email,
      })
    );
  }

  console.log('\n✅ Setup complete!');
}

// =============================================================================
// PHASE 2: HANDOFF AGENTS
// =============================================================================

async function runHandoff() {
  console.log('\n🤖 Phase 2: Triggering handoff agents...');

  // Find handoff customers
  const handoffCustomers = DEMO_CUSTOMERS.filter(c => c.lifecycle === 'handoff');

  for (const customer of handoffCustomers) {
    console.log(`\n Processing ${customer.name}...`);

    // Try to trigger the real handoff agent
    const result = await triggerAgent('/agents/handoff-auto/run', {
      workspace_id: WORKSPACE_ID,
      customer_id: customer.id,
      deal_notes: customer.dealNotes || '',
    });

    if (result.error === 'Backend not running') {
      console.log('  ⚠ Backend not running, seeding brief only (plans handled separately)...');

      // Fallback: seed brief directly (plans are now handled via new plan system)
      await tryCreateWithLog('Handoff brief', () =>
        createHandoffBrief({
          workspaceId: WORKSPACE_ID,
          customerId: customer.id,
          status: HandoffStatus.draft,
          salesCommitments: JSON.stringify([
            { text: '30-day implementation timeline' },
            { text: 'Outreach connector promised in 2 weeks' },
          ]),
          technicalContext: JSON.stringify([
            { text: 'HubSpot to Snowflake sync' },
            { text: 'Outreach sequence triggers' },
          ]),
          realityCheckConfidence: 'medium',
          realityCheckRisks: 'CEO is skeptical about integration tools — first impressions matter.',
          handbookVersionId: HANDBOOK_VERSION_ID,
          dayCurrent: 1,
          dayTotal: 60,
        })
      );
    } else if (result.error) {
      console.log(`  ✗ Agent error: ${result.error}`);
    } else {
      console.log(`  ✓ Agent triggered: ${result.run_id || 'success'}`);
      await sleep(2000); // Let agent complete
    }
  }

  console.log('\n✅ Handoff phase complete!');
}

// =============================================================================
// PHASE 3: SIGNAL WATCHER
// =============================================================================

async function runSignals() {
  console.log('\n📧 Phase 3: Injecting signals...');

  // Try to inject emails via webhook (if backend is running)
  for (const email of DEMO_EMAILS) {
    console.log(`\n Injecting email: "${email.subject}"...`);

    const customer = DEMO_CUSTOMERS.find(c => c.slug === email.customerSlug);
    if (!customer) {
      console.log(`  ⚠ Customer not found: ${email.customerSlug}`);
      continue;
    }

    // Try webhook injection
    const result = await triggerAgent('/webhooks/gmail', {
      from: email.from,
      to: email.to,
      subject: email.subject,
      body: email.body,
      // Include customer context for demo
      customer_id: customer.id,
    });

    if (result.error === 'Backend not running') {
      console.log('  ⚠ Backend not running, seeding need directly...');

      // Determine need type from content
      let needType = NeedType.escalation;
      let headline = '';

      if (email.body.includes('frustrated') || email.body.includes('wrong choice')) {
        needType = NeedType.frustrated_signal;
        headline = 'Customer expressing frustration';
      } else if (email.body.includes('expansion') || email.body.includes('more seats')) {
        needType = NeedType.expansion_signal;
        headline = 'Expansion opportunity detected';
      } else if (email.body.includes('commitments') || email.body.includes('workflows')) {
        needType = NeedType.escalation;
        headline = 'Customer following up on commitments';
      }

      const needId = `need-signal-${Date.now()}`;
      await tryCreateWithLog(`Need: ${headline}`, () =>
        createNeedWithId({
          id: needId,
          workspaceId: WORKSPACE_ID,
          customerId: customer.id,
          type: needType,
          headline: headline,
          lede: email.subject,
          priorityRank: 3,
          agentReasoning: `Signal detected from email: ${email.subject}`,
        })
      );
    } else if (result.error) {
      console.log(`  ✗ Webhook error: ${result.error}`);
    } else {
      console.log(`  ✓ Webhook processed`);
    }
  }

  console.log('\n✅ Signals phase complete!');
}

// =============================================================================
// PHASE 4: VERIFICATION
// =============================================================================

async function runVerify() {
  console.log('\n✅ Phase 4: Verification...');

  // Just log what we expect to see
  console.log('\n Expected state:');
  console.log('  - Workspace: Northcrest');
  console.log('  - Users: Marcus, Priya, Devon, Scott');
  console.log('  - Playbooks: Standard, Enterprise, Self-Serve');
  console.log('  - Customers: 7 (Marlin, Pinegrove, Foldwise, Bevelpoint, Aperio, Quietfield, Bridgenote)');
  console.log('  - Handoff customers with briefs/plans: Marlin');
  console.log('  - Signals/needs from emails: Aperio, Foldwise, Bridgenote');

  console.log('\n Next steps:');
  console.log('  1. Start the frontend: npm run dev:frontend');
  console.log('  2. Navigate to Today Queue to see needs');
  console.log('  3. Click on Marlin to see the Brief tab');
  console.log('  4. Check Sidekick page for any agent questions');
}

// =============================================================================
// MAIN
// =============================================================================

async function main() {
  console.log('🌱 Herofy Demo Seeding Script');
  console.log(`   Workspace: ${WORKSPACE_ID}`);
  console.log(`   Phase: ${selectedPhase}`);
  console.log(`   Clean: ${cleanFlag}`);

  try {
    // Phase 0: Clean (if requested)
    if (cleanFlag) {
      await runClean();
    }

    // Phase 1: Setup
    if (selectedPhase === 'all' || selectedPhase === 'setup') {
      await runSetup();
    }

    // Phase 2: Handoff
    if (selectedPhase === 'all' || selectedPhase === 'handoff') {
      await runHandoff();
    }

    // Phase 3: Signals
    if (selectedPhase === 'all' || selectedPhase === 'signals') {
      await runSignals();
    }

    // Phase 4: Verify
    if (selectedPhase === 'all') {
      await runVerify();
    }

    console.log('\n🎉 Demo seeding complete!');
  } catch (e: any) {
    console.error('\n❌ Seeding failed:', e.message);
    process.exit(1);
  }
}

main();
