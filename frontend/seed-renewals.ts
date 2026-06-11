/**
 * Renewals seed — layers the renewal workspace data (posture, plays, risk
 * register, goal-progress vectors, champion flags) on top of seed-data.ts.
 *
 * Run AFTER seed-data.ts, against a freshly seeded emulator:
 *   cd frontend && npx tsx seed-data.ts && npx tsx seed-renewals.ts
 *
 * Idempotent: profiles upsert; plays/risk-items/vectors are deleted then
 * recreated; stakeholders are matched by name (updated) or created.
 */

import { initializeApp } from 'firebase/app';
import { getDataConnect, connectDataConnectEmulator } from 'firebase/data-connect';
import {
  getCustomerSeedRefs,
  deleteProgressVector,
  createProgressVector,
  updateProgressVectorBaseline,
  upsertRenewalProfile,
  createRenewalPlay,
  deleteRenewalPlaysForProfile,
  createRenewalRiskItem,
  deleteRenewalRiskItemsForProfile,
  createStakeholderPublic,
  updateStakeholderRenewal,
  createGoalPublic,
} from '@herofy/dataconnect';

const app = initializeApp({ projectId: 'herofy-496505' });
const dc = getDataConnect(app, {
  connector: 'herofy',
  location: 'us-central1',
  service: 'herofy-prod-service',
});
connectDataConnectEmulator(dc, 'localhost', 9399);
console.log('🔍 Renewals seed → emulator localhost:9399\n');

const WORKSPACE_ID = '627b9eaea88649debffde520d1a79c18';

const CUSTOMER_IDS = {
  marlin: 'aaaa11111111111111111111111111d1',
  pinegrove: 'aaaa11111111111111111111111111d2',
  foldwise: 'aaaa11111111111111111111111111d3',
  bevelpoint: 'aaaa11111111111111111111111111d4',
  aperio: 'aaaa11111111111111111111111111d5',
  quietfield: 'aaaa11111111111111111111111111d6',
  bridgenote: 'aaaa11111111111111111111111111d7',
};

// Deterministic profile id per customer (swap the leading tag, keep suffix).
const profileId = (cid: string) => 'cccc' + cid.slice(4);

type Posture = 'expand' | 'hold' | 'defend';
type SignalState = 'ok' | 'warn' | 'risk';
type RiskLevel = 'low' | 'medium' | 'high';
type PlayKind = 're_anchor' | 'de_risk' | 're_seat' | 'upsell' | 'multi_year' | 'co_success' | 'early_close';
type Cat = 'trust' | 'risk_mitigation' | 'stakeholder' | 'value' | 'momentum';

interface VectorSeed {
  goalText: string;           // full goal text — matches a seeded goal, or is created if missing
  category: Cat;
  description: string;
  currentState: SignalState;
  progress: number;
  baselineProgress: number;
  targetProgress: number;
  targetLabel: string;        // evidence caption under the bar
  unlocks: string;            // the "say it as" coaching line
  assessmentReason: string;
}
interface PlaySeed {
  kind: PlayKind;
  title: string;
  description: string;
  basis?: string;
  valueAmountCents?: number;
  valueLabel?: string;
  isPrimary?: boolean;
}
interface RiskSeed { title: string; description: string; severity: RiskLevel; mitigation?: string; }
interface StakeholderSeed {
  name: string;
  role: string;
  email?: string;
  status?: 'active' | 'departed';
  isChampion?: boolean;
  renewalHealth?: SignalState;
  sentimentNote?: string;
}
interface CustomerSeed {
  key: keyof typeof CUSTOMER_IDS;
  posture: Posture;
  narrativeLede: string;
  postureReason: string;
  targetArrCents?: number;
  expansionPipeCents?: number;
  renewalType: string;
  autoRenew: boolean;
  termNote: string;
  lastPriceChangeNote?: string;
  vectors?: VectorSeed[];
  plays?: PlaySeed[];
  risks?: RiskSeed[];
  stakeholders?: StakeholderSeed[];
}

