/**
 * Demo Suite Constants
 *
 * Single source of truth for all demo data: UUIDs, Notion page IDs, customer
 * definitions, stakeholder emails, and signal scripts.
 *
 * All UUIDs are fixed and deterministic — SQL seeds use the same values inline.
 * No inter-script ID passing is needed; every script can run independently.
 *
 * Source: docs/demo_docs/demo_customers_notion.md
 */

// =============================================================================
// WORKSPACE + TEAM
// =============================================================================

export const WORKSPACE_ID = '00000000-0000-0000-0000-000000000001';

export const USER_IDS = {
  marcus: 'marcus-lee-northcrest-00000001',
  priya:  'priya-shah-northcrest-0000001',
  devon:  'devon-patel-northcrest-000001',
  scott:  'rk07bQuUP7PbwFInqX0QWI23jKE3', // real Firebase UID
};

export const PLAYBOOK_IDS = {
  standard:   'demo0000-play-0000-0000-000000000001',
  enterprise: 'demo0000-play-0000-0000-000000000002',
  selfServe:  'demo0000-play-0000-0000-000000000003',
};

// =============================================================================
// CUSTOMER IDs  (fixed UUIDs — same values used in SQL seeds)
// =============================================================================

export const CUSTOMER_IDS = {
  // Lane 1 — new handoffs (arrive at demo start)
  marlin:      'aa000001-0000-0000-0000-000000000001',
  cedarline:   'aa000001-0000-0000-0000-000000000002',
  vergeLending:'aa000001-0000-0000-0000-000000000003',

  // Lane 2 — established portfolio (seeded with 90-day history)
  quietfield:  'aa000001-0000-0000-0000-000000000004', // going dark — PRIMARY sweep target
  aperio:      'aa000001-0000-0000-0000-000000000005', // active escalation
  bevelpoint:  'aa000001-0000-0000-0000-000000000006', // renewal risk
  foldwise:    'aa000001-0000-0000-0000-000000000007', // frustrated / at-risk
  bridgenote:  'aa000001-0000-0000-0000-000000000008', // expansion signal
  pinegrove:   'aa000001-0000-0000-0000-000000000009', // healthy / expanding
  velmont:     'aa000001-0000-0000-0000-000000000010', // post-renewal open commitments

  // Background accounts — present in Lane 2 portfolio, minimal history
  hollowbrook: 'aa000001-0000-0000-0000-000000000011',
  saltmarsh:   'aa000001-0000-0000-0000-000000000012',
  pebblerock:  'aa000001-0000-0000-0000-000000000013',
} as const;

// =============================================================================
// NOTION PAGE IDs
// Source: docs/demo_docs/demo_customers_notion.md (exported filenames)
//
// NOTE: Bevelpoint ID appears to be 31 chars in the export — verify in Notion
// before running Lane 2 seeds. Placeholder marked below.
// =============================================================================

export const NOTION_PAGE_IDS = {
  marlin:       'a38f7c2b4dd8418e8bd7926778b6c3ac',
  cedarline:    '36d8cb9801b5809fb8d0e9404126dbf6',
  vergeLending: '36d8cb9801b580f3ae77f0ff73b535b5',
  quietfield:   '3c251ee87eae4e88ad13df1d3b94f43e',
  aperio:       'ebf0292c6a654ed58c63f6573476aaad',
  bevelpoint:   'VERIFY-60cbf492fe0b436fad3089313c8d83a', // 31 chars in export — check Notion
  foldwise:     '5df12c7e756e4e41a0b091ede18034b6',
  bridgenote:   'b3a34a67d0854caaa1c442effe160b0b',
  pinegrove:    'a3eddb5e26854fceaf0adfee0339a5f7',
  velmont:      '36e8cb9801b58038a006fb805905fe6f',
  hollowbrook:  '36d8cb9801b580fca29edcd53917015c',
  saltmarsh:    '36d8cb9801b5804da822fce2a6d0f503',
  pebblerock:   '36d8cb9801b58027b41fd555338f898e',
} as const;

export function notionUrl(pageId: string): string {
  return `https://www.notion.so/${pageId}`;
}

// =============================================================================
// CUSTOMER DEFINITIONS
// =============================================================================

import { CustomerLifecycle } from '@herofy/dataconnect';

export type DemoCustomer = {
  id: string;
  notionPageId: string;
  name: string;
  slug: string;
  domain: string;
  oneLiner: string;
  tier: string;
  arrCents: number;
  lifecycle: CustomerLifecycle;
  daysToRenewal: number;
  onboardingDayCurrent?: number;
  onboardingDayTotal?: number;
  // Champion contact — must match stakeholder email seeded in DB
  // so signal injection resolves the correct customer by sender email.
  primaryEmail: string;
};

