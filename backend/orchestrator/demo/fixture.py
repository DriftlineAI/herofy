"""Demo fixture — the single source of truth for the Northcrest demo workspace.

Content is transcribed from docs/demo_docs/demo_customers_notion.md (narratives) and
frontend/demo/constants.ts (roster, emails, Notion ids). Data-only: no DB calls live
here. The seeder (seeder.py) turns these dataclasses into real rows.

Time is expressed in offsets, not absolute timestamps, so the workspace always looks
"current" whenever it is seeded:
  - interaction.days_ago      → occurredAt = now - days_ago
  - meeting.days_from_now     → scheduledAt = now + days_from_now (negative = past)
  - milestone.target_days     → targetDate = today + target_days (negative = past/done)

Lanes (one comprehensive workspace; see DEMO_BUILD_PLAN.md):
  lane1 = fresh handoffs (pre-baked brief + plan)   lane2 = established portfolio
  bg    = portfolio padding (light data)
"""

from dataclasses import dataclass, field

# ── leaf dataclasses ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stakeholder:
    name: str
    role: str
    email: str
    is_champion: bool = False
    renewal_health: str | None = None       # SignalState: ok | warn | risk
    status: str = "active"                   # StakeholderStatus: active | departed


@dataclass(frozen=True)
class Goal:
    text: str
    status: str = "active"                   # GoalStatus: active | achieved | dropped
    is_primary: bool = False


@dataclass(frozen=True)
class Milestone:
    title: str
    status: str = "not_started"              # MilestoneStatus
    owner_side: str = "joint"                # OwnerSide: us | customer | joint
    target_days: int | None = None           # offset from today (negative = past)
    goal_index: int | None = None            # link to goals[i]
    goal_rationale: str | None = None


@dataclass(frozen=True)
class Interaction:
    days_ago: float
    direction: str                           # us | customer | internal
    body: str
    sender_name: str | None = None
    subject: str | None = None
    channel: str = "email"                    # email | slack | meeting | note


@dataclass(frozen=True)
class Thread:
    key: str                                  # stable per-customer key (id + reset)
    subject: str
    interactions: list[Interaction]
    channel: str = "email"
    thread_type: str = "customer"            # customer | sidekick | internal
    status: str = "open"                      # open | resolved | archived


@dataclass(frozen=True)
class Meeting:
    key: str
    title: str
    days_from_now: float                      # negative = past
    status: str = "scheduled"                # scheduled | completed | cancelled | no_show
    duration_minutes: int = 30
    attendees_ours: list[str] = field(default_factory=list)
    attendees_theirs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Need:
    key: str
    type: str                                 # NeedType
    headline: str
    priority_rank: int
    lede: str | None = None
    reasoning: str | None = None
    thread_key: str | None = None             # link to one of this customer's threads


@dataclass(frozen=True)
class Handoff:
    """Pre-baked sales→CS handoff brief + onboarding plan (lane1, no live LLM)."""
    body: str
    day_current: int
    day_total: int
    confidence: str
    risks: str
    sales_commitments: list[dict]             # serialized to JSON
    technical_context: dict                   # serialized to JSON
    plan_headline: str
    plan_rationale: str
    plan_duration_label: str
    plan_milestones: list[dict]               # serialized to JSON


@dataclass(frozen=True)
class SentimentPoint:
    """One backdated sentiment reading. Seeds a kind=sentiment Signal so the customer
    detail / RightRail sparkline has a real trajectory to plot (state: ok | warn | risk
    → 1.0 | 0.5 | 0.0). `note` becomes the signal sentence/evidence; a generic line is
    used when omitted."""
    days_ago: int
    state: str                                # ok | warn | risk
    note: str | None = None


@dataclass(frozen=True)
class Customer:
    slug: str
    name: str
    domain: str
    one_liner: str
    tier: str
    arr_cents: int
    lifecycle: str                            # CustomerLifecycle
    lane: str                                 # lane1 | lane2 | bg
    days_to_renewal: int | None = None
    onboarding_day_current: int | None = None
    onboarding_day_total: int | None = None
    health: str | None = None                 # RelationshipHealth
    health_score: int | None = None
    health_reason: str | None = None
    renewal_readiness: str | None = None      # RenewalReadiness
    notion_page_id: str | None = None
    stakeholders: list[Stakeholder] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    meetings: list[Meeting] = field(default_factory=list)
    needs: list[Need] = field(default_factory=list)
    handoff: Handoff | None = None
    # Explicit sentiment trajectory. When empty, the seeder derives a series from
    # `health` so every customer still shows a sparkline (see _sentiment_series).
    sentiment: list[SentimentPoint] = field(default_factory=list)


# ── workspace defaults: playbooks / handbook / voice ──────────────────────────


@dataclass(frozen=True)
class PlaybookMilestone:
    title: str
    owner_side: str
    duration_days: int
    description: str
    sort_order: int


@dataclass(frozen=True)
class Playbook:
    slug: str
    name: str
    archetype: str
    fit_note: str
    scenario: str                             # onboarding | renewal | risk
    milestones: list[PlaybookMilestone]


@dataclass(frozen=True)
class HandbookDoc:
    slug: str
    title: str
    body: str
    blast_radius: str = "medium"
    kind: str = "DOCUMENT"                    # HandbookDocKind
    pinned: bool = False
    chapter_num: int | None = None
    affects_surfaces: list[str] = field(default_factory=list)