const SEED: CustomerSeed[] = [
  // ---- BEVELPOINT — DEFEND (champion departed, consolidation threat) ----
  {
    key: 'bevelpoint',
    posture: 'defend',
    narrativeLede:
      "The champion left and the board is shopping a carrier-portal consolidation — but the dispatch-time value is real and measurable. Don't lead with the renewal: re-anchor the proof, re-seat a champion, de-risk the contract.",
    postureReason: 'Set from 6 risk signals · champion departed · 21 days silent · consolidation pressure',
    renewalType: 'At risk',
    autoRenew: false,
    termNote: 'Annual · opt-in',
    lastPriceChangeNote: 'None · 2yr flat',
    vectors: [
      {
        goalText: 'Real-time visibility into shipment status',
        category: 'value',
        description: 'Shipment visibility live across all 5 carriers',
        currentState: 'ok',
        progress: 0.78, baselineProgress: 0.14, targetProgress: 0.8,
        targetLabel: 'DISPATCH LATENCY 9D → 3.4D · 12 WORKFLOWS LIVE',
        unlocks:
          "In nine months we took dispatch from 9 days to under 4 — that's real capacity your ops team got back. Lead the renewal with this.",
        assessmentReason: '12 workflows live · finance-verified',
      },
      {
        goalText: 'Reduce manual dispatching effort by 60%',
        category: 'momentum',
        description: 'Dispatch automation rollout to the EMEA desk',
        currentState: 'risk',
        progress: 0.22, baselineProgress: 0.20, targetProgress: 0.8,
        targetLabel: 'STALLED · CHAMPION DEPARTED MARCH',
        unlocks:
          "Don't hide it. “The rollout stalled when Priya left — let's fix that together” turns the weakness into the re-engagement reason.",
        assessmentReason: 'Stalled when the champion departed',
      },
    ],
    plays: [
      {
        kind: 're_anchor', isPrimary: true,
        title: 'Send the value recap before you ask for the meeting',
        description:
          "21 days of silence means you can't open with “renewal.” Lead with their own numbers — the dispatch-time win, dollarized — so the first touch is value, not an invoice.",
        basis: '12 WORKFLOWS × AVG 5.6 DAYS SAVED · FINANCE-VERIFIED',
        valueAmountCents: 2400000, valueLabel: 'PROTECTS · $24K',
      },
      {
        kind: 'de_risk',
        title: 'Get ahead of the consolidation TCO math',
        description:
          "The board thinks the portal consolidation is “free.” It isn't — ~$71K/yr fully loaded, and it loses the 12 workflows ops now depends on. Arm Reggie with the one-pager before the board meeting.",
        basis: 'CARRIER CONTRACTS + SEAT COUNT',
        valueLabel: 'CONSOLIDATION THREAT',
      },
      {
        kind: 're_seat',
        title: 'Name a successor to Priya inside Bevelpoint',
        description:
          'One champion is a single point of failure. Reggie (COO) is still warm — ask him who owns the dispatch win now, and build that relationship before renewal.',
        basis: 'ENGAGEMENT GRAPH · REGGIE LAST POSITIVE TOUCH MAY 9',
        valueLabel: 'SINGLE-CHAMPION RISK',
      },
    ],
    risks: [
      { title: 'Board mandates carrier-portal consolidation before renewal', severity: 'high',
        description: 'The "free tool" narrative wins if the real TCO never reaches finance.',
        mitigation: 'TCO one-pager this week.' },
      { title: 'No active champion at renewal', severity: 'high',
        description: 'Priya drove the value story. Without a successor it lands on a cost-cutting desk.',
        mitigation: 'Re-seat via Reggie.' },
      { title: 'Usage decline reads as low value', severity: 'medium',
        description: 'WAU is down 60% — but it tracks to the EMEA stall, not the live workflows.',
        mitigation: 'Segment the usage story.' },
    ],
    stakeholders: [
      { name: 'Reggie Vance', role: 'COO · last warm contact', isChampion: false, renewalHealth: 'warn',
        sentimentNote: 'Last positive contact May 9. Warm but not driving the renewal.' },
      { name: 'Priya Desai', role: 'Ex-champion · VP Operations', status: 'departed', isChampion: true, renewalHealth: 'risk',
        email: 'priya@bevelpoint.com', sentimentNote: 'Departed March. Drove the dispatch-time value story.' },
      { name: 'Tom Kessler', role: 'IT Director · carries consolidation mandate', isChampion: false, renewalHealth: 'warn',
        email: 'tom@bevelpoint.com', sentimentNote: 'Carrying the board portal-consolidation mandate. Potential blocker.' },
    ],
  },

  // ---- BRIDGENOTE — EXPAND (goals green, pilot agreed) ----
  {
    key: 'bridgenote',
    posture: 'expand',
    narrativeLede:
      "Two goals beat plan and the QBR opened a Gong-connector pilot Kavya agreed to champion. You've earned the ask — lead with the expansion; the renewal rides along as a tier bump, not a flat re-sign.",
    postureReason: 'Set from goals green + QBR expansion commitment + second champion emerging',
    targetArrCents: 3800000,        // $38K
    expansionPipeCents: 1200000,    // +$12K
    renewalType: 'Expansion',
    autoRenew: true,
    termNote: '24-month goal',
    lastPriceChangeNote: 'None · first renewal',
    vectors: [
      {
        goalText: 'Unified revenue intelligence across all channels',
        category: 'value',
        description: 'Revenue intelligence unified across all 5 channels',
        currentState: 'ok',
        progress: 0.82, baselineProgress: 0.20, targetProgress: 0.8,
        targetLabel: '5 CHANNELS LIVE · PIPELINE ACCURACY +38% · BEAT TARGET',
        unlocks: "You beat the revenue-intelligence goal — so let's set the next one bigger. Green goals are permission to expand scope.",
        assessmentReason: 'All 5 channel sources live; accuracy up 38%',
      },
      {
        goalText: 'Integrate Gong call data with pipeline forecasting',
        category: 'momentum',
        description: 'Gong connector pilot — Kavya championing',
        currentState: 'warn',
        progress: 0.35, baselineProgress: 0.22, targetProgress: 0.8,
        targetLabel: 'PILOT AGREED AT QBR · KAVYA CHAMPIONING',
        unlocks: "The stalled goal is now the upsell. “Kavya agreed to the pilot — here's the connector tier.”",
        assessmentReason: 'Pilot agreed at QBR (transcript 00:48)',
      },
      {
        goalText: 'Enable RevOps team to build custom attribution models',
        category: 'stakeholder',
        description: 'Finance signed off on the attribution audit trail',
        currentState: 'ok',
        progress: 0.6, baselineProgress: 0.10, targetProgress: 0.7,
        targetLabel: 'FINANCE SIGNED OFF · DANA ENGAGED',
        unlocks: 'Finance already trusts the audit trail. That trust is the wedge for the connector expansion.',
        assessmentReason: 'Dana Liu (Finance) engaged on expansion',
      },
    ],
    plays: [
      {
        kind: 'upsell', isPrimary: true,
        title: 'Propose the Gong-connector tier as the renewal, not an add-on',
        description:
          "Kavya already agreed to champion the pilot. Bundle the connector seats into the renewal so it's one clean motion — a tier bump, not two negotiations.",
        basis: 'QBR COMMITMENT · TRANSCRIPT 00:48 · 30-DAY PILOT',
        valueAmountCents: 1200000, valueLabel: 'ADDS · +$12K ARR',
      },
      {
        kind: 'multi_year',
        title: 'Trade a small discount for a two-year term',
        description:
          'Goals are green and a second champion (Dana, finance) just emerged. Strong moment to lock duration — offer 5% for a 24-month commit.',
        basis: '2 ACTIVE CHAMPIONS · SENTIMENT WARM ↑',
        valueLabel: 'LOCKS · 2-YR TERM',
      },
    ],
    risks: [
      { title: 'Competitor pricing pitched to procurement', severity: 'low',
        description: 'A point tool floated a lower headline price to procurement.',
        mitigation: 'Lead with realized value + switching cost.' },
    ],
    stakeholders: [
      { name: 'Kavya Reddy', role: 'RevOps Manager · pilot champion', isChampion: true, renewalHealth: 'ok',
        sentimentNote: 'Champion. Asked about the Gong connector; hired 2 new RevOps people.' },
      { name: 'Dana Liu', role: 'VP Finance · new champion', isChampion: true, renewalHealth: 'ok',
        email: 'dana@bridgenote.io', sentimentNote: 'Signed off on the attribution audit trail. Engaged on expansion.' },
    ],
  },

  // ---- APERIO — DEFEND (open production escalation) ----
  {
    key: 'aperio',
    posture: 'defend',
    narrativeLede:
      'Webhook reliability issues put the renewal at risk. Re-anchor on the analytics wins that landed, and close the open escalation before the renewal conversation.',
    postureReason: 'Set from at-risk lifecycle + open escalation + reliability signal',
    renewalType: 'At risk',
    autoRenew: false,
    termNote: 'Annual',
    lastPriceChangeNote: 'None',
    vectors: [
      {
        goalText: 'Reliable webhook integration for production workflows',
        category: 'risk_mitigation',
        description: 'Production webhook reliability',
        currentState: 'risk',
        progress: 0.4, baselineProgress: 0.35, targetProgress: 0.9,
        targetLabel: 'OPEN ESCALATION · 2 INCIDENTS THIS MONTH',
        unlocks: "Name the gap first: “we own the reliability miss — here's the fix and the timeline.” Credibility before renewal.",
        assessmentReason: 'Two production incidents this month',
      },
      {
        goalText: 'Zero-downtime data pipeline for analytics dashboard',
        category: 'value',
        description: 'Analytics dashboard uptime since the migration',
        currentState: 'warn',
        progress: 0.62, baselineProgress: 0.30, targetProgress: 0.9,
        targetLabel: 'UPTIME 99.1% · TRENDING UP',
        unlocks: 'The dashboard is delivering — lead with the uptime trend once the webhook fix lands.',
        assessmentReason: 'Uptime recovering post-migration',
      },
    ],
    plays: [
      { kind: 're_anchor', isPrimary: true,
        title: 'Close the open escalation before any renewal talk',
        description: "Liam won't hear a renewal pitch while a production incident is open. Resolve it, then recap the analytics value.",
        basis: 'OPEN ESCALATION · LIAM (VP ENG)', valueAmountCents: 3000000, valueLabel: 'PROTECTS · $30K' },
      { kind: 'de_risk',
        title: 'Bring Nina a reliability SLA commitment',
        description: 'The CEO is watching the incidents. A written reliability SLA de-risks the renewal at the exec level.',
        basis: 'CEO ENGAGED ON INCIDENTS', valueLabel: 'EXEC RISK' },
    ],
    risks: [
      { title: 'Open production escalation unresolved at renewal', severity: 'high',
        description: 'A live incident overshadows the value story.', mitigation: 'Close it this week.' },
      { title: 'Exec sentiment cooling (CEO watching)', severity: 'medium',
        description: 'Nina is tracking the incidents personally.', mitigation: 'Reliability SLA commitment.' },
    ],
    stakeholders: [
      { name: 'Liam Carter', role: 'VP Engineering', isChampion: true, renewalHealth: 'warn',
        sentimentNote: 'Frustrated by the open escalation. Still the primary contact.' },
      { name: 'Nina Tasaki', role: 'CEO', isChampion: false, renewalHealth: 'warn',
        sentimentNote: 'Watching the incidents personally. Exec risk.' },
    ],
  },

  // ---- FOLDWISE — DEFEND (at risk, no goals seeded) ----
  {
    key: 'foldwise',
    posture: 'defend',
    narrativeLede:
      'Account flagged at-risk with no agreed goals on file — the first move is to re-establish what success looks like before the renewal, not to ask for the signature.',
    postureReason: 'Set from at-risk lifecycle + no goals on file',
    renewalType: 'At risk',
    autoRenew: false,
    termNote: 'Annual',
    plays: [
      { kind: 're_anchor', isPrimary: true,
        title: 'Run a value-reset working session, not a renewal call',
        description: "There are no agreed success criteria on file. Re-establish goals with David before the renewal window closes.",
        basis: 'NO GOALS ON FILE', valueAmountCents: 3600000, valueLabel: 'PROTECTS · $36K' },
    ],
    risks: [
      { title: 'No agreed success criteria on file', severity: 'high',
        description: 'Without goals, there is no value story to renew against.', mitigation: 'Value-reset session with David.' },
    ],
    stakeholders: [
      { name: 'David Okonkwo', role: 'Head of RevOps', isChampion: true, renewalHealth: 'warn',
        sentimentNote: 'Responsive but no agreed goals captured yet.' },
    ],
  },

  // ---- PINEGROVE — HOLD (healthy, steady) ----
  {
    key: 'pinegrove',
    posture: 'hold',
    narrativeLede:
      'Healthy and steady — payroll automation is landing and compliance reporting is on track. No upsell yet; protect the value story and re-commit to the next goal.',
    postureReason: 'Set from goals on track + stable sentiment + no expansion trigger',
    renewalType: 'Annual',
    autoRenew: true,
    termNote: 'Annual',
    lastPriceChangeNote: '+4% last renewal',
    vectors: [
      {
        goalText: 'Reduce payroll processing time by 50%',
        category: 'value',
        description: 'Payroll processing time reduction',
        currentState: 'ok',
        progress: 0.7, baselineProgress: 0.25, targetProgress: 0.8,
        targetLabel: 'PROCESSING TIME −44% · ON TRACK',
        unlocks: 'Steady win — re-commit to the 50% target as the next-term goal.',
        assessmentReason: 'On track to the 50% target',
      },
      {
        goalText: 'Implement compliance reporting dashboard',
        category: 'momentum',
        description: 'Compliance reporting dashboard adoption',
        currentState: 'warn',
        progress: 0.5, baselineProgress: 0.20, targetProgress: 0.8,
        targetLabel: 'DASHBOARD LIVE · ADOPTION RAMPING',
        unlocks: 'Adoption is ramping — a check-in keeps it moving toward the next-term goal.',
        assessmentReason: 'Dashboard live; adoption ramping',
      },
    ],
    plays: [
      { kind: 'co_success', isPrimary: true,
        title: 'Agree the next-term goal at the renewal',
        description: 'Goals are on track. Use the renewal to set the next North Star together — keeps the relationship forward-looking.',
        basis: 'GOALS ON TRACK · STABLE SENTIMENT', valueAmountCents: 3200000, valueLabel: 'HOLDS · $32K' },
    ],
    stakeholders: [
      { name: 'Maya Brooks', role: 'Director of Operations', isChampion: true, renewalHealth: 'ok',
        sentimentNote: 'Steady champion. No escalations.' },
    ],
  },

  // ---- QUIETFIELD — HOLD (quietly satisfied, no goals) ----
  {
    key: 'quietfield',
    posture: 'hold',
    narrativeLede:
      'Quietly satisfied — few questions, no escalations. The risk is silence, not churn: re-commit to a goal so the renewal has a value story.',
    postureReason: 'Set from stable sentiment + low engagement + no expansion trigger',
    renewalType: 'Annual',
    autoRenew: true,
    termNote: 'Annual',
    plays: [
      { kind: 'co_success', isPrimary: true,
        title: 'Schedule a value check-in to set a goal',
        description: 'No agreed goals and a quiet account. A check-in establishes a value story before the renewal.',
        basis: 'LOW ENGAGEMENT · NO ESCALATIONS', valueAmountCents: 2000000, valueLabel: 'HOLDS · $20K' },
    ],
    stakeholders: [
      { name: 'Hana Müller', role: 'Director of Engineering Operations', isChampion: true, renewalHealth: 'ok',
        sentimentNote: 'Quiet but satisfied. Few touches.' },
    ],
  },

  // ---- MARLIN — HOLD (mid-onboarding, renewal far off) ----
  {
    key: 'marlin',
    posture: 'hold',
    narrativeLede:
      'Mid-onboarding and on track — the renewal is a formality if the first-quarter automation goal lands. Protect momentum.',
    postureReason: 'Set from onboarding on track + renewal far off',
    renewalType: 'Annual',
    autoRenew: true,
    termNote: 'Annual',
    vectors: [
      {
        goalText: 'Reduce manual data entry by 80% within first quarter',
        category: 'value',
        description: 'Manual data-entry reduction in onboarding',
        currentState: 'warn',
        progress: 0.4, baselineProgress: 0.05, targetProgress: 0.8,
        targetLabel: 'DAY 38 OF 105 · ON TRACK',
        unlocks: 'On track for the 80% target — keep the onboarding cadence and the renewal is a formality.',
        assessmentReason: 'Onboarding day 38 of 105',
      },
    ],
    stakeholders: [
      { name: 'Sarah Chen', role: 'Head of RevOps', isChampion: true, renewalHealth: 'ok',
        sentimentNote: 'Engaged onboarding sponsor.' },
    ],
  },
];

