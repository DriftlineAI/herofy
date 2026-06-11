// Default content seeded when a new workspace is created
// These provide a starting point that users can customize

export interface DefaultHandbookDoc {
  slug: string;
  title: string;
  description: string;
  body: string;
  blastRadius: 'low' | 'medium' | 'high';
}

export interface DefaultPlaybookMilestone {
  title: string;
  ownerSide: 'us' | 'customer' | 'joint';
  durationDays: number;
  description: string;
  sortOrder: number;
}

export interface DefaultPlaybook {
  name: string;
  archetype: string;
  fitNote: string;
  scenario: 'onboarding' | 'renewal' | 'risk';
  milestones: DefaultPlaybookMilestone[];
}

// Default handbook documents - these teach Sidekick how your CS process works
export const DEFAULT_HANDBOOK_DOCS: DefaultHandbookDoc[] = [
  {
    slug: 'going-dark',
    title: 'How We Define Going Dark',
    description: 'Criteria for identifying customers who have gone silent',
    body: `# Going Dark Definition

A customer is "going dark" when:

1. No response to 2+ outreach attempts over 7 days
2. Engagement score dropped >30% in the last 14 days
3. Key stakeholders haven't logged in for 10+ days
4. Open commitments are overdue with no communication

## Response Protocol

1. Escalate to champion's backup contact
2. Try alternative channels (Slack if email is primary)
3. Surface as priority need if no response in 48h

## When to Escalate

- After 3 failed contact attempts across multiple channels
- If account is >$50K ARR
- If renewal is within 90 days`,
    blastRadius: 'medium',
  },
  {
    slug: 'renewal-readiness',
    title: 'How We Think About Renewal Readiness',
    description: 'Framework for assessing renewal probability',
    body: `# Renewal Readiness Framework

## Ready (Green)
- Champion actively advocating
- Usage metrics trending up or stable
- No open escalations
- Budget confirmed or historically auto-renews
- Multiple stakeholders engaged

## Tracking (Yellow)
- Some positive signals but gaps exist
- Need more stakeholder coverage
- Usage stable but not growing
- Champion engaged but not advocating
- No budget discussion yet (within 60 days)

## At Risk (Red)
- Champion departed or gone quiet
- Usage declining >20% quarter over quarter
- Open escalations or unresolved complaints
- Budget discussions, downgrade inquiries, or competitor mentions
- Single point of contact with no backup

## Timeline Guidelines
- Start renewal conversation at T-90 days for Enterprise
- Start at T-60 days for Mid-Market
- Start at T-30 days for SMB/self-serve upgrades`,
    blastRadius: 'high',
  },
  {
    slug: 'handoff-quality',
    title: 'Sales to CS Handoff Quality Standards',
    description: 'What makes a good handoff and how to identify risks early',
    body: `# Handoff Quality Standards

## Required Information
- Primary stakeholders and their roles
- Technical requirements and constraints
- Sales commitments (explicit and implied)
- Success criteria from customer's perspective
- Timeline expectations and any hard deadlines
- Budget and contract details

## Red Flags to Surface
- Unrealistic timelines promised (flag anything <30 days for Enterprise)
- Technical requirements not validated by SE
- Missing executive sponsor
- Vague or unmeasurable success criteria
- Discount or special terms not documented
- Customer expressed concerns during sales process

## Quality Checklist
Before accepting a handoff, verify:
- [ ] At least 2 stakeholder contacts documented
- [ ] Technical requirements reviewed by implementation team
- [ ] Success metrics are specific and measurable
- [ ] Timeline aligns with standard playbook (+/- 20%)
- [ ] No undocumented commitments discovered`,
    blastRadius: 'high',
  },
  {
    slug: 'escalation-handling',
    title: 'How We Handle Escalations',
    description: 'Process for managing and resolving customer escalations',
    body: `# Escalation Handling

## Severity Levels

### P1 - Critical
- Customer's business is down or severely impacted
- Response within 1 hour
- All hands until resolved
- Executive notification required

### P2 - High
- Major feature broken, workaround exists
- Response within 4 hours
- Daily updates until resolved

### P3 - Medium
- Feature issue with easy workaround
- Response within 1 business day
- Updates every 2-3 days

## Escalation Response Framework

1. **Acknowledge** - Respond immediately, even if just to say you're looking into it
2. **Investigate** - Gather all context before promising solutions
3. **Communicate** - Set clear expectations on timeline and next steps
4. **Resolve** - Fix the issue and confirm with customer
5. **Follow-up** - Check in 48h later to ensure satisfaction

## When to Involve Leadership
- Any P1 escalation
- Customer threatens churn or legal action
- Issue persists beyond SLA
- Escalation from executive stakeholder`,
    blastRadius: 'high',
  },
];