PLAYBOOKS: list[Playbook] = [
    Playbook(
        slug="standard-onboarding", name="Standard SaaS Onboarding", archetype="Onboarding",
        scenario="onboarding",
        fit_note="Best for $25K–$100K ARR accounts with straightforward implementations.",
        milestones=[
            PlaybookMilestone("Kickoff Call", "us", 7, "Align on goals, timeline, success criteria, and stakeholders.", 1),
            PlaybookMilestone("Technical Setup", "customer", 14, "API keys, environments, initial integration.", 2),
            PlaybookMilestone("Data Migration", "joint", 21, "Historical data imported, validated, verified.", 3),
            PlaybookMilestone("User Training", "us", 28, "Admin + end-user training sessions.", 4),
            PlaybookMilestone("Go-Live", "joint", 35, "Production cutover; success criteria verified.", 5),
        ],
    ),
    Playbook(
        slug="enterprise-implementation", name="Enterprise Implementation", archetype="Onboarding",
        scenario="onboarding",
        fit_note="For $100K+ ARR with complex integrations, security review, or many stakeholders.",
        milestones=[
            PlaybookMilestone("Executive Alignment", "us", 7, "Confirm exec sponsor and outcomes.", 1),
            PlaybookMilestone("Security Review", "customer", 21, "InfoSec sign-off on data handling.", 2),
            PlaybookMilestone("Technical Discovery", "joint", 28, "Map systems, owners, constraints.", 3),
            PlaybookMilestone("Custom Development", "us", 56, "Build the committed connectors.", 4),
            PlaybookMilestone("Pilot Launch", "joint", 70, "Limited production pilot.", 5),
            PlaybookMilestone("Full Rollout", "joint", 84, "Org-wide go-live.", 6),
        ],
    ),
    Playbook(
        slug="renewal-prep", name="Renewal Prep", archetype="CS Play", scenario="renewal",
        fit_note="For accounts entering the renewal window — validate outcomes, confirm budget, secure sponsor.",
        milestones=[
            PlaybookMilestone("Outcome Audit", "us", 7, "Quantify value delivered to date.", 1),
            PlaybookMilestone("Champion Alignment", "us", 14, "Confirm champion is advocating internally.", 2),
            PlaybookMilestone("Business Review", "joint", 21, "Exec QBR on outcomes and roadmap.", 3),
            PlaybookMilestone("Commercial Discussion", "us", 30, "Pricing, terms, multi-year options.", 4),
            PlaybookMilestone("Renewal Closed", "joint", 45, "Signed renewal.", 5),
        ],
    ),
    Playbook(
        slug="at-risk-recovery", name="At-Risk Recovery", archetype="CS Play", scenario="risk",
        fit_note="For customers showing churn signals — engagement drop, champion departure, escalations.",
        milestones=[
            PlaybookMilestone("Situation Assessment", "us", 2, "Diagnose what actually changed.", 1),
            PlaybookMilestone("Stakeholder Outreach", "us", 5, "Re-establish contact with the champion.", 2),
            PlaybookMilestone("Executive Alignment", "joint", 10, "Get the right execs in the room.", 3),
            PlaybookMilestone("Quick Wins", "us", 14, "Ship visible improvements fast.", 4),
            PlaybookMilestone("Success Review", "joint", 30, "Confirm trajectory has turned.", 5),
        ],
    ),
]

HANDBOOK_DOCS: list[HandbookDoc] = [
    HandbookDoc(
        slug="going-dark", title="How We Define Going Dark", blast_radius="medium",
        body=("A customer is 'going dark' when there's no response to 2+ outreach attempts over 7 days, "
              "or no inbound contact for longer than their lifecycle norm. Usage may continue — silence is "
              "about the relationship, not the product. Re-engage with a low-friction, async-first touch."),
    ),
    HandbookDoc(
        slug="renewal-readiness", title="How We Think About Renewal Readiness", blast_radius="high",
        body=("Ready (green): champion actively advocating, usage trending up, outcomes quantified. "
              "Tracking (yellow): value real but narrative not yet built. At-risk (red): competing priority, "
              "budget scrutiny, or a consolidation threat. Start the renewal play at the first yellow."),
    ),
    HandbookDoc(
        slug="handoff-quality", title="Sales→CS Handoff Quality Standards", blast_radius="high",
        body=("A complete handoff names the primary stakeholders and roles, the concrete success criteria, "
              "every sales commitment (with scope and owner), the technical context, and any hidden risk "
              "surfaced in the close. If a commitment isn't written down, it didn't happen."),
    ),
    HandbookDoc(
        slug="escalation-handling", title="How We Handle Escalations", blast_radius="high",
        body=("P1 (critical, response within 1 hour): production impact or exec-level anger. Acknowledge fast, "
              "own the timeline, over-communicate. After resolution, deliver a postmortem and the concrete "
              "changes — follow-through is what rebuilds trust, not the apology."),
    ),
]

VOICE_DOCS: list[HandbookDoc] = [
    HandbookDoc(
        slug="core-voice", title="A thoughtful coworker who's been through it before.",
        kind="VOICE_CORE", blast_radius="high", pinned=True,
        affects_surfaces=["SIDEKICK_TIP", "EMAIL_DRAFT", "HITL_QUESTION", "PLAN_STEP"],
        body=("Sidekick speaks like a seasoned CSM writing to a peer at the customer: warm, direct, specific, "
              "never corporate. Short sentences. No hype, no filler, no apologizing twice."),
    ),
    HandbookDoc(
        slug="voice-relationships", title="How we think about relationships",
        kind="VOICE_FOUNDATION", chapter_num=1, affects_surfaces=["EMAIL_DRAFT", "SIDEKICK_TIP"],
        body="A relationship is built in small acts of remembering, not big moments of celebration.",
    ),
    HandbookDoc(
        slug="voice-onboarding", title="How we onboard customers",
        kind="VOICE_FOUNDATION", chapter_num=2, affects_surfaces=["PLAN_STEP", "EMAIL_DRAFT", "SIDEKICK_TIP"],
        body="Onboarding ends when they don't need us. Optimize for their independence, not our touchpoints.",
    ),
    HandbookDoc(
        slug="voice-attention", title="How we prioritize attention",
        kind="VOICE_FOUNDATION", chapter_num=3, affects_surfaces=["SIDEKICK_TIP", "HITL_QUESTION"],
        body="Not every signal deserves a touchpoint. Spend attention where it changes an outcome.",
    ),
    HandbookDoc(
        slug="voice-customer-cares", title="What our customers care about",
        kind="VOICE_FOUNDATION", chapter_num=4, affects_surfaces=["EMAIL_DRAFT", "HITL_QUESTION", "PLAN_STEP"],
        body="They care about looking smart to their own boss. Make the champion the hero.",
    ),
    HandbookDoc(
        slug="voice-success", title="How we define success",
        kind="VOICE_FOUNDATION", chapter_num=5, affects_surfaces=["SIDEKICK_TIP", "PLAN_STEP"],
        body="Success is the outcome they came for — not the renewal. The renewal follows the outcome.",
    ),
    HandbookDoc(
        slug="voice-going-dark", title="How we define going dark",
        kind="VOICE_FOUNDATION", chapter_num=6, affects_surfaces=["EMAIL_DRAFT", "SIDEKICK_TIP", "HITL_QUESTION"],
        body="Silence isn't always trouble. Re-open the door without making them feel chased.",
    ),
]