// ---- apply helpers ------------------------------------------------------

async function applyProfile(cfg: CustomerSeed): Promise<string> {
  const customerId = CUSTOMER_IDS[cfg.key];
  const id = profileId(customerId);
  await upsertRenewalProfile({
    id,
    workspaceId: WORKSPACE_ID,
    customerId,
    posture: cfg.posture,
    postureReason: cfg.postureReason,
    narrativeLede: cfg.narrativeLede,
    targetArrCents: cfg.targetArrCents ?? null,
    expansionPipeCents: cfg.expansionPipeCents ?? null,
    renewalType: cfg.renewalType,
    autoRenew: cfg.autoRenew,
    termNote: cfg.termNote,
    lastPriceChangeNote: cfg.lastPriceChangeNote ?? null,
    postureSetBy: 'seed',
  });
  return id;
}

async function applyPlays(cfg: CustomerSeed, pid: string) {
  if (!cfg.plays?.length) return;
  const customerId = CUSTOMER_IDS[cfg.key];
  await deleteRenewalPlaysForProfile({ profileId: pid });
  let i = 0;
  for (const p of cfg.plays) {
    await createRenewalPlay({
      workspaceId: WORKSPACE_ID,
      customerId,
      profileId: pid,
      kind: p.kind,
      posture: cfg.posture,
      title: p.title,
      description: p.description,
      basis: p.basis ?? null,
      valueAmountCents: p.valueAmountCents ?? null,
      valueLabel: p.valueLabel ?? null,
      isPrimary: !!p.isPrimary,
      sortOrder: i++,
    });
  }
}