// Default playbooks - templates for onboarding and CS workflows
export const DEFAULT_PLAYBOOKS: DefaultPlaybook[] = [
  {
    name: 'Standard SaaS Onboarding',
    archetype: 'Onboarding',
    scenario: 'onboarding',
    fitNote: 'Best for $25K-$100K ARR accounts with straightforward implementations',
    milestones: [
      {
        title: 'Kickoff Call',
        ownerSide: 'us',
        durationDays: 7,
        description: 'Initial alignment on goals, timeline, success criteria, and key stakeholders',
        sortOrder: 1,
      },
      {
        title: 'Technical Setup',
        ownerSide: 'customer',
        durationDays: 14,
        description: 'API keys generated, environments configured, initial integration completed',
        sortOrder: 2,
      },
      {
        title: 'Data Migration',
        ownerSide: 'joint',
        durationDays: 21,
        description: 'Historical data imported, validated, and verified by customer',
        sortOrder: 3,
      },
      {
        title: 'User Training',
        ownerSide: 'us',
        durationDays: 28,
        description: 'Admin training and end-user training sessions completed',
        sortOrder: 4,
      },
      {
        title: 'Go-Live',
        ownerSide: 'joint',
        durationDays: 35,
        description: 'Production deployment, cutover from legacy system, success criteria verified',
        sortOrder: 5,
      },
    ],
  },
  {
    name: 'Enterprise Implementation',
    archetype: 'Onboarding',
    scenario: 'onboarding',
    fitNote: 'For $100K+ ARR with complex integrations, security reviews, or multiple stakeholder groups',
    milestones: [
      {
        title: 'Executive Alignment',
        ownerSide: 'us',
        durationDays: 7,
        description: 'C-level sponsor identified and aligned on vision and success metrics',
        sortOrder: 1,
      },
      {
        title: 'Security Review',
        ownerSide: 'customer',
        durationDays: 21,
        description: 'InfoSec review completed, security questionnaire approved, compliance verified',
        sortOrder: 2,
      },
      {
        title: 'Technical Discovery',
        ownerSide: 'joint',
        durationDays: 28,
        description: 'Architecture review, integration mapping, detailed requirements finalized',
        sortOrder: 3,
      },
      {
        title: 'Custom Development',
        ownerSide: 'us',
        durationDays: 56,
        description: 'Custom integrations built, configurations completed, internal QA passed',
        sortOrder: 4,
      },
      {
        title: 'Pilot Launch',
        ownerSide: 'joint',
        durationDays: 70,
        description: 'Limited rollout to pilot group, feedback collected, adjustments made',
        sortOrder: 5,
      },
      {
        title: 'Full Rollout',
        ownerSide: 'joint',
        durationDays: 84,
        description: 'Company-wide deployment, training completed, success criteria achieved',
        sortOrder: 6,
      },
    ],
  },
  {
    name: 'Renewal Prep',
    archetype: 'CS Play',
    scenario: 'renewal',
    fitNote: 'For accounts entering the renewal window — validate outcomes, confirm budget, secure exec sponsor',
    milestones: [
      {
        title: 'Outcome Audit',
        ownerSide: 'us',
        durationDays: 7,
        description: 'Compile proof points for value delivered since last renewal. Identify gaps that could surface as objections.',
        sortOrder: 1,
      },
      {
        title: 'Champion Alignment',
        ownerSide: 'us',
        durationDays: 14,
        description: 'Confirm champion is still engaged and willing to advocate internally. Surface any internal pressure or competing priorities.',
        sortOrder: 2,
      },
      {
        title: 'Business Review',
        ownerSide: 'joint',
        durationDays: 21,
        description: 'Executive-level review of outcomes, roadmap, and value. Secure internal buy-in for renewal decision.',
        sortOrder: 3,
      },
      {
        title: 'Commercial Discussion',
        ownerSide: 'us',
        durationDays: 30,
        description: 'Introduce renewal terms. Surface any budget or headcount concerns early. Align on expansion opportunities.',
        sortOrder: 4,
      },
      {
        title: 'Renewal Closed',
        ownerSide: 'joint',
        durationDays: 45,
        description: 'Contract signed, order processed, next-year success criteria documented.',
        sortOrder: 5,
      },
    ],
  },
  {
    name: 'At-Risk Recovery',
    archetype: 'CS Play',
    scenario: 'risk',
    fitNote: 'For customers showing churn signals - engagement drop, champion departure, or escalations',
    milestones: [
      {
        title: 'Situation Assessment',
        ownerSide: 'us',
        durationDays: 2,
        description: 'Review all signals, identify root cause, document current state',
        sortOrder: 1,
      },
      {
        title: 'Stakeholder Outreach',
        ownerSide: 'us',
        durationDays: 5,
        description: 'Connect with all known contacts, identify new stakeholders if champion departed',
        sortOrder: 2,
      },
      {
        title: 'Executive Alignment',
        ownerSide: 'joint',
        durationDays: 10,
        description: 'Schedule call with decision-maker, present value summary and recovery plan',
        sortOrder: 3,
      },
      {
        title: 'Quick Wins',
        ownerSide: 'us',
        durationDays: 14,
        description: 'Deliver 2-3 immediate improvements or resolve outstanding issues',
        sortOrder: 4,
      },
      {
        title: 'Success Review',
        ownerSide: 'joint',
        durationDays: 30,
        description: 'Present progress, confirm renewed commitment, document lessons learned',
        sortOrder: 5,
      },
    ],
  },
];