export const DEMO_CUSTOMERS: DemoCustomer[] = [
  // ── Lane 1: new handoffs ────────────────────────────────────────────────────
  {
    id: CUSTOMER_IDS.marlin,
    notionPageId: NOTION_PAGE_IDS.marlin,
    name: 'Marlin Insights',
    slug: 'marlin-insights',
    domain: 'marlininsights.com',
    oneLiner: 'Series A product analytics for ecommerce',
    tier: 'Mid-Market',
    arrCents: 1_800_000,
    lifecycle: CustomerLifecycle.handoff,
    daysToRenewal: 365,
    onboardingDayCurrent: 0,
    onboardingDayTotal: 60,
    primaryEmail: 'sarah.chen@marlininsights.com',
  },
  {
    id: CUSTOMER_IDS.cedarline,
    notionPageId: NOTION_PAGE_IDS.cedarline,
    name: 'Cedarline Freight',
    slug: 'cedarline-freight',
    domain: 'cedarlinefreight.com',
    oneLiner: 'Seed-stage SaaS in freight brokerage operations',
    tier: 'SMB',
    arrCents: 2_400_000,
    lifecycle: CustomerLifecycle.handoff,
    daysToRenewal: 365,
    onboardingDayCurrent: 0,
    onboardingDayTotal: 60,
    primaryEmail: 'lena@cedarlinefreight.com',
  },
  {
    id: CUSTOMER_IDS.vergeLending,
    notionPageId: NOTION_PAGE_IDS.vergeLending,
    name: 'Verge Lending',
    slug: 'verge-lending',
    domain: 'vergelending.com',
    oneLiner: 'Series B SaaS in lending operations',
    tier: 'Growth',
    arrCents: 3_800_000,
    lifecycle: CustomerLifecycle.handoff,
    daysToRenewal: 365,
    onboardingDayCurrent: 0,
    onboardingDayTotal: 50,
    primaryEmail: 'marcus@vergelending.com',
  },

  // ── Lane 2: established portfolio ───────────────────────────────────────────
  {
    id: CUSTOMER_IDS.quietfield,
    notionPageId: NOTION_PAGE_IDS.quietfield,
    name: 'Quietfield Software',
    slug: 'quietfield-software',
    domain: 'quietfieldsoftware.com',
    oneLiner: 'B2B SaaS for QA test orchestration',
    tier: 'SMB',
    arrCents: 2_000_000,
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 180,
    primaryEmail: 'hana.mueller@quietfieldsoftware.com',
  },
  {
    id: CUSTOMER_IDS.aperio,
    notionPageId: NOTION_PAGE_IDS.aperio,
    name: 'Aperio Analytics',
    slug: 'aperio-analytics',
    domain: 'aperioanalytics.com',
    oneLiner: 'Series A product analytics SaaS',
    tier: 'Growth',
    arrCents: 3_000_000,
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 150,
    primaryEmail: 'liam.carter@aperioanalytics.com',
  },
  {
    id: CUSTOMER_IDS.bevelpoint,
    notionPageId: NOTION_PAGE_IDS.bevelpoint,
    name: 'Bevelpoint Logistics',
    slug: 'bevelpoint-logistics',
    domain: 'bevelpointlogistics.com',
    oneLiner: 'B2B SaaS for freight brokerage workflow',
    tier: 'Mid-Market',
    arrCents: 2_400_000,
    lifecycle: CustomerLifecycle.renewing,
    daysToRenewal: 75,
    primaryEmail: 'reggie.vance@bevelpointlogistics.com',
  },
  {
    id: CUSTOMER_IDS.foldwise,
    notionPageId: NOTION_PAGE_IDS.foldwise,
    name: 'Foldwise',
    slug: 'foldwise',
    domain: 'foldwise.com',
    oneLiner: 'Series B contract lifecycle management SaaS',
    tier: 'Growth',
    arrCents: 3_600_000,
    lifecycle: CustomerLifecycle.at_risk,
    daysToRenewal: 120,
    primaryEmail: 'david.okonkwo@foldwise.com',
  },
  {
    id: CUSTOMER_IDS.bridgenote,
    notionPageId: NOTION_PAGE_IDS.bridgenote,
    name: 'Bridgenote',
    slug: 'bridgenote',
    domain: 'bridgenote.com',
    oneLiner: 'Series A B2B SaaS in revenue intelligence',
    tier: 'Growth',
    arrCents: 2_600_000,
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 120,
    primaryEmail: 'kavya.reddy@bridgenote.com',
  },
  {
    id: CUSTOMER_IDS.pinegrove,
    notionPageId: NOTION_PAGE_IDS.pinegrove,
    name: 'Pinegrove HR',
    slug: 'pinegrove-hr',
    domain: 'pinegrovehr.com',
    oneLiner: 'HR/payroll SaaS',
    tier: 'Mid-Market',
    arrCents: 3_200_000,
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 210,
    primaryEmail: 'maya.brooks@pinegrovehr.com',
  },
  {
    id: CUSTOMER_IDS.velmont,
    notionPageId: NOTION_PAGE_IDS.velmont,
    name: 'Velmont Freight',
    slug: 'velmont-freight',
    domain: 'velmontfreight.com',
    oneLiner: 'Freight brokerage SaaS, recently renewed with uptier',
    tier: 'Growth',
    arrCents: 3_400_000,
    lifecycle: CustomerLifecycle.active,
    daysToRenewal: 365,
    primaryEmail: 'greg@velmontfreight.com',
  },

  // ── Background accounts (Lane 2 portfolio padding) ────────────────────────
  {
    id: CUSTOMER_IDS.hollowbrook,
    notionPageId: NOTION_PAGE_IDS.hollowbrook,
    name: 'Hollowbrook Media',
    slug: 'hollowbrook-media',
    domain: 'hollowbrookmedia.com',
    oneLiner: 'Series A SaaS in ad-ops and media buying',
    tier: 'Growth',
    arrCents: 2_800_000,
    lifecycle: CustomerLifecycle.onboarding,
    daysToRenewal: 330,
    onboardingDayCurrent: 14,
    onboardingDayTotal: 60,
    primaryEmail: 'p.raman@hollowbrookmedia.com',
  },
  {
    id: CUSTOMER_IDS.saltmarsh,
    notionPageId: NOTION_PAGE_IDS.saltmarsh,
    name: 'Saltmarsh Bio',
    slug: 'saltmarsh-bio',
    domain: 'saltmarshbio.com',
    oneLiner: 'Series A SaaS in lab/biotech operations',
    tier: 'Mid-Market',
    arrCents: 3_000_000,
    lifecycle: CustomerLifecycle.onboarding,
    daysToRenewal: 330,
    onboardingDayCurrent: 10,
    onboardingDayTotal: 60,
    primaryEmail: 'a.bose@saltmarshbio.com',
  },
  {
    id: CUSTOMER_IDS.pebblerock,
    notionPageId: NOTION_PAGE_IDS.pebblerock,
    name: 'Pebblerock Retail',
    slug: 'pebblerock-retail',
    domain: 'pebblerockretail.com',
    oneLiner: 'Series A SaaS in retail analytics',
    tier: 'Growth',
    arrCents: 2_600_000,
    lifecycle: CustomerLifecycle.onboarding,
    daysToRenewal: 330,
    onboardingDayCurrent: 8,
    onboardingDayTotal: 60,
    primaryEmail: 'gracem@pebblerockretail.com',
  },
];