async function applyRisks(cfg: CustomerSeed, pid: string) {
  if (!cfg.risks?.length) return;
  const customerId = CUSTOMER_IDS[cfg.key];
  await deleteRenewalRiskItemsForProfile({ profileId: pid });
  let i = 0;
  for (const r of cfg.risks) {
    await createRenewalRiskItem({
      workspaceId: WORKSPACE_ID,
      customerId,
      profileId: pid,
      title: r.title,
      description: r.description,
      severity: r.severity,
      mitigation: r.mitigation ?? null,
      sortOrder: i++,
    });
  }
}

// Ensure every goal a vector needs exists (creates it if seed-data didn't),
// capturing the inserted id directly — a re-read won't see writes from this
// same process (the query layer serves a cached result). Returns the merged
// goal list (existing + newly created).
async function ensureGoals(
  cfg: CustomerSeed,
  goals: Array<{ id: string; text: string }>
): Promise<Array<{ id: string; text: string }>> {
  if (!cfg.vectors?.length) return goals;
  const customerId = CUSTOMER_IDS[cfg.key];
  const merged = [...goals];
  const have = (text: string) => merged.some(g => g.text.toLowerCase() === text.toLowerCase());
  const needed = Array.from(new Set(cfg.vectors.map(v => v.goalText)));
  let order = goals.length + 1;
  for (const text of needed) {
    if (have(text)) continue;
    try {
      const res = await createGoalPublic({ workspaceId: WORKSPACE_ID, customerId, text, status: 'active', sortOrder: order++ });
      const id = (res.data as any)?.goal_insert?.id;
      if (id) merged.push({ id, text });
    } catch (e: any) {
      console.log(`    goal create error (${cfg.key}):`, e.message?.substring(0, 50));
    }
  }
  return merged;
}