# ── workspace metadata ────────────────────────────────────────────────────────

WORKSPACE_NAME = "Northcrest"
WORKSPACE_SLUG = "northcrest"
WORKSPACE_VALUE_PROP = (
    "B2B SaaS workflow automation for operations and RevOps teams — streamline data "
    "pipelines, automate sales↔CS handoffs, and surface customer-health signals."
)


# ── the roster ────────────────────────────────────────────────────────────────

CUSTOMERS: list[Customer] = [
    # ===== LANE 1 — fresh handoffs (pre-baked brief + plan) =====================
    Customer(
        slug="marlin-insights", name="Marlin Insights", domain="marlininsights.com",
        one_liner="Series A product analytics for ecommerce", tier="Mid-Market",
        arr_cents=1_800_000, lifecycle="handoff", lane="lane1", days_to_renewal=365,
        onboarding_day_current=0, onboarding_day_total=60,
        health="healthy", health_score=74,
        health_reason="Fresh handoff; strong fit, but CEO is skeptical of integration tools.",
        notion_page_id="a38f7c2b4dd8418e8bd7926778b6c3ac",
        stakeholders=[
            Stakeholder("Sarah Chen", "Head of RevOps", "sarah.chen@marlininsights.com", is_champion=True),
            Stakeholder("Jamal Foster", "Director of Data", "jamal.foster@marlininsights.com"),
        ],
        goals=[
            Goal("RevOps ships revenue plays without engineering for every change", is_primary=True),
            Goal("Sync HubSpot opportunity + lifecycle data into Snowflake"),
            Goal("Trigger Outreach sequences automatically from intent signals"),
        ],
        milestones=[
            Milestone("Kickoff call", "not_started", "us", target_days=3, goal_index=0),
            Milestone("Snowflake schema review with Jamal", "not_started", "joint", target_days=10, goal_index=1),
            Milestone("Outreach connector live", "not_started", "us", target_days=30, goal_index=2,
                      goal_rationale="Sarah is counting on this for phase two; Priya scoped it at ~2 weeks."),
        ],
        meetings=[
            Meeting("kickoff", "Marlin Insights — Kickoff", days_from_now=3, status="scheduled",
                    attendees_ours=["Devon Patel"], attendees_theirs=["Sarah Chen", "Jamal Foster"]),
        ],
        threads=[
            Thread("pre-kickoff", "Quick question before kickoff", channel="email", interactions=[
                Interaction(2, "customer", sender_name="Marlin — Sarah Chen",
                            subject="Quick question before kickoff",
                            body="Before Thursday — can Northcrest write back to HubSpot once the Snowflake "
                                 "model is built, or is it read-only into Snowflake? That writeback is the "
                                 "phase-two unlock for us."),
            ]),
        ],
        needs=[
            Need("handoff", "new_handoff", "Review handoff brief for Marlin Insights", priority_rank=2,
                 lede="Marcus → Devon. Outreach connector committed; CEO skeptical.",
                 reasoning="New deal closed last week; brief + plan are drafted and ready for review.",
                 thread_key="pre-kickoff"),
        ],
        handoff=Handoff(
            body=("Marlin wants onboarding that feels enterprise-reliable without enterprise process. Core use "
                  "case: sync HubSpot opportunity + lifecycle data into Snowflake, then trigger Outreach off "
                  "intent signals. Sarah's north star: 'RevOps ships revenue plays without asking engineering.' "
                  "They chose us over Workato (too IT-led) and an in-house Hightouch build because we committed "
                  "to an Outreach connector. Sarah prefers async/Slack and dislikes standing meetings."),
            day_current=0, day_total=60, confidence="high",
            risks="CEO is skeptical of integration tools — week-one reliability and responsiveness matter a lot.",
            sales_commitments=[
                {"what": "Outreach connector shipped", "scope": "~2 weeks (scoped by Priya)", "owner": "Priya",
                 "due": "end of next month"},
            ],
            technical_context={"source": "HubSpot", "warehouse": "Snowflake", "activation": "Outreach",
                               "technical_contact": "Jamal Foster (Snowflake schema/security reviewer)"},
            plan_headline="Crisp 60-day onboarding with an Outreach connector milestone",
            plan_rationale="Standard onboarding, front-loaded reliability, connector by week 4 to protect phase two.",
            plan_duration_label="60 days",
            plan_milestones=[
                {"title": "Kickoff + success criteria", "owner": "us", "day": 3},
                {"title": "Snowflake schema reviewed with Jamal", "owner": "joint", "day": 10},
                {"title": "First 2 workflows live", "owner": "joint", "day": 21},
                {"title": "Outreach connector live", "owner": "us", "day": 30},
                {"title": "3 workflows in prod (1 on Outreach)", "owner": "joint", "day": 60},
            ],
        ),
    ),
    Customer(
        slug="cedarline-freight", name="Cedarline Freight", domain="cedarlinefreight.com",
        one_liner="Seed-stage SaaS in freight brokerage operations", tier="SMB",
        arr_cents=2_400_000, lifecycle="handoff", lane="lane1", days_to_renewal=365,
        onboarding_day_current=0, onboarding_day_total=60,
        health="healthy", health_score=72,
        health_reason="Clean deal; single technical contact is the main risk.",
        notion_page_id="36d8cb9801b5809fb8d0e9404126dbf6",
        stakeholders=[
            Stakeholder("Lena Hartwell", "Head of RevOps", "lena@cedarlinefreight.com", is_champion=True),
            Stakeholder("Owen Reyes", "Data Engineer", "owen@cedarlinefreight.com"),
        ],
        goals=[
            Goal("3 workflows live in production by day 60", is_primary=True),
            Goal("Auto-create Asana tasks when deals stall past 14 days"),
        ],
        milestones=[
            Milestone("Kickoff call", "not_started", "us", target_days=4, goal_index=0),
            Milestone("Salesforce→Snowflake sync configured", "not_started", "customer", target_days=14, goal_index=0),
        ],
        threads=[],
        needs=[
            Need("handoff", "new_handoff", "Review handoff brief for Cedarline Freight", priority_rank=4,
                 lede="Marcus closed, Devon onboards. Weekly office-hours commitment.",
                 reasoning="New deal; office-hours commitment must be tracked."),
        ],
        handoff=Handoff(
            body=("Seed-stage freight brokerage SaaS. Use case: sync Salesforce opportunity data into Snowflake "
                  "and auto-create Asana tasks when deals stall past 14 days. Chose us over Zapier and a "
                  "contractor build on price + the no-code builder for Lena's non-technical team. Lena prefers "
                  "email; Owen lives in Slack."),
            day_current=0, day_total=60, confidence="high",
            risks="Owen is the only technical resource and is stretched thin — if he goes heads-down, implementation stalls.",
            sales_commitments=[
                {"what": "30-min weekly office-hours slot", "scope": "first month of onboarding", "owner": "Devon",
                 "due": "weekly, month 1"},
            ],
            technical_context={"source": "Salesforce", "warehouse": "Snowflake", "tasks": "Asana",
                               "technical_contact": "Owen Reyes (sole engineer)"},
            plan_headline="Standard 60-day onboarding with weekly office hours",
            plan_rationale="Low complexity; the risk is Owen's bandwidth, so keep cadence light and async-friendly.",
            plan_duration_label="60 days",
            plan_milestones=[
                {"title": "Kickoff", "owner": "us", "day": 4},
                {"title": "Salesforce→Snowflake sync", "owner": "customer", "day": 14},
                {"title": "Stalled-deal Asana automation", "owner": "joint", "day": 30},
                {"title": "3 workflows in prod", "owner": "joint", "day": 60},
            ],
        ),
    ),
    Customer(
        slug="verge-lending", name="Verge Lending", domain="vergelending.com",
        one_liner="Series B SaaS in lending operations", tier="Growth",
        arr_cents=3_800_000, lifecycle="handoff", lane="lane1", days_to_renewal=365,
        onboarding_day_current=0, onboarding_day_total=50,
        health="stable", health_score=68,
        health_reason="Strong deal; a hidden VP-Eng approver gates expansion.",
        notion_page_id="36d8cb9801b580f3ae77f0ff73b535b5",
        stakeholders=[
            Stakeholder("Marcus Webb", "Director of RevOps", "marcus@vergelending.com", is_champion=True),
            Stakeholder("Dana Lindqvist", "Data Lead", "dana@vergelending.com"),
            Stakeholder("Soren Halvorsen", "VP Engineering", "soren@vergelending.com",
                        renewal_health="warn"),
        ],
        goals=[
            Goal("Live in 50 days with 3 workflows", is_primary=True),
            Goal("Trigger Apollo sequences off intent signals (needs connector enhancement)"),
        ],
        milestones=[
            Milestone("Kickoff call", "not_started", "us", target_days=5, goal_index=0),
            Milestone("Apollo connector field-mapping enhancement", "not_started", "us", target_days=14, goal_index=1),
        ],
        threads=[],
        needs=[
            Need("handoff", "new_handoff", "Review handoff brief for Verge Lending", priority_rank=5,
                 lede="Apollo connector committed; Soren (VP Eng) gates the warehouse side.",
                 reasoning="New deal; hidden stakeholder Soren must bless BigQuery before expansion."),
        ],
        handoff=Handoff(
            body=("Series B lending-ops SaaS. Use case: sync HubSpot opportunity data into BigQuery and trigger "
                  "Apollo sequences off intent signals. Chose us on price, no-code, and our willingness to "
                  "prioritize an Apollo connector enhancement. Note: customer-side champion is also named Marcus "
                  "(not our Marcus). Webb prefers Slack; Dana prefers email."),
            day_current=0, day_total=50, confidence="medium",
            risks="VP Eng Soren Halvorsen has final sign-off on anything touching the warehouse and was skeptical "
                  "in the eval — he won't be in kickoff but his approval gates scaling usage.",
            sales_commitments=[
                {"what": "Apollo connector field-mapping enhancement", "scope": "~2 weeks (scoped by Priya)",
                 "owner": "Priya", "due": "within first month"},
            ],
            technical_context={"source": "HubSpot", "warehouse": "BigQuery", "sequences": "Apollo",
                               "gatekeeper": "Soren Halvorsen (VP Eng, warehouse sign-off)"},
            plan_headline="50-day onboarding with an early Apollo connector enhancement",
            plan_rationale="Front-load the connector and get Soren bought in early so expansion isn't blocked later.",
            plan_duration_label="50 days",
            plan_milestones=[
                {"title": "Kickoff", "owner": "us", "day": 5},
                {"title": "Apollo connector enhancement", "owner": "us", "day": 14},
                {"title": "BigQuery sign-off from Soren", "owner": "joint", "day": 25},
                {"title": "3 workflows live (1 on Apollo)", "owner": "joint", "day": 50},
            ],
        ),
    ),
    # ===== LANE 2 — established portfolio =======================================
    Customer(
        slug="quietfield-software", name="Quietfield Software", domain="quietfieldsoftware.com",
        one_liner="B2B SaaS for QA test orchestration", tier="SMB",
        arr_cents=2_000_000, lifecycle="active", lane="lane2", days_to_renewal=180,
        health="at_risk", health_score=55,
        health_reason="Strong start, then silence — last inbound 35 days ago. Usage continues; sentiment unknown.",
        renewal_readiness="tracking",
        notion_page_id="3c251ee87eae4e88ad13df1d3b94f43e",
        stakeholders=[
            Stakeholder("Hana Müller", "Director of Engineering Operations",
                        "hana.mueller@quietfieldsoftware.com", is_champion=True, renewal_health="warn"),
        ],
        # Goals intentionally omitted (going-dark account; mirrors HITL-test seed intent).
        milestones=[
            Milestone("Onboarding kickoff", "done", "us", target_days=-200),
            Milestone("4 workflows live in production", "done", "joint", target_days=-160),
            Milestone("Establish check-in cadence", "blocked", "us", target_days=-20,
                      goal_rationale="Cadence never got set after onboarding — the root of the silence."),
        ],
        meetings=[
            Meeting("onboarding-review", "Quietfield — Onboarding Review", days_from_now=-150, status="completed",
                    attendees_ours=["Devon Patel"], attendees_theirs=["Hana Müller"]),
        ],
        threads=[
            # The going-dark gap: active inbound through day -35, then only CSM outbound, no reply.
            Thread("setup-and-silence", "Setup question — workflow retries", channel="email", interactions=[
                Interaction(88, "customer", sender_name="Quietfield — Hana Müller", channel="email",
                            body="Onboarding's gone really smoothly — we've got two workflows live already. Quick one: "
                                 "how do retries behave when a downstream check times out?"),
                Interaction(74, "customer", sender_name="Quietfield — Hana Müller", channel="email",
                            body="Third and fourth workflows are in. Team's happy. Thanks for the quick help last week."),
                Interaction(60, "customer", sender_name="Quietfield — Hana Müller", channel="email",
                            body="All four are running clean in prod now. We're good for a bit — will reach out if anything comes up."),
                Interaction(47, "us", sender_name="Devon Patel", channel="email",
                            body="Love to hear it. I'll check in lightly in a few weeks — flag me anytime."),
                Interaction(35, "customer", sender_name="Quietfield — Hana Müller", channel="email",
                            body="One small config question — can a workflow be paused without losing its run history? "
                                 "No rush."),
                # ── silence begins. CSM nudges, no reply. ──
                Interaction(21, "us", sender_name="Devon Patel", channel="email",
                            body="Hey Hana — answered the pause question above. Also wanted to set up a quick async "
                                 "check-in as you head toward renewal. What works?"),
                Interaction(9, "us", sender_name="Devon Patel", channel="email",
                            body="Following up on the check-in — totally fine to keep it async. How are the four "
                                 "workflows feeling in day-to-day use?"),
            ]),
        ],
        needs=[],  # the going-dark Need is produced organically by POST /sweep, not seeded.
        # Afterglow of a strong onboarding, then a steady decline into silence — the
        # going-dark trajectory the morning sweep ultimately catches.
        sentiment=[
            SentimentPoint(28, "ok",   "Onboarding afterglow; four workflows running clean."),
            SentimentPoint(21, "warn", "First check-in nudge went unanswered."),
            SentimentPoint(14, "warn", "Still quiet; cadence never established."),
            SentimentPoint(7,  "risk", "Weeks of silence — no reply to repeated nudges."),
            SentimentPoint(2,  "risk", "Fully dark; renewal approaching with no contact."),
        ],
    ),
    Customer(
        slug="aperio-analytics", name="Aperio Analytics", domain="aperioanalytics.com",
        one_liner="Series A product analytics SaaS", tier="Growth",
        arr_cents=3_000_000, lifecycle="active", lane="lane2", days_to_renewal=150,
        health="at_risk", health_score=48,
        health_reason="Active escalation after a webhook-change incident; CEO pulled in. Trust hinges on follow-through.",
        renewal_readiness="at_risk",
        notion_page_id="ebf0292c6a654ed58c63f6573476aaad",
        stakeholders=[
            Stakeholder("Liam Carter", "VP Engineering", "liam.carter@aperioanalytics.com",
                        is_champion=True, renewal_health="risk"),
            Stakeholder("Nina Tasaki", "CEO", "nina.tasaki@aperioanalytics.com", renewal_health="risk"),
        ],
        goals=[
            Goal("Reliable webhook integration for production workflows", is_primary=True),
            Goal("Zero-downtime data pipeline for the analytics dashboard"),
        ],
        milestones=[
            Milestone("Postmortem document", "in_progress", "us", target_days=2, goal_index=0,
                      goal_rationale="Committed on the emergency call; Priya is the bottleneck — unblock fast."),
            Milestone("Webhook signature-change policy", "not_started", "us", target_days=7, goal_index=0),
            Milestone("Service credit applied at renewal", "not_started", "us", target_days=150, goal_index=0),
        ],
        meetings=[
            Meeting("emergency-call", "Aperio — Incident Review (emergency)", days_from_now=-4, status="completed",
                    duration_minutes=45, attendees_ours=["Marcus Lee", "Priya Shah"],
                    attendees_theirs=["Liam Carter", "Nina Tasaki"]),
        ],
        threads=[
            Thread("escalation", "Following up on Wednesday commitments", channel="email", interactions=[
                Interaction(6, "customer", sender_name="Aperio — Liam Carter",
                            subject="Two workflows silently stopped firing",
                            body="Two of our three production workflows silently stopped firing for ~36 hours after "
                                 "your webhook signature change. No migration notice. This is business-critical for us."),
                Interaction(4, "us", sender_name="Marcus Lee",
                            subject="Re: Two workflows silently stopped firing",
                            body="Owning this fully. On Friday's call we committed to a postmortem by EOD Wednesday, a "
                                 "signature-change policy by next Friday, and a service credit at renewal."),
                Interaction(1, "customer", sender_name="Aperio — Liam Carter",
                            subject="Re: Following up on Wednesday commitments",
                            body="Appreciate it. Nina's watching this closely. The postmortem is what matters most — "
                                 "if Wednesday slips, this becomes a much bigger conversation."),
            ]),
        ],
        needs=[
            Need("escalation", "escalation", "Aperio escalation — postmortem due Wednesday", priority_rank=1,
                 lede="Webhook incident; 3 commitments open. CEO escalated. Postmortem is the bottleneck.",
                 reasoning="P1 escalation: trust hinges on delivering the postmortem on time.",
                 thread_key="escalation"),
        ],
        # Solid → sharp dip at the webhook incident (~6d ago) → still raw while the
        # postmortem is pending. Sentiment stays at risk even as engagement climbs (they're
        # talking more, but trust isn't restored) — explains the 48/100 health. Ending at
        # `risk` also lets the sweep's sentiment detector dedup against it (no extra need).
        sentiment=[
            SentimentPoint(28, "ok",   "Steady; production workflows healthy."),
            SentimentPoint(20, "ok",   "Routine check-in, no friction."),
            SentimentPoint(12, "warn", "Minor questions about an upcoming webhook change."),
            SentimentPoint(6,  "risk", "Two production workflows stopped firing — business-critical."),
            SentimentPoint(3,  "risk", "CEO escalated; postmortem still pending."),
            SentimentPoint(1,  "risk", "Engaging on the commitments, but trust hinges on Wednesday's postmortem."),
        ],
    ),
    Customer(
        slug="bevelpoint-logistics", name="Bevelpoint Logistics", domain="bevelpointlogistics.com",
        one_liner="B2B SaaS for freight brokerage workflow", tier="Mid-Market",
        arr_cents=2_400_000, lifecycle="renewing", lane="lane2", days_to_renewal=75,
        health="stable", health_score=62,
        health_reason="Strong usage (12 workflows) but board is pushing CPQ consolidation; renewal narrative not built.",
        renewal_readiness="at_risk",
        # Notion page id is malformed in source (31 hex, 'VERIFY-' prefix). Stored best-effort;
        # Bevelpoint is a renewal account, not a live-handoff target, so this is non-blocking.
        notion_page_id="60cbf492fe0b436fad3089313c8d83a",
        stakeholders=[
            Stakeholder("Reggie Vance", "COO", "reggie.vance@bevelpointlogistics.com",
                        is_champion=True, renewal_health="warn"),
        ],
        goals=[
            Goal("Differentiated outcomes vs. the 'consolidate to CPQ' narrative", is_primary=True),
            Goal("Real-time visibility into shipment status"),
            Goal("Reduce manual dispatching effort by 60%", status="achieved"),
        ],
        milestones=[
            Milestone("Outcome audit (time saved, error reduction)", "not_started", "us", target_days=10, goal_index=0),
            Milestone("Renewal QBR with Reggie", "not_started", "joint", target_days=21, goal_index=0),
        ],
        meetings=[
            Meeting("renewal-qbr", "Bevelpoint — Renewal QBR", days_from_now=14, status="scheduled",
                    attendees_ours=["Marcus Lee"], attendees_theirs=["Reggie Vance"]),
        ],
        threads=[
            Thread("qbr-notes", "Last QBR — consolidation pressure", channel="note", interactions=[
                Interaction(20, "internal", sender_name="Marcus Lee", channel="note",
                            body="QBR recap: Reggie positive on outcomes (12 active workflows, 4 users this month). "
                                 "But the board is pushing to reduce tool sprawl and consolidate on Salesforce CPQ, "
                                 "which overlaps a feature of ours. CPQ is inferior but effectively 'free.' We need a "
                                 "renewal case on differentiated outcomes. Haven't started prep — 75 days out."),
                Interaction(4, "customer", sender_name="Bevelpoint — Reggie Vance", channel="note",
                            body="Confirmed for the QBR on the 14th — anything you need from me beforehand?"),
            ]),
        ],
        needs=[
            Need("renewal", "approaching_renewal", "Bevelpoint renewal in 75 days — build the case", priority_rank=3,
                 lede="Board pushing CPQ consolidation; strong usage but no renewal narrative yet.",
                 reasoning="Renewal at risk on strategy, not product. Start the renewal play now.",
                 thread_key="qbr-notes"),
        ],
    ),
    Customer(
        slug="foldwise", name="Foldwise", domain="foldwise.com",
        one_liner="Series B contract lifecycle management SaaS", tier="Growth",
        arr_cents=3_600_000, lifecycle="at_risk", lane="lane2", days_to_renewal=120,
        health="deteriorating", health_score=38,
        health_reason="Two rate-limit incidents; promised reliability review never delivered. Benchmarking Tray/Workato.",
        renewal_readiness="at_risk",
        notion_page_id="5df12c7e756e4e41a0b091ede18034b6",
        stakeholders=[
            Stakeholder("David Okonkwo", "Head of RevOps", "david.okonkwo@foldwise.com",
                        is_champion=True, renewal_health="risk"),
        ],
        # Goals intentionally omitted (at-risk account; mirrors HITL-test seed intent).
        milestones=[
            Milestone("Reliability review (what changed, monitoring added)", "blocked", "us", target_days=-3,
                      goal_rationale="Committed after David's complaint 10 days ago; never followed up — overdue."),
        ],
        threads=[
            Thread("reliability", "Still waiting on the reliability review", channel="email", interactions=[
                Interaction(10, "customer", sender_name="Foldwise — David Okonkwo",
                            subject="Reliability — this can't be best-effort",
                            body="Two rate-limit incidents in six weeks, both slow to resolve. RevOps-owned "
                                 "automations tied to revenue can't feel best-effort. I need a real reliability plan."),
                Interaction(9, "us", sender_name="Marcus Lee",
                            subject="Re: Reliability — this can't be best-effort",
                            body="You're right, and I'm sorry. I'll get you a reliability review — what happened, what "
                                 "we're changing, and the monitoring we're adding — with a timeline."),
                Interaction(2, "customer", sender_name="Foldwise — David Okonkwo",
                            subject="Re: Reliability — this can't be best-effort",
                            body="It's been over a week with nothing. We're starting to look at Tray and Workato. I "
                                 "want to make this work but I need to see follow-through."),
            ]),
        ],
        needs=[
            Need("at-risk", "frustrated_signal", "Foldwise frustrated — reliability review overdue", priority_rank=1,
                 lede="Promised review never delivered; David benchmarking Tray/Workato. Churn risk.",
                 reasoning="Frustration + competitor benchmarking + a broken commitment = default trajectory is churn.",
                 thread_key="reliability"),
        ],
    ),
    Customer(
        slug="bridgenote", name="Bridgenote", domain="bridgenote.com",
        one_liner="Series A B2B SaaS in revenue intelligence", tier="Growth",
        arr_cents=2_600_000, lifecycle="active", lane="lane2", days_to_renewal=120,
        health="strong", health_score=84,
        health_reason="Healthy, 6 workflows in prod; asking for a Gong connector and more seats. Clear expansion upside.",
        renewal_readiness="tracking",
        notion_page_id="b3a34a67d0854caaa1c442effe160b0b",
        stakeholders=[
            Stakeholder("Kavya Reddy", "RevOps Manager", "kavya.reddy@bridgenote.com",
                        is_champion=True, renewal_health="ok"),
        ],
        goals=[
            Goal("Unified revenue intelligence across all channels", is_primary=True),
            Goal("Integrate Gong call data with pipeline forecasting"),
            Goal("Custom attribution models built by RevOps"),
        ],
        milestones=[
            Milestone("Onboarding complete (6 workflows live)", "done", "joint", target_days=-120, goal_index=0),
            Milestone("Gong connector scoping with Priya", "not_started", "us", target_days=14, goal_index=1),
        ],
        threads=[
            Thread("gong-ask", "Gong connector — any update?", channel="email", interactions=[
                Interaction(14, "customer", sender_name="Bridgenote — Kavya Reddy",
                            subject="Trigger workflows from Gong call data?",
                            body="Can Northcrest trigger workflows from Gong call data — e.g. auto-create a HubSpot "
                                 "task when a sales call mentions a competitor? Also we just added 2 RevOps hires."),
                Interaction(3, "customer", sender_name="Bridgenote — Kavya Reddy",
                            subject="Re: Trigger workflows from Gong call data?",
                            body="Following up — and could you send per-seat pricing at our tier? Onboarding the two "
                                 "new folks this month."),
            ]),
        ],
        needs=[
            Need("expansion", "expansion_signal", "Bridgenote expansion — Gong connector + 2 seats", priority_rank=3,
                 lede="Healthy account asking for a connector and more seats. Marcus hasn't replied (pulled into Aperio).",
                 reasoning="Strong expansion signal at risk of going cold while attention is elsewhere.",
                 thread_key="gong-ask"),
        ],
    ),
    Customer(
        slug="pinegrove-hr", name="Pinegrove HR", domain="pinegrovehr.com",
        one_liner="HR/payroll SaaS", tier="Mid-Market",
        arr_cents=3_200_000, lifecycle="active", lane="lane2", days_to_renewal=210,
        health="strong", health_score=88,
        health_reason="Healthy, expanding. Usage growing MoM; asked about a second seat. No red flags.",
        renewal_readiness="ready",
        notion_page_id="a3eddb5e26854fceaf0adfee0339a5f7",
        stakeholders=[
            Stakeholder("Maya Brooks", "Director of Operations", "maya.brooks@pinegrovehr.com",
                        is_champion=True, renewal_health="ok"),
        ],
        goals=[
            Goal("Northcrest as the orchestration layer across HubSpot/Salesforce/ChartHop", is_primary=True),
            Goal("Reduce payroll processing time by 50%"),
            Goal("Automate HR data sync across 3 regional offices", status="achieved"),
        ],
        milestones=[
            Milestone("Onboarding complete", "done", "joint", target_days=-240, goal_index=2),
            Milestone("Add second seat (new RevOps analyst)", "not_started", "us", target_days=21, goal_index=0),
        ],
        meetings=[
            Meeting("check-in", "Pinegrove — Routine Check-in", days_from_now=-14, status="completed",
                    attendees_ours=["Marcus Lee"], attendees_theirs=["Maya Brooks"]),
        ],
        threads=[
            Thread("seat-request", "Adding a seat for our new analyst", channel="email", interactions=[
                Interaction(14, "customer", sender_name="Pinegrove — Maya Brooks",
                            subject="Adding a seat",
                            body="Things are running smoothly — no concerns from the last check-in. We just hired a "
                                 "RevOps analyst; can we add a second seat for her?"),
                Interaction(5, "customer", sender_name="Pinegrove — Maya Brooks", subject="Re: Adding a seat",
                            body="Thanks — let me know once the second seat is set up. No rush on my end."),
            ]),
        ],
        needs=[
            Need("expansion", "positive_signal", "Pinegrove healthy — second-seat request", priority_rank=6,
                 lede="Expanding account; routine seat add. Good renewal signal for next quarter.",
                 reasoning="Positive expansion signal; low-effort win that reinforces the relationship.",
                 thread_key="seat-request"),
        ],
    ),
    Customer(
        slug="velmont-freight", name="Velmont Freight", domain="velmontfreight.com",
        one_liner="Freight brokerage SaaS, recently renewed with an uptier", tier="Growth",
        arr_cents=3_400_000, lifecycle="active", lane="lane2", days_to_renewal=365,
        health="healthy", health_score=74,
        health_reason="Renewed + uptiered; strong usage. Risk is execution — two renewal commitments are behind.",
        renewal_readiness="tracking",
        notion_page_id="36e8cb9801b58038a006fb805905fe6f",
        stakeholders=[
            Stakeholder("Greg Halloran", "COO", "greg@velmontfreight.com", is_champion=True, renewal_health="ok"),
            Stakeholder("Marisol Tan", "RevOps Lead", "marisol@velmontfreight.com", renewal_health="warn"),
        ],
        goals=[
            Goal("Deliver the two commitments that won the renewal", is_primary=True),
            Goal("Custom EDI-data connector live within the committed 6 weeks"),
            Goal("Quarterly business review cadence with Greg"),
        ],
        milestones=[
            Milestone("EDI connector — build", "in_progress", "us", target_days=21, goal_index=1,
                      goal_rationale="Committed on the renewal call (6 weeks; now week 3). Scoped, not started."),
            Milestone("Stand up QBR cadence with Greg", "not_started", "us", target_days=14, goal_index=2),
        ],
        threads=[
            Thread("edi-timeline", "EDI connector timeline?", channel="email", interactions=[
                Interaction(30, "internal", sender_name="Marcus Lee", channel="note",
                            body="Renewal closed two weeks ago — uptiered to $34k from $30k. Two commitments: EDI "
                                 "connector in 6 weeks and a QBR cadence with Greg. Both behind."),
                Interaction(3, "customer", sender_name="Velmont — Marisol Tan",
                            subject="EDI connector timeline?",
                            body="Checking on the EDI connector — we're at week 3 of the 6 we agreed on the renewal "
                                 "call. Where are we, and when can we test?"),
            ]),
        ],
        needs=[
            Need("commitment", "open_commitment_overdue", "Velmont — EDI connector + QBR commitments slipping",
                 priority_rank=2,
                 lede="Two renewal commitments behind; Marisol asking on timeline. Don't sour a great account post-uptier.",
                 reasoning="Execution risk on promises made to win the renewal — the fastest way to lose a happy account.",
                 thread_key="edi-timeline"),
        ],
    ),
    # ===== BACKGROUND — portfolio padding (light data) ==========================
    Customer(
        slug="hollowbrook-media", name="Hollowbrook Media", domain="hollowbrookmedia.com",
        one_liner="Series A SaaS in ad-ops and media buying", tier="Growth",
        arr_cents=2_800_000, lifecycle="onboarding", lane="bg", days_to_renewal=330,
        onboarding_day_current=14, onboarding_day_total=60,
        health="stable", health_score=65,
        health_reason="Early onboarding; CEO not yet convinced — first month matters.",
        notion_page_id="36d8cb9801b580fca29edcd53917015c",
        stakeholders=[
            Stakeholder("Priya Raman", "RevOps Lead", "p.raman@hollowbrookmedia.com", is_champion=True),
        ],
        goals=[
            Goal("2 workflows live + daily Slack pacing summary by end of month one", is_primary=True),
        ],
        milestones=[
            Milestone("Kickoff", "done", "us", target_days=-12, goal_index=0),
            Milestone("HubSpot→BigQuery sync", "in_progress", "customer", target_days=7, goal_index=0),
            Milestone("Daily Slack spend-pacing summary", "not_started", "us", target_days=16, goal_index=0),
        ],
        threads=[
            Thread("onboarding-check", "HubSpot sync setup", channel="email", interactions=[
                Interaction(3, "customer", sender_name="Hollowbrook — Priya Raman", subject="HubSpot sync setup",
                            body="Working through the HubSpot→BigQuery field mapping — should have it wrapped by EOD. "
                                 "Any blockers on your side?"),
            ]),
        ],
        needs=[],
    ),
    Customer(
        slug="saltmarsh-bio", name="Saltmarsh Bio", domain="saltmarshbio.com",
        one_liner="Series A SaaS in lab/biotech operations", tier="Mid-Market",
        arr_cents=3_000_000, lifecycle="onboarding", lane="bg", days_to_renewal=330,
        onboarding_day_current=10, onboarding_day_total=60,
        health="stable", health_score=66,
        health_reason="Onboarding; a hidden board deadline ('live before the July audit') is riding on this.",
        notion_page_id="36d8cb9801b5804da822fce2a6d0f503",
        stakeholders=[
            Stakeholder("Dr. Anita Bose", "VP Operations", "a.bose@saltmarshbio.com", is_champion=True),
            Stakeholder("Felix Tran", "Systems Analyst", "felix@saltmarshbio.com"),
        ],
        goals=[
            Goal("3 workflows live; data-hygiene rules catching malformed records", is_primary=True),
        ],
        milestones=[
            Milestone("Kickoff", "done", "us", target_days=-8, goal_index=0),
            Milestone("Custom sample-ID validation rule template", "in_progress", "us", target_days=5, goal_index=0,
                      goal_rationale="Sales committed ~1 week; ties to the hidden July-audit go-live date."),
        ],
        threads=[
            Thread("onboarding-check", "Sample-ID template question", channel="email", interactions=[
                Interaction(2, "customer", sender_name="Saltmarsh — Felix Tran", subject="Sample-ID template question",
                            body="Building out the validation-rule template — quick question on the regex format for the "
                                 "sample-ID prefix. Can you point us at the right docs?"),
            ]),
        ],
        needs=[],
    ),
    Customer(
        slug="pebblerock-retail", name="Pebblerock Retail", domain="pebblerockretail.com",
        one_liner="Series A SaaS in retail analytics", tier="Growth",
        arr_cents=2_600_000, lifecycle="onboarding", lane="bg", days_to_renewal=330,
        onboarding_day_current=8, onboarding_day_total=60,
        health="healthy", health_score=70,
        health_reason="Clean deal, no commitments; only watch-item is adoption (retire the old CSV process).",
        notion_page_id="36d8cb9801b58027b41fd555338f898e",
        stakeholders=[
            Stakeholder("Grace Mbeki", "Director of Operations", "gracem@pebblerockretail.com", is_champion=True),
            Stakeholder("Tobias Klein", "BI Analyst", "tobias@pebblerockretail.com"),
        ],
        goals=[
            Goal("3 workflows live; scheduled dashboard refresh replacing the manual export", is_primary=True),
        ],
        milestones=[
            Milestone("Kickoff", "done", "us", target_days=-6, goal_index=0),
            Milestone("HubSpot→Snowflake sync + scheduled refresh", "in_progress", "customer", target_days=10, goal_index=0),
        ],
        threads=[
            Thread("onboarding-check", "Snowflake sync progress", channel="email", interactions=[
                Interaction(3, "customer", sender_name="Pebblerock — Tobias Klein", subject="Snowflake sync progress",
                            body="The HubSpot→Snowflake connector is mostly configured — we should be able to test the "
                                 "scheduled refresh by Friday."),
            ]),
        ],
        needs=[],
    ),
]


def select(profile: str) -> list[Customer]:
    """Pick customers for a seed profile. 'full' = everyone (default)."""
    if profile == "lane1":
        return [c for c in CUSTOMERS if c.lane == "lane1"]
    if profile == "lane2":
        return [c for c in CUSTOMERS if c.lane in ("lane2", "bg")]
    return list(CUSTOMERS)