// =============================================================================
// STAKEHOLDERS
// Primary email must match DEMO_CUSTOMERS[x].primaryEmail exactly —
// signal injection resolves customers by matching sender → stakeholder email.
// =============================================================================

export type DemoStakeholder = {
  customerId: string;
  name: string;
  role: string;
  email: string;
  isChampion?: boolean;
};

export const DEMO_STAKEHOLDERS: DemoStakeholder[] = [
  // Marlin Insights
  { customerId: CUSTOMER_IDS.marlin, name: 'Sarah Chen',   role: 'Head of RevOps',               email: 'sarah.chen@marlininsights.com',    isChampion: true },
  { customerId: CUSTOMER_IDS.marlin, name: 'Jamal Foster', role: 'Director of Data',              email: 'jamal.foster@marlininsights.com' },

  // Cedarline Freight
  { customerId: CUSTOMER_IDS.cedarline, name: 'Lena Hartwell', role: 'Head of RevOps',   email: 'lena@cedarlinefreight.com',  isChampion: true },
  { customerId: CUSTOMER_IDS.cedarline, name: 'Owen Reyes',    role: 'Data Engineer',    email: 'owen@cedarlinefreight.com' },

  // Verge Lending
  { customerId: CUSTOMER_IDS.vergeLending, name: 'Marcus Webb',       role: 'Director of RevOps',  email: 'marcus@vergelending.com',    isChampion: true },
  { customerId: CUSTOMER_IDS.vergeLending, name: 'Dana Lindqvist',    role: 'Data Lead',            email: 'dana@vergelending.com' },
  { customerId: CUSTOMER_IDS.vergeLending, name: 'Soren Halvorsen',   role: 'VP Engineering',       email: 'soren@vergelending.com' },

  // Quietfield Software
  { customerId: CUSTOMER_IDS.quietfield, name: 'Hana Müller', role: 'Director of Engineering Operations', email: 'hana.mueller@quietfieldsoftware.com', isChampion: true },

  // Aperio Analytics
  { customerId: CUSTOMER_IDS.aperio, name: 'Liam Carter',  role: 'VP Engineering', email: 'liam.carter@aperioanalytics.com', isChampion: true },
  { customerId: CUSTOMER_IDS.aperio, name: 'Nina Tasaki',  role: 'CEO',            email: 'nina.tasaki@aperioanalytics.com' },

  // Bevelpoint Logistics
  { customerId: CUSTOMER_IDS.bevelpoint, name: 'Reggie Vance', role: 'COO', email: 'reggie.vance@bevelpointlogistics.com', isChampion: true },

  // Foldwise
  { customerId: CUSTOMER_IDS.foldwise, name: 'David Okonkwo', role: 'Head of RevOps', email: 'david.okonkwo@foldwise.com', isChampion: true },

  // Bridgenote
  { customerId: CUSTOMER_IDS.bridgenote, name: 'Kavya Reddy', role: 'RevOps Manager', email: 'kavya.reddy@bridgenote.com', isChampion: true },

  // Pinegrove HR
  { customerId: CUSTOMER_IDS.pinegrove, name: 'Maya Brooks', role: 'Director of Operations', email: 'maya.brooks@pinegrovehr.com', isChampion: true },

  // Velmont Freight
  { customerId: CUSTOMER_IDS.velmont, name: 'Greg Halloran', role: 'COO',           email: 'greg@velmontfreight.com',    isChampion: true },
  { customerId: CUSTOMER_IDS.velmont, name: 'Marisol Tan',   role: 'RevOps Lead',   email: 'marisol@velmontfreight.com' },

  // Hollowbrook Media
  { customerId: CUSTOMER_IDS.hollowbrook, name: 'Priya Raman', role: 'RevOps Lead', email: 'p.raman@hollowbrookmedia.com', isChampion: true },

  // Saltmarsh Bio
  { customerId: CUSTOMER_IDS.saltmarsh, name: 'Dr. Anita Bose', role: 'VP Operations',  email: 'a.bose@saltmarshbio.com',   isChampion: true },
  { customerId: CUSTOMER_IDS.saltmarsh, name: 'Felix Tran',      role: 'Systems Analyst', email: 'felix@saltmarshbio.com' },

  // Pebblerock Retail
  { customerId: CUSTOMER_IDS.pebblerock, name: 'Grace Mbeki',   role: 'Director of Operations', email: 'gracem@pebblerockretail.com', isChampion: true },
  { customerId: CUSTOMER_IDS.pebblerock, name: 'Tobias Klein',  role: 'BI Analyst',             email: 'tobias@pebblerockretail.com' },
];