async function applyVectors(
  cfg: CustomerSeed,
  goals: Array<{ id: string; text: string }>,
  existingVectorIds: string[]
) {
  if (!cfg.vectors?.length) return;
  const customerId = CUSTOMER_IDS[cfg.key];

  // Idempotency: drop existing vectors for this customer first.
  for (const id of existingVectorIds) {
    try { await deleteProgressVector({ id }); } catch { /* ignore */ }
  }

  for (const v of cfg.vectors) {
    const goal = goals.find(g => g.text.toLowerCase() === v.goalText.toLowerCase());
    if (!goal) {
      console.log(`    ⚠ no goal for "${v.goalText}" (${cfg.key}) — skipping vector`);
      continue;
    }
    try {
      const res = await createProgressVector({
        workspaceId: WORKSPACE_ID,
        customerId,
        goalId: goal.id,
        category: v.category,
        description: v.description,
        currentState: v.currentState,
        progress: v.progress,
        targetProgress: v.targetProgress,
        targetLabel: v.targetLabel,
        unlocks: v.unlocks,
        assessmentReason: v.assessmentReason,
        lastAssessedBy: 'seed',
      });
      const vid = (res.data as any)?.progressVector_insert?.id;
      if (vid) {
        await updateProgressVectorBaseline({ id: vid, baselineProgress: v.baselineProgress });
      }
    } catch (e: any) {
      console.log(`    vector error (${cfg.key}/${v.goalText}):`, e.message?.substring(0, 60));
    }
  }
}

