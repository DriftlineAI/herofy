/**
 * Seed script for Firebase SQL Connect emulator
 * Based on DEMO_SCENARIO.md - Northcrest customers
 * Run with: cd frontend && npx tsx seed-data.ts
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  createWorkspaceWithId,
  createUserWithId,
  createCustomerWithId,
  createStakeholderPublic,
  createNeedWithId,
  createSignal,
  createMilestonePublic,
  createGoalPublic,
  createHandbookDocWithId,
  createHandbookVersionWithId,
  addWorkspaceMemberPublic,
  createWaitingAgentRunForTest,
  createSidekickItem,
  createPlaybookWithId,
  createPlaybookMilestoneWithId,
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
console.log('🔍 DataConnect configured for emulator: localhost:9399');
console.log('🔍 Testing connection...\n');

// IDs for referential integrity (v4 - fresh IDs)
const WORKSPACE_ID = '627b9eaea88649debffde520d1a79c18'; // Scott's workspace
const USER_MARCUS_ID = 'marcus-lee-004';
const USER_PRIYA_ID = 'priya-shah-004';
const USER_DEVON_ID = 'devon-patel-004';
const USER_SCOTT_ID = 'rk07bQuUP7PbwFInqX0QWI23jKE3'; // Scott from Firebase Auth

const HANDBOOK_DOC_ID = '33333333333333333333333333333334';
const HANDBOOK_VERSION_ID = '44444444444444444444444444444444';

// Customer IDs for Northcrest's 7 customers (from DEMO_SCENARIO.md) - v4
const CUSTOMER_IDS = {
  marlin: 'aaaa11111111111111111111111111d1',
  pinegrove: 'aaaa11111111111111111111111111d2',
  foldwise: 'aaaa11111111111111111111111111d3',
  bevelpoint: 'aaaa11111111111111111111111111d4',
  aperio: 'aaaa11111111111111111111111111d5',
  quietfield: 'aaaa11111111111111111111111111d6',
  bridgenote: 'aaaa11111111111111111111111111d7',
};

// Playbook IDs - must use same workspace as customers for agents to find them
const PLAYBOOK_IDS = {
  standard: 'bbbb22222222222222222222222221',
  enterprise: 'bbbb22222222222222222222222222',
  selfServe: 'bbbb22222222222222222222222223',
};

async function seed() {
  console.log('🌱 Seeding Northcrest demo data...\n');

  // 1. Create handbook doc and version first (needed for foreign keys)
  console.log('Creating handbook doc and version...');
  try {
    await createHandbookDocWithId({
      id: HANDBOOK_DOC_ID,
      workspaceId: WORKSPACE_ID,
      slug: 'going-dark',
      title: 'How We Define Going Dark',
      description: 'Criteria for identifying customers who have gone silent',
      body: '# Going Dark Definition\n\nA customer is "going dark" when:\n\n1. No response to 2+ outreach attempts over 7 days\n2. No product usage in 14 days\n3. No scheduled meetings on calendar',
      blastRadius: 'medium',
    });
    console.log('  ✓ Handbook doc created');
  } catch (e: any) {
    console.log('  Handbook doc may already exist:', e.message?.substring(0, 50));
  }

  try {
    await createHandbookVersionWithId({
      id: HANDBOOK_VERSION_ID,
      docId: HANDBOOK_DOC_ID,
      body: '# Going Dark Definition\n\nA customer is "going dark" when:\n\n1. No response to 2+ outreach attempts over 7 days\n2. No product usage in 14 days\n3. No scheduled meetings on calendar',
    });
    console.log('  ✓ Handbook version created');
  } catch (e: any) {
    console.log('  Handbook version may already exist:', e.message?.substring(0, 50));
  }

  // 2. Create workspace (Northcrest)
  console.log('\nCreating workspace...');
  try {
    await createWorkspaceWithId({
      id: WORKSPACE_ID,
      name: 'Northcrest',
      slug: 'northcrest',
      domain: 'northcrest.io',
      valueProp: 'B2B SaaS workflow automation platform for operations and RevOps teams. We help companies streamline data pipelines, automate handoffs between sales and CS, and provide real-time visibility into customer health metrics.',
      setupCompleted: true, // Mark setup as complete for seeded workspace
    });
    console.log('  ✓ Northcrest workspace created (setupCompleted=true)');
  } catch (e: any) {
    console.log('  Workspace error:', e.message);
    console.log('  Full error:', JSON.stringify(e, null, 2));
  }

  // 3. Create users (Northcrest team + Scott)
  console.log('\nCreating Northcrest team members...');
  const users = [
    { id: USER_MARCUS_ID, email: 'marcus@northcrest.io', displayName: 'Marcus Lee' },
    { id: USER_PRIYA_ID, email: 'priya@northcrest.io', displayName: 'Priya Shah' },
    { id: USER_DEVON_ID, email: 'devon@northcrest.io', displayName: 'Devon Patel' },
    { id: USER_SCOTT_ID, email: 'scott@driftline.ai', displayName: 'Scott' },
  ];

  for (const user of users) {
    try {
      await createUserWithId(user);
      console.log(`  ✓ ${user.displayName}`);
    } catch (e: any) {
      console.log(`  ${user.displayName} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // 3b. Add users as workspace members
  console.log('\nAdding users to workspace...');
  for (const user of users) {
    try {
      await addWorkspaceMemberPublic({
        workspaceId: WORKSPACE_ID,
        userId: user.id,
        role: 'owner',
        hasCompletedSetup: true, // Mark setup as complete for seeded users
      });
      console.log(`  ✓ ${user.displayName} added as workspace member (hasCompletedSetup=true)`);
    } catch (e: any) {
      console.log(`  ${user.displayName} membership error:`, e.message?.substring(0, 50));
    }
  }

  // 3c. Create playbooks (CRITICAL: must be in same workspace for agents to find them)
  console.log('\nCreating playbooks...');

  // Standard Onboarding Playbook
  try {
    await createPlaybookWithId({
      id: PLAYBOOK_IDS.standard,
      workspaceId: WORKSPACE_ID,
      name: 'Standard Onboarding',
      archetype: 'mid-market',
      fitNote: 'Best for customers with $25K-$100K ARR. Typical timeline: 30-45 days.',
    });
    console.log('  ✓ Standard Onboarding playbook created');
  } catch (e: any) {
    console.log('  Standard playbook may already exist:', e.message?.substring(0, 50));
  }

  const standardMilestones = [
    {
      id: 'cccc55555555555555555555555501',
      title: 'Kickoff Call',
      ownerSide: 'us' as const,
      durationDays: 3,
      description: 'Align on goals, timeline, and success criteria. Identify stakeholders and communication preferences.',
      sortOrder: 1,
    },
    {
      id: 'cccc55555555555555555555555502',
      title: 'Technical Setup',
      ownerSide: 'customer' as const,
      durationDays: 7,
      description: 'API keys, SSO configuration, environment setup. Provide documentation and support as needed.',
      sortOrder: 2,
    },
    {
      id: 'cccc55555555555555555555555503',
      title: 'Integration Configuration',
      ownerSide: 'joint' as const,
      durationDays: 7,
      description: 'Configure integrations, connect data sources, validate data flow.',
      sortOrder: 3,
    },
    {
      id: 'cccc55555555555555555555555504',
      title: 'Data Migration',
      ownerSide: 'joint' as const,
      durationDays: 5,
      description: 'Import historical data, validate integrity, run reconciliation checks.',
      sortOrder: 4,
    },
    {
      id: 'cccc55555555555555555555555505',
      title: 'User Training',
      ownerSide: 'us' as const,
      durationDays: 5,
      description: 'Train end users and admins. Provide documentation and quick-reference guides.',
      sortOrder: 5,
    },
    {
      id: 'cccc55555555555555555555555506',
      title: 'Go-Live',
      ownerSide: 'joint' as const,
      durationDays: 3,
      description: 'Launch in production. Monitor closely, address any issues immediately.',
      sortOrder: 6,
    },
    {
      id: 'cccc55555555555555555555555507',
      title: 'Post-Launch Review',
      ownerSide: 'us' as const,
      durationDays: 7,
      description: 'Review metrics, gather feedback, document lessons learned. Transition to ongoing support.',
      sortOrder: 7,
    },
  ];

  for (const m of standardMilestones) {
    try {
      await createPlaybookMilestoneWithId({
        ...m,
        playbookId: PLAYBOOK_IDS.standard,
      });
      console.log(`    ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`    ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // Enterprise Onboarding Playbook
  try {
    await createPlaybookWithId({
      id: PLAYBOOK_IDS.enterprise,
      workspaceId: WORKSPACE_ID,
      name: 'Enterprise Onboarding',
      archetype: 'enterprise',
      fitNote: 'For customers with $100K+ ARR. Extended timeline: 60-90 days. Includes executive alignment.',
    });
    console.log('  ✓ Enterprise Onboarding playbook created');
  } catch (e: any) {
    console.log('  Enterprise playbook may already exist:', e.message?.substring(0, 50));
  }

  const enterpriseMilestones = [
    {
      id: 'cccc55555555555555555555555601',
      title: 'Executive Alignment',
      ownerSide: 'us' as const,
      durationDays: 5,
      description: 'Meet with executive sponsors to align on strategic goals and success metrics.',
      sortOrder: 1,
    },
    {
      id: 'cccc55555555555555555555555602',
      title: 'Discovery & Planning',
      ownerSide: 'joint' as const,
      durationDays: 10,
      description: 'Detailed requirements gathering, technical architecture review, project planning.',
      sortOrder: 2,
    },
    {
      id: 'cccc55555555555555555555555603',
      title: 'Security Review',
      ownerSide: 'customer' as const,
      durationDays: 14,
      description: 'Complete security questionnaire, SOC2 review, vendor assessment.',
      sortOrder: 3,
    },
    {
      id: 'cccc55555555555555555555555604',
      title: 'Technical Setup & Integration',
      ownerSide: 'joint' as const,
      durationDays: 14,
      description: 'Enterprise SSO, custom integrations, staging environment setup.',
      sortOrder: 4,
    },
    {
      id: 'cccc55555555555555555555555605',
      title: 'Pilot Deployment',
      ownerSide: 'joint' as const,
      durationDays: 14,
      description: 'Limited rollout to pilot team, gather feedback, iterate.',
      sortOrder: 5,
    },
    {
      id: 'cccc55555555555555555555555606',
      title: 'Full Rollout',
      ownerSide: 'joint' as const,
      durationDays: 10,
      description: 'Company-wide deployment, training sessions, change management support.',
      sortOrder: 6,
    },
    {
      id: 'cccc55555555555555555555555607',
      title: 'Business Review',
      ownerSide: 'us' as const,
      durationDays: 7,
      description: 'Executive business review, ROI analysis, success metrics review.',
      sortOrder: 7,
    },
  ];

  for (const m of enterpriseMilestones) {
    try {
      await createPlaybookMilestoneWithId({
        ...m,
        playbookId: PLAYBOOK_IDS.enterprise,
      });
      console.log(`    ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`    ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // Self-Serve Quick Start Playbook
  try {
    await createPlaybookWithId({
      id: PLAYBOOK_IDS.selfServe,
      workspaceId: WORKSPACE_ID,
      name: 'Self-Serve Quick Start',
      archetype: 'self-serve',
      fitNote: 'For PLG customers under $25K ARR. Automated onboarding with light-touch check-ins.',
    });
    console.log('  ✓ Self-Serve Quick Start playbook created');
  } catch (e: any) {
    console.log('  Self-Serve playbook may already exist:', e.message?.substring(0, 50));
  }

  const selfServeMilestones = [
    {
      id: 'cccc55555555555555555555555701',
      title: 'Welcome & Setup',
      ownerSide: 'customer' as const,
      durationDays: 3,
      description: 'Self-service account setup, initial configuration via wizard.',
      sortOrder: 1,
    },
    {
      id: 'cccc55555555555555555555555702',
      title: 'First Value',
      ownerSide: 'customer' as const,
      durationDays: 7,
      description: 'Complete first use case, see initial value from the product.',
      sortOrder: 2,
    },
    {
      id: 'cccc55555555555555555555555703',
      title: 'Check-in Call',
      ownerSide: 'us' as const,
      durationDays: 3,
      description: 'Optional 30-min call to answer questions and ensure success.',
      sortOrder: 3,
    },
    {
      id: 'cccc55555555555555555555555704',
      title: 'Expansion Ready',
      ownerSide: 'joint' as const,
      durationDays: 7,
      description: 'Review usage, identify expansion opportunities, upgrade path.',
      sortOrder: 4,
    },
  ];

  for (const m of selfServeMilestones) {
    try {
      await createPlaybookMilestoneWithId({
        ...m,
        playbookId: PLAYBOOK_IDS.selfServe,
      });
      console.log(`    ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`    ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // 4. Create customers (Northcrest's 7 customers from DEMO_SCENARIO.md)
  console.log('\nCreating Northcrest customers...');
  const customers = [
    {
      id: CUSTOMER_IDS.marlin,
      name: 'Marlin Insights',
      slug: 'marlin-insights',
      domain: 'marlininsights.com',
      oneLiner: 'Series A product analytics for ecommerce',
      tier: 'Mid-Market',
      arrCents: 1800000, // $18k/year
      lifecycle: 'onboarding' as const,
      onboardingDayCurrent: 5,
      onboardingDayTotal: 60,
      daysToRenewal: 360,
    },
    {
      id: CUSTOMER_IDS.pinegrove,
      name: 'Pinegrove HR',
      slug: 'pinegrove',
      domain: 'pinegrove.io',
      oneLiner: 'HR/payroll SaaS, healthy and expanding',
      tier: 'Growth',
      arrCents: 3200000, // $32k/year
      lifecycle: 'active' as const,
      daysToRenewal: 210,
      renewalReadiness: 'ready' as const,
    },
    {
      id: CUSTOMER_IDS.foldwise,
      name: 'Foldwise',
      slug: 'foldwise',
      domain: 'foldwise.com',
      oneLiner: 'Contract lifecycle management, at-risk',
      tier: 'Growth',
      arrCents: 3600000, // $36k/year
      lifecycle: 'at_risk' as const,
      daysToRenewal: 120,
      renewalReadiness: 'at_risk' as const,
    },
    {
      id: CUSTOMER_IDS.bevelpoint,
      name: 'Bevelpoint Logistics',
      slug: 'bevelpoint',
      domain: 'bevelpoint.com',
      oneLiner: 'Freight brokerage workflow, renewal approaching',
      tier: 'Mid-Market',
      arrCents: 2400000, // $24k/year
      lifecycle: 'renewing' as const,
      daysToRenewal: 75,
      renewalReadiness: 'tracking' as const,
    },
    {
      id: CUSTOMER_IDS.aperio,
      name: 'Aperio Analytics',
      slug: 'aperio',
      domain: 'aperioanalytics.com',
      oneLiner: 'Product analytics SaaS, active escalation',
      tier: 'Growth',
      arrCents: 3000000, // $30k/year
      lifecycle: 'at_risk' as const,
      daysToRenewal: 150,
      renewalReadiness: 'at_risk' as const,
    },
    {
      id: CUSTOMER_IDS.quietfield,
      name: 'Quietfield Software',
      slug: 'quietfield',
      domain: 'quietfield.io',
      oneLiner: 'QA test orchestration, gone quiet',
      tier: 'Mid-Market',
      arrCents: 2000000, // $20k/year
      lifecycle: 'active' as const,
      daysToRenewal: 180,
      renewalReadiness: 'tracking' as const,
    },
    {
      id: CUSTOMER_IDS.bridgenote,
      name: 'Bridgenote',
      slug: 'bridgenote',
      domain: 'bridgenote.io',
      oneLiner: 'Revenue intelligence, expansion opportunity',
      tier: 'Growth',
      arrCents: 2600000, // $26k/year
      lifecycle: 'active' as const,
      daysToRenewal: 120,
      renewalReadiness: 'ready' as const,
    },
  ];

  for (const c of customers) {
    try {
      await createCustomerWithId({ ...c, workspaceId: WORKSPACE_ID });
      console.log(`  ✓ ${c.name}`);
    } catch (e: any) {
      console.log(`\n❌ ${c.name} FAILED:`);
      console.log('Full error:', JSON.stringify(e, null, 2));
      console.log('Message:', e.message);
      break; // Stop after first error to see full details
    }
  }

  // 5. Create stakeholders (with correct emails for test script)
  console.log('\nCreating stakeholders...');
  const stakeholders = [
    // Marlin Insights
    { customerId: CUSTOMER_IDS.marlin, name: 'Sarah Chen', email: 'sarah@marlininsights.com', role: 'Head of RevOps' },
    { customerId: CUSTOMER_IDS.marlin, name: 'Jamal Foster', email: 'jamal@marlininsights.com', role: 'Director of Data' },

    // Pinegrove HR
    { customerId: CUSTOMER_IDS.pinegrove, name: 'Maya Brooks', email: 'maya@pinegrove.io', role: 'Director of Operations' },

    // Foldwise (at-risk customer)
    { customerId: CUSTOMER_IDS.foldwise, name: 'David Okonkwo', email: 'david@foldwise.com', role: 'Head of RevOps' },

    // Bevelpoint Logistics
    { customerId: CUSTOMER_IDS.bevelpoint, name: 'Reggie Vance', email: 'reggie@bevelpoint.com', role: 'COO' },

    // Aperio Analytics (escalation customer)
    { customerId: CUSTOMER_IDS.aperio, name: 'Liam Carter', email: 'liam@aperioanalytics.com', role: 'VP Engineering' },
    { customerId: CUSTOMER_IDS.aperio, name: 'Nina Tasaki', email: 'nina@aperioanalytics.com', role: 'CEO' },

    // Quietfield Software (quiet customer)
    { customerId: CUSTOMER_IDS.quietfield, name: 'Hana Müller', email: 'hana@quietfield.io', role: 'Director of Engineering Operations' },

    // Bridgenote (expansion opportunity)
    { customerId: CUSTOMER_IDS.bridgenote, name: 'Kavya Reddy', email: 'kavya@bridgenote.io', role: 'RevOps Manager' },
  ];

  for (const s of stakeholders) {
    try {
      await createStakeholderPublic({ ...s, workspaceId: WORKSPACE_ID });
      console.log(`  ✓ ${s.name} (${s.email})`);
    } catch (e: any) {
      console.log(`  ${s.name} error:`, e.message?.substring(0, 50));
    }
  }

  // 6. Create sample needs (Today Queue)
  console.log('\nCreating sample needs...');
  const needs = [
    {
      id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee01',
      customerId: CUSTOMER_IDS.marlin,
      needType: 'new_handoff',
      headline: 'Review handoff brief for Marlin Insights',
      lede: 'New customer just signed. Devon is handling onboarding. Marcus committed to Outreach connector delivery.',
      workflowStatus: 'needs_response' as const,
      priority: 'high' as const,
    },
    {
      id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee02',
      customerId: CUSTOMER_IDS.aperio,
      needType: 'escalation',
      headline: 'Aperio escalation - postmortem overdue',
      lede: 'Webhook signature change broke two production workflows. Postmortem promised by Wednesday, now overdue. Nina (CEO) is involved.',
      workflowStatus: 'needs_response' as const,
      priority: 'urgent' as const,
    },
    {
      id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee03',
      customerId: CUSTOMER_IDS.foldwise,
      needType: 'going_dark',
      headline: 'Foldwise going quiet after complaints',
      lede: 'David complained about rate-limit incidents 10 days ago. Marcus promised reliability review but hasn\'t followed up. Customer mentioning competitors.',
      workflowStatus: 'needs_response' as const,
      priority: 'high' as const,
    },
    {
      id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee04',
      customerId: CUSTOMER_IDS.quietfield,
      needType: 'check_in_due',
      headline: 'No contact with Quietfield in 32 days',
      lede: 'Last interaction was a routine Slack question from Hana. Usage data shows continued activity, but no sense of customer health. Renewal in 6 months.',
      workflowStatus: 'needs_response' as const,
      priority: 'medium' as const,
    },
    {
      id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeee05',
      customerId: CUSTOMER_IDS.bevelpoint,
      needType: 'approaching_renewal',
      headline: 'Bevelpoint renewal in 75 days',
      lede: 'Usage is solid but Reggie mentioned board pushback on tool sprawl. Salesforce CPQ overlaps with our features. Need to make renewal case.',
      workflowStatus: 'needs_response' as const,
      priority: 'medium' as const,
    },
  ];

  for (const need of needs) {
    try {
      await createNeedWithId({ ...need, workspaceId: WORKSPACE_ID });
      console.log(`  ✓ Need created: ${need.headline.substring(0, 50)}...`);
    } catch (e: any) {
      console.log(`  Need error:`, e.message?.substring(0, 50));
    }
  }

  // 7. Create sample signals
  console.log('\nCreating sample signals...');
  const signals = [
    {
      customerId: CUSTOMER_IDS.foldwise,
      kind: 'sentiment',
      state: 'warn',
      sentence: 'David expressed frustration about API rate-limit incidents and slow resolution time',
      confidence: 0.85,
      detectedAt: new Date().toISOString(),
    },
    {
      customerId: CUSTOMER_IDS.aperio,
      kind: 'sentiment',
      state: 'risk',
      sentence: 'Nina (CEO) pulled into escalation. Two production workflows silently failed for 36 hours.',
      confidence: 0.95,
      detectedAt: new Date().toISOString(),
    },
    {
      customerId: CUSTOMER_IDS.bridgenote,
      kind: 'expansion',
      state: 'ok',
      sentence: 'Kavya asked about Gong connector integration. Bridgenote just hired 2 more RevOps people.',
      confidence: 0.78,
      detectedAt: new Date().toISOString(),
    },
  ];

  for (const signal of signals) {
    try {
      await createSignal({ ...signal, workspaceId: WORKSPACE_ID });
      console.log(`  ✓ Signal: ${signal.sentence.substring(0, 50)}...`);
    } catch (e: any) {
      console.log(`  Signal error:`, e.message?.substring(0, 50));
    }
  }

  // 8. Create customer goals (5 customers with goals, 2 without to test HITL)
  // Foldwise and Quietfield intentionally have NO goals - agent should ask via HITL
  console.log('\nCreating customer goals...');
  const customerGoals = [
    // Marlin Insights - onboarding customer
    { customerId: CUSTOMER_IDS.marlin, text: 'Reduce manual data entry by 80% within first quarter', status: 'active' as const, sortOrder: 1 },
    { customerId: CUSTOMER_IDS.marlin, text: 'Integrate with existing Salesforce workflows', status: 'active' as const, sortOrder: 2 },
    { customerId: CUSTOMER_IDS.marlin, text: 'Enable RevOps team self-service analytics by go-live', status: 'active' as const, sortOrder: 3 },

    // Pinegrove HR - active/expanding customer
    { customerId: CUSTOMER_IDS.pinegrove, text: 'Automate HR data sync across 3 regional offices', status: 'achieved' as const, sortOrder: 1 },
    { customerId: CUSTOMER_IDS.pinegrove, text: 'Reduce payroll processing time by 50%', status: 'active' as const, sortOrder: 2 },
    { customerId: CUSTOMER_IDS.pinegrove, text: 'Implement compliance reporting dashboard', status: 'active' as const, sortOrder: 3 },

    // Bevelpoint Logistics - renewal approaching
    { customerId: CUSTOMER_IDS.bevelpoint, text: 'Consolidate freight data from 5 carrier systems', status: 'achieved' as const, sortOrder: 1 },
    { customerId: CUSTOMER_IDS.bevelpoint, text: 'Real-time visibility into shipment status', status: 'active' as const, sortOrder: 2 },
    { customerId: CUSTOMER_IDS.bevelpoint, text: 'Reduce manual dispatching effort by 60%', status: 'active' as const, sortOrder: 3 },

    // Aperio Analytics - at-risk with escalation (goal status reflects delivery risk)
    { customerId: CUSTOMER_IDS.aperio, text: 'Reliable webhook integration for production workflows', status: 'active' as const, sortOrder: 1 },
    { customerId: CUSTOMER_IDS.aperio, text: 'Zero-downtime data pipeline for analytics dashboard', status: 'active' as const, sortOrder: 2 },

    // Bridgenote - expansion opportunity
    { customerId: CUSTOMER_IDS.bridgenote, text: 'Unified revenue intelligence across all channels', status: 'active' as const, sortOrder: 1 },
    { customerId: CUSTOMER_IDS.bridgenote, text: 'Integrate Gong call data with pipeline forecasting', status: 'active' as const, sortOrder: 2 },
    { customerId: CUSTOMER_IDS.bridgenote, text: 'Enable RevOps team to build custom attribution models', status: 'active' as const, sortOrder: 3 },

    // NOTE: Foldwise and Quietfield intentionally have NO goals
    // This tests the agent's ability to detect missing goals and ask via HITL
  ];

  for (const goal of customerGoals) {
    try {
      await createGoalPublic(goal);
      console.log(`  ✓ Goal for ${goal.customerId.slice(-2)}: ${goal.text.substring(0, 40)}...`);
    } catch (e: any) {
      console.log(`  Goal error:`, e.message?.substring(0, 50));
    }
  }

  // =========================================================================
  // 10. Seed HITL Test Data (Agent Runs waiting for input)
  // =========================================================================
  console.log('\n10. Creating HITL test data (waiting agent runs)...');

  const HITL_AGENT_RUN_1 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad';
  const HITL_AGENT_RUN_2 = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb4';
  const HITL_AGENT_RUN_3 = 'ccccccccccccccccccccccccccccccc5';

  // HITL Test Data with Structured Question Types
  // Uses the new backend format: question_type is lowercase (pick_one, pick_many, etc.)
  // Metadata contains type-specific fields
  const hitlTestRuns = [
    {
      id: HITL_AGENT_RUN_1,
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.marlin,
      agentName: 'handoff_auto',
      pauseReason: 'Need clarification on primary champion and contract details',
      currentStep: 'stakeholder_validation',
      confidenceLevel: 'medium' as const,
      clarifyingQuestions: JSON.stringify([
        {
          id: 'q_champion',
          field: 'primary_champion',
          question: 'Who is the primary champion for this account?',
          context: 'Sarah Chen and Jamal Foster both have recent activity. Who should be the main point of contact?',
          question_type: 'pick_person',
          metadata: {
            people: [
              { stakeholder_id: 'sarah-004', name: 'Sarah Chen', role: 'VP Product', avatar_seed: 'sarah', signal: 'ok', signal_label: 'ENGAGED', last_contact: '2h ago · email' },
              { stakeholder_id: 'jamal-004', name: 'Jamal Foster', role: 'Head of Ops', avatar_seed: 'jamal', signal: 'neutral', signal_label: 'NEUTRAL', last_contact: '1d ago · slack' },
            ],
            allow_decide: true,
            allow_manual: true,
          },
        },
        {
          id: 'q_arr',
          field: 'arr_cents',
          question: 'What is the confirmed annual contract value?',
          context: 'The handoff brief mentioned $50K but email thread suggests possible expansion to $75K.',
          question_type: 'freeform',
          placeholder: '$XX,XXX',
          metadata: { multiline: false },
        },
        {
          id: 'q_timeline',
          field: 'go_live_date',
          question: 'When is the expected go-live date?',
          context: 'Customer mentioned "by end of quarter" but no specific date.',
          question_type: 'date',
          metadata: { min_date: '2026-06-01', max_date: '2026-12-31' },
        },
      ]),
    },
    {
      id: HITL_AGENT_RUN_2,
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.aperio,
      agentName: 'handoff_auto',
      pauseReason: 'Missing key technical requirements for onboarding plan',
      currentStep: 'plan_generation',
      confidenceLevel: 'low' as const,
      clarifyingQuestions: JSON.stringify([
        {
          id: 'q_sso',
          field: 'requires_sso',
          question: 'Does Aperio Analytics require SSO integration?',
          context: 'Enterprise customers typically need SSO. Please confirm.',
          question_type: 'yes_no',
          metadata: {
            yes_label: 'Yes, they need SSO',
            no_label: 'No, standard auth is fine',
            allow_decide: true,
          },
        },
        {
          id: 'q_data_volume',
          field: 'expected_data_volume',
          question: 'What is the expected monthly data volume?',
          context: 'This affects infrastructure setup and onboarding timeline.',
          question_type: 'pick_one',
          metadata: {
            options: [
              { value: 'low', label: 'Low (< 100GB/mo)', description: 'Standard infrastructure' },
              { value: 'medium', label: 'Medium (100GB - 1TB/mo)', description: 'Dedicated cluster recommended' },
              { value: 'high', label: 'High (> 1TB/mo)', description: 'Enterprise infrastructure required' },
            ],
            allow_decide: false,
            allow_other: true,
          },
        },
      ]),
    },
    // Third run with ALL structured question types for testing
    {
      id: HITL_AGENT_RUN_3,
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.foldwise,
      agentName: 'handoff_auto',
      pauseReason: 'A few things before I can keep going on the Foldwise onboarding plan.',
      currentStep: 'onboarding_plan_draft',
      confidenceLevel: 'medium' as const,
      clarifyingQuestions: JSON.stringify([
        // pick_one with options
        {
          id: 'q_timeline_type',
          field: 'timeline_firmness',
          question: 'How firm is the Aug 15 launch date?',
          context: 'Sales noted a board commitment in the handoff brief.',
          question_type: 'pick_one',
          metadata: {
            options: [
              { value: 'firm', label: 'Firm — board commitment', description: 'Missing this date has real consequences', default: true },
              { value: 'target', label: 'Target — they\'d prefer it', description: 'Important but some flexibility' },
              { value: 'aspiration', label: 'Aspiration — nice-to-have', description: 'Would be great but not critical' },
            ],
            allow_decide: true,
            decide_label: 'Sidekick, you decide',
          },
        },
        // pick_many for multi-select
        {
          id: 'q_critical_milestones',
          field: 'critical_milestones',
          question: 'Which milestones are most critical for Foldwise?',
          context: 'Select up to 3 milestones that define success for this customer.',
          question_type: 'pick_many',
          metadata: {
            options: [
              { value: 'sso', label: 'SSO Integration' },
              { value: 'data_import', label: 'Historical Data Import' },
              { value: 'training', label: 'Team Training Sessions' },
              { value: 'api', label: 'API Setup' },
              { value: 'reporting', label: 'Custom Reporting' },
            ],
            min_selections: 1,
            max_selections: 3,
          },
        },
        // pick_person for stakeholder selection
        {
          id: 'q_primary_champion',
          field: 'primary_champion',
          question: 'Who should I mark as the primary champion?',
          context: 'Two contacts have the role + recency to qualify.',
          question_type: 'pick_person',
          metadata: {
            people: [
              { stakeholder_id: 'david-004', name: 'David Okonkwo', role: 'Head of RevOps', avatar_seed: 'david', signal: 'ok', signal_label: 'ENGAGED', last_contact: '2h ago · email' },
              { stakeholder_id: 'emily-004', name: 'Emily Zhang', role: 'VP Engineering', avatar_seed: 'emily', signal: 'warn', signal_label: 'BUSY', last_contact: '5d ago · meeting' },
              { stakeholder_id: 'marcus-004', name: 'Marcus Johnson', role: 'CEO', avatar_seed: 'marcus', signal: 'neutral', signal_label: 'EXECUTIVE', last_contact: '2w ago · call' },
            ],
            allow_decide: true,
            allow_manual: true,
            multi_select: false,
          },
        },
        // slider for numeric input
        {
          id: 'q_silence_threshold',
          field: 'silence_threshold_days',
          question: 'How many days of silence before I flag a Going Dark risk?',
          context: 'Customer mentioned "aggressive timeline" - shorter threshold catches issues faster but may create noise.',
          question_type: 'slider',
          metadata: {
            min: 3,
            max: 21,
            default: 7,
            step: 1,
            label_low: 'Aggressive · 3d',
            label_high: 'Patient · 21d',
            format_template: '{value} days of silence',
          },
        },
        // freeform for open text
        {
          id: 'q_success_criteria',
          field: 'custom_success_criteria',
          question: 'Any specific success criteria for Foldwise?',
          context: 'E.g., "Must integrate with Salesforce by Day 15" or "Need executive sign-off before training"',
          question_type: 'freeform',
          required: false,
          placeholder: 'Enter success criteria or leave blank...',
          metadata: {
            multiline: true,
            max_length: 500,
          },
        },
        // yes_no for binary choice
        {
          id: 'q_has_technical_resources',
          field: 'has_technical_resources',
          question: 'Does Foldwise have technical resources for integration?',
          context: 'This affects which milestones we recommend and whether we need to provide more hands-on support.',
          question_type: 'yes_no',
          metadata: {
            yes_label: 'Yes, they have developers',
            no_label: 'No, they need our help',
            allow_decide: true,
          },
        },
      ]),
    },
  ];

  for (const run of hitlTestRuns) {
    try {
      await createWaitingAgentRunForTest(run);
      console.log(`  ✓ Agent run: ${run.agentName} for customer ${run.customerId.slice(0, 8)}...`);
    } catch (e: any) {
      console.log(`  Agent run may already exist:`, e.message?.substring(0, 50));
    }
  }

  // Also create sidekick items for these agent runs
  const sidekickItems = [
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.marlin,
      type: 'asking' as const,
      question: 'Who is the primary champion?',
      why: 'Need to confirm main point of contact before proceeding with onboarding plan.',
      isBlocking: true,
      agentRunId: HITL_AGENT_RUN_1,
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.aperio,
      type: 'asking' as const,
      question: 'Does Aperio require SSO?',
      why: 'Technical requirement needed for infrastructure planning.',
      isBlocking: true,
      agentRunId: HITL_AGENT_RUN_2,
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.foldwise,
      type: 'tip' as const,
      text: 'Last interaction was a positive demo call. Customer mentioned they want to move fast with implementation.',
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.foldwise,
      type: 'asking' as const,
      question: 'A few things before I can keep going on the onboarding plan',
      why: 'Need to verify team contacts, milestone priorities, and timeline confidence before finalizing the plan.',
      isBlocking: true,
      agentRunId: HITL_AGENT_RUN_3,
    },
    // Observed items - quieter factual notes
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.pinegrove,
      type: 'observed' as const,
      text: 'Last activity was 14 days ago. Response rate has been declining over the past month.',
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.bevelpoint,
      type: 'observed' as const,
      text: 'Sarah mentioned budget discussions in last email. May be relevant to renewal timeline.',
    },
    // Working items - agent currently processing
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.quietfield,
      type: 'working' as const,
      task: 'Analyzing usage patterns',
      step: 'Correlating feature adoption with contract value',
      stepNum: 3,
      totalSteps: 5,
    },
    // Resolved items - completed questions
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.bridgenote,
      type: 'resolved' as const,
      question: 'Confirm the onboarding timeline for Bridgenote',
      resolution: 'Approved Standard 30-day plan with extended API integration phase.',
      resolvedByUserId: USER_SCOTT_ID,
      resolvedAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // Yesterday
      timestampLabel: '1d ago',
    },
    {
      workspaceId: WORKSPACE_ID,
      customerId: CUSTOMER_IDS.marlin,
      type: 'resolved' as const,
      question: 'What is the contract renewal date?',
      resolution: 'Renewal date confirmed as June 15, 2026. Auto-renewal clause active.',
      resolvedByUserId: USER_MARCUS_ID,
      resolvedAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days ago
      timestampLabel: '3d ago',
    },
  ];

  for (const item of sidekickItems) {
    try {
      await createSidekickItem(item);
      console.log(`  ✓ Sidekick item: ${item.type} for customer ${item.customerId.slice(0, 8)}...`);
    } catch (e: any) {
      console.log(`  Sidekick item error:`, e.message?.substring(0, 50));
    }
  }

  console.log('\n✅ Seeding complete!\n');
  console.log('📊 Summary:');
  console.log('  • Workspace: Northcrest (northcrest.io) with valueProp');
  console.log('  • Users: Marcus Lee, Priya Shah, Devon Patel');
  console.log('  • Customers: 7 (Marlin, Pinegrove, Foldwise, Bevelpoint, Aperio, Quietfield, Bridgenote)');
  console.log('  • Stakeholders: 9 with correct emails for testing');
  console.log('  • Needs: 5 sample items in Today Queue');
  console.log('  • Signals: 3 sample signals');
  console.log('  • Customer Goals: 14 goals for 5 customers (Foldwise & Quietfield have NONE for HITL testing)');
  console.log('  • HITL Agent Runs: 3 waiting for input (Marlin, Aperio, Foldwise)');
  console.log('  • Sidekick Items: 9 (3 asking, 1 tip, 2 observed, 1 working, 2 resolved)');
  console.log('\n🧪 Ready for testing with test-signal-watcher.sh');
  console.log(`   Workspace ID: ${WORKSPACE_ID}`);
  console.log(`   HITL Test Run 1: ${HITL_AGENT_RUN_1} (Marlin - 3 questions)`);
  console.log(`   HITL Test Run 2: ${HITL_AGENT_RUN_2} (Aperio - 2 questions)`);
  console.log(`   HITL Test Run 3: ${HITL_AGENT_RUN_3} (Foldwise - 6 expanded questions)`);
}

seed()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error('❌ Seeding failed:', error);
    process.exit(1);
  });