// Default voice documents - these define how Sidekick communicates
export interface DefaultVoiceDoc {
  slug: string;
  title: string;
  description: string;
  body: string;
  kind: 'VOICE_CORE' | 'VOICE_FOUNDATION' | 'VOICE_SCENARIO';
  blastRadius: 'low' | 'medium' | 'high';
  pinned?: boolean;
  chapterNum?: number;
  affectsSurfaces?: string;
}

export const DEFAULT_VOICE_DOCS: DefaultVoiceDoc[] = [
  {
    slug: 'core-voice',
    title: 'A thoughtful coworker who\'s been through it before.',
    kind: 'VOICE_CORE',
    pinned: true,
    description: 'The foundation for how Sidekick always sounds.',
    body: `Sidekick speaks like a seasoned CSM writing to a peer at the customer. Direct but not curt. We say "I noticed" not "data indicates". We never hedge with "perhaps" or "it might be worth considering".

If we don't know something, we ask. We default to concrete examples over abstractions — if someone says "things are tense" we ask which conversation, with whom.

"We err shorter, not longer. Exclamation points only in genuine celebration."

We use the customer's own words when they've been clear about what they want. We never invent metrics, dates, or commitments that didn't come from a real source.

Tone signals we lean on: plain English, contractions, one idea per sentence, a comfortable willingness to not say something if it isn't useful.

⌐ NEVER DRAFT
- "Just bumping this"
- "Hope all's well!"
- "Happy to jump on a quick call"
- "Per my last email"
- "Circling back"`,
    blastRadius: 'high',
    affectsSurfaces: JSON.stringify(['SIDEKICK_TIP', 'EMAIL_DRAFT', 'HITL_QUESTION', 'PLAN_STEP']),
  },
  {
    slug: 'voice-relationships',
    title: 'How we think about relationships',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 1,
    description: 'Earn trust by being specific.',
    body: `A relationship is built in small acts of remembering, not big moments of celebration. We earn trust by being specific.

When suggesting outreach, we frame around their goals, not our agenda. When drafting emails, we reference specific prior conversations. When asking questions, we show we've done our homework.

We never say "checking in" without a reason. If there's nothing to say, we don't say it.`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['EMAIL_DRAFT', 'SIDEKICK_TIP']),
  },
  {
    slug: 'voice-onboarding',
    title: 'How we onboard customers',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 2,
    description: 'Make ourselves less necessary, not more.',
    body: `Onboarding ends when they don't need us. Every check-in is a chance to make ourselves less necessary — not more.

We celebrate their wins, not ours. "Your team got the integration live" not "We got the integration live."

If they're stuck, we don't just offer help — we diagnose why and offer something concrete.`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['PLAN_STEP', 'EMAIL_DRAFT', 'SIDEKICK_TIP']),
  },
  {
    slug: 'voice-attention',
    title: 'How we prioritize attention',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 3,
    description: 'The cost of unneeded check-ins is higher than you think.',
    body: `Not every signal deserves a touchpoint. The cost of a check-in nobody needed is higher than the benefit of one they didn't miss.

When deciding what to surface, we ask: "Would they thank us for this?" If the answer is uncertain, we wait.

We surface risk, not noise. A usage dip is information, not an emergency.`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['SIDEKICK_TIP', 'HITL_QUESTION']),
  },
  {
    slug: 'voice-customer-cares',
    title: 'What our customers care about',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 4,
    description: 'Make them look smart to their boss.',
    body: `They care about looking smart to their own boss. Everything we draft should make that easier — never the opposite.

We never put them in a position where they have to explain our behavior. If we made a mistake, we own it.

When suggesting actions, we consider: will this help their career or make them look desperate?`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['EMAIL_DRAFT', 'HITL_QUESTION', 'PLAN_STEP']),
  },
  {
    slug: 'voice-success',
    title: 'How we define success',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 5,
    description: 'Get the outcome right, renewal follows.',
    body: `Success is the outcome they came for — not the renewal. If we get the first right, the second follows.

When measuring progress, we use their goals, not ours. "You wanted X by Q2" not "We need to hit Y for renewal."

We never conflate our revenue goals with their success criteria.`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['SIDEKICK_TIP', 'PLAN_STEP']),
  },
  {
    slug: 'voice-going-dark',
    title: 'How we define going dark',
    kind: 'VOICE_FOUNDATION',
    chapterNum: 6,
    description: 'Silence is a question, not a verdict.',
    body: `Silence isn't always trouble. We treat 14 days as a question, not a verdict — the right move depends on what was happening before.

If we have something specific to offer — a doc they asked about, an answer to an open question — we lead with that, not with our absence.

We acknowledge the silence without making it the subject. "I owe you X" works. "Just checking in" doesn't — it tells them we have nothing to say.

We give them a graceful out. "If you've already solved this, no need to reply" tells them we respect their time more than we want a response.

⌐ NEVER, IN THIS SCENARIO
- "Bumping this"
- "Wanted to make sure you saw"
- "I know you're busy, but"
- Any reference to renewal, expansion, or commercial outcome.`,
    blastRadius: 'medium',
    affectsSurfaces: JSON.stringify(['EMAIL_DRAFT', 'SIDEKICK_TIP', 'HITL_QUESTION']),
  },
];