async function applyStakeholders(
  cfg: CustomerSeed,
  existing: Array<{ id: string; name: string }>
) {
  if (!cfg.stakeholders?.length) return;
  const customerId = CUSTOMER_IDS[cfg.key];

  for (const s of cfg.stakeholders) {
    let id = existing.find(e => e.name.toLowerCase() === s.name.toLowerCase())?.id;
    if (!id) {
      try {
        const res = await createStakeholderPublic({
          workspaceId: WORKSPACE_ID,
          customerId,
          name: s.name,
          email: s.email ?? null,
          role: s.role,
        });
        id = (res.data as any)?.stakeholder_insert?.id;
      } catch (e: any) {
        console.log(`    stakeholder create error (${s.name}):`, e.message?.substring(0, 50));
        continue;
      }
    }
    if (!id) continue;
    // Single PUBLIC call sets renewal status + champion + health (USER-level
    // UpdateStakeholder isn't callable from the unauthenticated seed).
    try {
      await updateStakeholderRenewal({
        id,
        isChampion: !!s.isChampion,
        renewalHealth: s.renewalHealth ?? null,
        status: s.status ?? 'active',
      });
    } catch (e: any) {
      console.log(`    stakeholder renewal-update error (${s.name}):`, e.message?.substring(0, 50));
    }
  }
}