// =============================================================================
// SIGNAL SCRIPTS
// Used by inject/signals.ts to fire /test/gmail-message and /test/slack-message.
// from_email must match a stakeholder email above — that's how customer resolution works.
// =============================================================================

export type EmailSignal = {
  customerId: string;       // for logging only; resolution is by sender email
  from_email: string;
  from_name: string;
  subject: string;
  body: string;
  scenario: 'lane1' | 'lane2' | 'both';
};

export type SlackSignal = {
  customerId: string;
  user_email: string;
  user_name: string;
  text: string;
  channel_name: string;
  scenario: 'lane1' | 'lane2' | 'both';
};

export const DEMO_EMAIL_SIGNALS: EmailSignal[] = [
  // ── Lane 1 signals (fire after handoff agent runs) ─────────────────────────

  // Marlin: Slack-preferring customer emails anyway with an urgent question —
  // shows the signal watcher catching out-of-band contact and routing it.
  {
    customerId: CUSTOMER_IDS.marlin,
    from_email: 'sarah.chen@marlininsights.com',
    from_name: 'Sarah Chen',
    subject: 'Quick question before kickoff',
    body: `Hi — one thing I forgot to ask: do you support writing back to HubSpot from Snowflake, or is it one-directional today? That might affect how we scope phase two. Also, still waiting on the kickoff invite — can we do Thursday afternoon CT?`,
    scenario: 'lane1',
  },

  // ── Lane 2 signals (fire at the "90 days later" demo moment) ───────────────

  // Aperio: follow-up on the three commitments from the emergency call
  {
    customerId: CUSTOMER_IDS.aperio,
    from_email: 'liam.carter@aperioanalytics.com',
    from_name: 'Liam Carter',
    subject: 'Following up on Wednesday commitments',
    body: `Marcus — checking in on the postmortem. Today's Wednesday. Nina is asking me and I need to tell her something concrete. Where does this stand? Also: the webhook signature policy was supposed to be next Friday. Has Priya started on that?`,
    scenario: 'lane2',
  },

  // Foldwise: frustrated follow-up, competitor language
  {
    customerId: CUSTOMER_IDS.foldwise,
    from_email: 'david.okonkwo@foldwise.com',
    from_name: 'David Okonkwo',
    subject: 'Still waiting on the reliability review',
    body: `Marcus, it has been 10 days since I raised the reliability concerns and I haven't heard anything back on the review you mentioned. My team is asking me whether they should trust these automations for our renewal pipeline. I need a real answer, not another apology. I've started a preliminary conversation with Tray.`,
    scenario: 'lane2',
  },

  // Bridgenote: expansion — Gong connector follow-up
  {
    customerId: CUSTOMER_IDS.bridgenote,
    from_email: 'kavya.reddy@bridgenote.com',
    from_name: 'Kavya Reddy',
    subject: 'Gong connector — any update?',
    body: `Hi Marcus, circling back on the Gong integration question from two weeks ago. We just hired two more RevOps folks and this use case is getting more urgent — auto-creating HubSpot tasks from competitor mentions in Gong calls would save us hours a week. Is this something Northcrest can commit to? Happy to jump on a quick call.`,
    scenario: 'lane2',
  },

  // Velmont: day-to-day contact pushing on open commitment
  {
    customerId: CUSTOMER_IDS.velmont,
    from_email: 'marisol@velmontfreight.com',
    from_name: 'Marisol Tan',
    subject: 'EDI connector timeline?',
    body: `Hey — Greg asked me to follow up on the EDI connector. He said it was part of the renewal agreement and scoped at 6 weeks. We are now at week 3. Priya mentioned she was going to start — can you give me a status and projected delivery date so I can put something on Greg's radar?`,
    scenario: 'lane2',
  },
];

