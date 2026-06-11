/**
 * Seed script for Playbooks and System Configuration
 * Run with: cd frontend && npx tsx seed-playbooks.ts
 *
 * This seeds the foundational data needed for the handoff agent:
 * - Standard Onboarding Playbook with milestones
 * - Handbook doc with system rules
 *
 * Run this BEFORE importing customers from Notion.
 * Customers are NOT created here - they come from Notion import.
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  createWorkspaceWithId,
  createPlaybookWithId,
  createPlaybookMilestoneWithId,
  createHandbookDocWithId,
  createHandbookVersionWithId,
  PlaybookScenario,
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

// IDs for referential integrity
const WORKSPACE_ID = '11111111-1111-1111-1111-111111111111';

// Playbook IDs
const PLAYBOOKS = {
  standard: '22222222-2222-2222-2222-222222222221',
  enterprise: '22222222-2222-2222-2222-222222222222',
  selfServe: '22222222-2222-2222-2222-222222222223',
};

// Handbook IDs
const HANDBOOK_DOC_ID = '33333333-3333-3333-3333-333333333331';
const HANDBOOK_VERSION_ID = '44444444-4444-4444-4444-444444444441';

async function seed() {
  console.log('🌱 Seeding playbooks and system configuration...\n');

  // 1. Create workspace (if not exists)
  console.log('Creating workspace...');
  try {
    await createWorkspaceWithId({
      id: WORKSPACE_ID,
      name: 'Herofy Demo',
      slug: 'herofy-demo',
      setupCompleted: true, // Mark setup as complete for seeded workspace
    });
    console.log('  ✓ Workspace created (setupCompleted=true)');
  } catch (e: any) {
    console.log('  Workspace may already exist:', e.message?.substring(0, 50));
  }

  // 2. Create handbook doc and version (system rules for AI)
  console.log('\nCreating handbook (system rules)...');
  try {
    await createHandbookDocWithId({
      id: HANDBOOK_DOC_ID,
      workspaceId: WORKSPACE_ID,
      slug: 'onboarding-guide',
      title: 'Customer Onboarding Guide',
      description: 'Standard procedures for customer onboarding',
      body: `# Customer Onboarding Guide

## Overview
This guide outlines our standard approach to onboarding new customers.

## Key Principles
1. **Early Value Delivery**: Get customers to their first "aha moment" within the first week
2. **Clear Communication**: Set expectations early, communicate proactively
3. **Technical Excellence**: Ensure smooth technical setup before moving forward
4. **Human Touch**: AI assists, but humans own the relationship

## Risk Signals During Onboarding
- No response for 3+ business days
- Missed kickoff call
- Technical blockers lasting >2 days
- Stakeholder changes mid-onboarding
- Scope creep on requirements

## Escalation Criteria
- Customer expresses frustration
- Timeline at risk (>20% behind)
- Executive involvement requested
- Competitive threat mentioned`,
      blastRadius: 'high',
    });
    console.log('  ✓ Handbook doc created');
  } catch (e: any) {
    console.log('  Handbook doc may already exist:', e.message?.substring(0, 50));
  }

  try {
    await createHandbookVersionWithId({
      id: HANDBOOK_VERSION_ID,
      docId: HANDBOOK_DOC_ID,
      body: `# Customer Onboarding Guide v1.0

This is the initial version of our onboarding guide.

## Milestones
Each customer goes through these standard phases:
1. Kickoff & Alignment
2. Technical Setup
3. Data Migration (if applicable)
4. User Training
5. Go-Live
6. Post-Launch Review`,
    });
    console.log('  ✓ Handbook version created');
  } catch (e: any) {
    console.log('  Handbook version may already exist:', e.message?.substring(0, 50));
  }

  // 3. Create Standard Onboarding Playbook
  console.log('\nCreating Standard Onboarding playbook...');
  try {
    await createPlaybookWithId({
      id: PLAYBOOKS.standard,
      workspaceId: WORKSPACE_ID,
      name: 'Standard Onboarding',
      archetype: 'mid-market',
      fitNote: 'Best for customers with $25K-$100K ARR. Typical timeline: 30-45 days.',
      scenario: PlaybookScenario.onboarding,
    });
    console.log('  ✓ Standard Onboarding playbook created');
  } catch (e: any) {
    console.log('  Playbook may already exist:', e.message?.substring(0, 50));
  }

  // Standard Onboarding Milestones
  const standardMilestones = [
    {
      id: '55555555-5555-5555-5555-555555555501',
      title: 'Kickoff Call',
      ownerSide: 'us' as const,
      durationDays: 3,
      description: 'Align on goals, timeline, and success criteria. Identify stakeholders and communication preferences.',
      sortOrder: 1,
    },
    {
      id: '55555555-5555-5555-5555-555555555502',
      title: 'Technical Setup',
      ownerSide: 'customer' as const,
      durationDays: 7,
      description: 'API keys, SSO configuration, environment setup. Provide documentation and support as needed.',
      sortOrder: 2,
    },
    {
      id: '55555555-5555-5555-5555-555555555503',
      title: 'Integration Configuration',
      ownerSide: 'joint' as const,
      durationDays: 7,
      description: 'Configure integrations, connect data sources, validate data flow.',
      sortOrder: 3,
    },
    {
      id: '55555555-5555-5555-5555-555555555504',
      title: 'Data Migration',
      ownerSide: 'joint' as const,
      durationDays: 5,
      description: 'Import historical data, validate integrity, run reconciliation checks.',
      sortOrder: 4,
    },
    {
      id: '55555555-5555-5555-5555-555555555505',
      title: 'User Training',
      ownerSide: 'us' as const,
      durationDays: 5,
      description: 'Train end users and admins. Provide documentation and quick-reference guides.',
      sortOrder: 5,
    },
    {
      id: '55555555-5555-5555-5555-555555555506',
      title: 'Go-Live',
      ownerSide: 'joint' as const,
      durationDays: 3,
      description: 'Launch in production. Monitor closely, address any issues immediately.',
      sortOrder: 6,
    },
    {
      id: '55555555-5555-5555-5555-555555555507',
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
        playbookId: PLAYBOOKS.standard,
      });
      console.log(`  ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`  ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // 4. Create Enterprise Playbook (for high-touch customers)
  console.log('\nCreating Enterprise playbook...');
  try {
    await createPlaybookWithId({
      id: PLAYBOOKS.enterprise,
      workspaceId: WORKSPACE_ID,
      name: 'Enterprise Onboarding',
      archetype: 'enterprise',
      fitNote: 'For customers with $100K+ ARR. Extended timeline: 60-90 days. Includes executive alignment.',
      scenario: PlaybookScenario.onboarding,
    });
    console.log('  ✓ Enterprise playbook created');
  } catch (e: any) {
    console.log('  Playbook may already exist:', e.message?.substring(0, 50));
  }

  // Enterprise Milestones
  const enterpriseMilestones = [
    {
      id: '55555555-5555-5555-5555-555555555601',
      title: 'Executive Alignment',
      ownerSide: 'us' as const,
      durationDays: 5,
      description: 'Meet with executive sponsors to align on strategic goals and success metrics.',
      sortOrder: 1,
    },
    {
      id: '55555555-5555-5555-5555-555555555602',
      title: 'Discovery & Planning',
      ownerSide: 'joint' as const,
      durationDays: 10,
      description: 'Detailed requirements gathering, technical architecture review, project planning.',
      sortOrder: 2,
    },
    {
      id: '55555555-5555-5555-5555-555555555603',
      title: 'Security Review',
      ownerSide: 'customer' as const,
      durationDays: 14,
      description: 'Complete security questionnaire, SOC2 review, vendor assessment.',
      sortOrder: 3,
    },
    {
      id: '55555555-5555-5555-5555-555555555604',
      title: 'Technical Setup & Integration',
      ownerSide: 'joint' as const,
      durationDays: 14,
      description: 'Enterprise SSO, custom integrations, staging environment setup.',
      sortOrder: 4,
    },
    {
      id: '55555555-5555-5555-5555-555555555605',
      title: 'Pilot Deployment',
      ownerSide: 'joint' as const,
      durationDays: 14,
      description: 'Limited rollout to pilot team, gather feedback, iterate.',
      sortOrder: 5,
    },
    {
      id: '55555555-5555-5555-5555-555555555606',
      title: 'Full Rollout',
      ownerSide: 'joint' as const,
      durationDays: 10,
      description: 'Company-wide deployment, training sessions, change management support.',
      sortOrder: 6,
    },
    {
      id: '55555555-5555-5555-5555-555555555607',
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
        playbookId: PLAYBOOKS.enterprise,
      });
      console.log(`  ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`  ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  // 5. Create Self-Serve Playbook (for PLG/low-touch)
  console.log('\nCreating Self-Serve playbook...');
  try {
    await createPlaybookWithId({
      id: PLAYBOOKS.selfServe,
      workspaceId: WORKSPACE_ID,
      name: 'Self-Serve Quick Start',
      archetype: 'self-serve',
      fitNote: 'For PLG customers under $25K ARR. Automated onboarding with light-touch check-ins.',
      scenario: PlaybookScenario.onboarding,
    });
    console.log('  ✓ Self-Serve playbook created');
  } catch (e: any) {
    console.log('  Playbook may already exist:', e.message?.substring(0, 50));
  }

  // Self-Serve Milestones
  const selfServeMilestones = [
    {
      id: '55555555-5555-5555-5555-555555555701',
      title: 'Welcome & Setup',
      ownerSide: 'customer' as const,
      durationDays: 3,
      description: 'Self-service account setup, initial configuration via wizard.',
      sortOrder: 1,
    },
    {
      id: '55555555-5555-5555-5555-555555555702',
      title: 'First Value',
      ownerSide: 'customer' as const,
      durationDays: 7,
      description: 'Complete first use case, see initial value from the product.',
      sortOrder: 2,
    },
    {
      id: '55555555-5555-5555-5555-555555555703',
      title: 'Check-in Call',
      ownerSide: 'us' as const,
      durationDays: 3,
      description: 'Optional 30-min call to answer questions and ensure success.',
      sortOrder: 3,
    },
    {
      id: '55555555-5555-5555-5555-555555555704',
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
        playbookId: PLAYBOOKS.selfServe,
      });
      console.log(`  ✓ ${m.title}`);
    } catch (e: any) {
      console.log(`  ${m.title} may already exist:`, e.message?.substring(0, 50));
    }
  }

  console.log('\n✅ Playbooks and system configuration seeded!');
  console.log('\nNext steps:');
  console.log('1. Import customers from Notion');
  console.log('2. Test handoff agent with: curl -X POST http://localhost:8081/agents/handoff-chain/run');
}

seed().catch(console.error);