async function run() {
  for (const cfg of SEED) {
    const customerId = CUSTOMER_IDS[cfg.key];
    console.log(`\n• ${cfg.key} → ${cfg.posture.toUpperCase()}`);
    try {
      let refs = (await getCustomerSeedRefs({ customerId })).data?.customer as any;
      if (!refs) { console.log('  ⚠ customer not found — run seed-data.ts first'); continue; }

      let goals = (refs.goals_on_customer || []).map((g: any) => ({ id: g.id, text: g.text }));
      const stakeholders = (refs.stakeholders_on_customer || []).map((s: any) => ({ id: s.id, name: s.name }));
      const existingVectorIds = (refs.progressVectors_on_customer || []).map((v: any) => v.id);

      const pid = await applyProfile(cfg);
      console.log('  ✓ profile');
      await applyPlays(cfg, pid);
      if (cfg.plays?.length) console.log(`  ✓ ${cfg.plays.length} play(s)`);
      await applyRisks(cfg, pid);
      if (cfg.risks?.length) console.log(`  ✓ ${cfg.risks.length} risk(s)`);

      // Make sure the goals the vectors reference exist (captures new ids).
      goals = await ensureGoals(cfg, goals);
      await applyVectors(cfg, goals, existingVectorIds);
      if (cfg.vectors?.length) console.log(`  ✓ ${cfg.vectors.length} vector(s)`);
      await applyStakeholders(cfg, stakeholders);
      if (cfg.stakeholders?.length) console.log(`  ✓ ${cfg.stakeholders.length} stakeholder(s)`);
    } catch (e: any) {
      console.log(`  ❌ ${cfg.key} failed:`, e.message?.substring(0, 120));
    }
  }
  console.log('\n✅ Renewals seed complete.\n');
}

run().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