export const DEMO_SLACK_SIGNALS: SlackSignal[] = [
  // Marlin: complements the email — Sarah pings on Slack too (she prefers it)
  {
    customerId: CUSTOMER_IDS.marlin,
    user_email: 'sarah.chen@marlininsights.com',
    user_name: 'Sarah Chen',
    text: `Hey — I also sent an email but figured I'd ping here since you mentioned Slack. The HubSpot → Snowflake writeback question is kind of a blocker for how we plan phase 2. Let me know when you have a sec.`,
    channel_name: 'northcrest-marlin',
    scenario: 'lane1',
  },

  // Aperio: Nina escalates over Slack after Liam's email gets no response
  {
    customerId: CUSTOMER_IDS.aperio,
    user_email: 'nina.tasaki@aperioanalytics.com',
    user_name: 'Nina Tasaki',
    text: `Marcus, I'm following up because Liam tells me the postmortem was due today and he hasn't heard anything. I need to know by end of day whether this is being handled. If we miss this commitment, I need to have a broader conversation about whether this partnership is working.`,
    channel_name: 'northcrest-aperio',
    scenario: 'lane2',
  },

  // Bridgenote: quick Slack ping about seat expansion alongside Gong email
  {
    customerId: CUSTOMER_IDS.bridgenote,
    user_email: 'kavya.reddy@bridgenote.com',
    user_name: 'Kavya Reddy',
    text: `Also — separately from the Gong question — we've added 2 RevOps headcount and they need access. Can we add 2 seats? And what's the per-seat pricing at our tier?`,
    channel_name: 'northcrest-bridgenote',
    scenario: 'lane2',
  },
];

// =============================================================================
// GOING DARK DETECTION PARAMETERS
// Quietfield is the primary sweep target. The SQL history seed puts their
// last inbound interaction at 35 days ago — well past the 14-day risk threshold
// for 'active' lifecycle (LIFECYCLE_THRESHOLDS.active = 7, risk = 2× = 14).
// The EngagementTrendDetector also fires: prior 14d window has 3 inbound,
// recent 14d window has 0.
// =============================================================================

export const GOING_DARK_CUSTOMER_ID = CUSTOMER_IDS.quietfield;
export const GOING_DARK_LAST_INBOUND_DAYS_AGO = 35;
