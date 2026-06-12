# Herofy

**AI-powered Customer Success workspace for small B2B SaaS teams**

Herofy watches your Gmail, Slack, Calendar, and Notion so your CSMs don't have to. It surfaces what needs attention today, takes autonomous action on at-risk accounts, and keeps humans in the loop for decisions that matter.

Built for the **Google ADK Hackathon** — three production agents running on Google ADK 1.20 + Gemini 2.5 Flash.

---

## What it does

A CSM managing 40 B2B accounts can't watch every email thread and Slack channel. Herofy's three agents handle the signal-to-action pipeline end-to-end:

1. **Signal Watcher** watches every inbound Gmail/Slack/Calendar/Notion event, classifies it, and routes significant signals into the system
2. **Handoff Autonomous Agent** picks up new deals from Notion, reads the entire sales history, and builds a structured onboarding brief + goal-driven plan for the CSM to review
3. **Orchestrator** autonomously investigates at-risk accounts, runs risk/save plays, self-critiques the output, and surfaces recommendations in the Today queue — scheduling follow-ups for itself

---

## The demo

Visit `demo.herofy.ai` to spin up an isolated sandbox workspace seeded with the Northcrest portfolio: a mix of healthy, onboarding, and at-risk accounts.

### What you'll see

**Today Queue** — AI-prioritized list of what needs attention. Each card has an AI headline, the reasoning behind it, and quick actions (snooze, resolve, dive in). The ticker bar at the top shows live portfolio stats.

**Handoff Plan Approval** — A new deal just landed. Click "Review Plan" on the handoff need to open the dual-pane HITL interface:
- Left pane: the handoff brief the agent extracted from Notion — sales commitments quoted with sources, technical requirements, reality-check risks
- Right pane: the AI-generated onboarding plan — goal-driven milestones with owners and target dates

Five actions: **Approve** (creates milestones, moves customer to onboarding), **Edit Plan** (adjust inline), **Edit Handoff** (correct sales commitments + regenerate), **Regenerate** (new plan), **Reject** (with reason).

**At-Risk Account (Bevelpoint Logistics)** — Navigate to this customer after triggering the orchestrator demo. The autonomous worker investigated the account, ran the Risk/Save play, self-critiqued the save plan, and surfaced a `renewal_at_risk` need with a multi-step save strategy. Everything you see (RiskBrief, play steps, the need itself) is a real Postgres row — no UI mocks.

**Conversations** — Every Gmail thread and Slack message the signal watcher ingested, linked to the right customer and need. OOO detection, response latency tracking, stakeholder profiles.

**Portfolio** — All customers grouped by lifecycle (active, onboarding, at-risk, renewing) with health sparklines from the metric time-series.

---

## Architecture

```
Frontend (React 19 + Vite)
    │
    ├── Firebase SQL Connect ──► CloudSQL PostgreSQL  (primary data layer)
    │   (GraphQL auto-SDK)       35 tables, 25 enums
    │
    └── Python FastAPI :8081 ──► AI agents + webhooks + orchestrator
            │
            ├── Signal Watcher          (agents/signal_watcher_unified/)
            │   Webhook → classify → Thread/Interaction/Need/AgentTask
            │
            ├── Handoff Agent           (agents/handoff_auto/)
            │   ADK LlmAgent + PlanReActPlanner → Brief + Plan + HITL
            │
            └── Orchestrator            (orchestrator/)
                Queue → Worker → Play → Specialist → Persist → Surface
```

### Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, React Router 7, Vite, TailwindCSS 4, Motion (Framer) |
| Data | Firebase SQL Connect (CloudSQL PostgreSQL 15), Firebase Auth |
| Backend | Python FastAPI, Google ADK 1.20 |
| AI | Gemini 2.5 Flash / Flash-Lite (tiered by use case) |
| Real-time | Firestore (live status streaming only — not primary data) |

---

## The three agents

### Signal Watcher (`backend/agents/signal_watcher_unified/`)
**Production. Event-driven ingestion layer.**

Every inbound webhook fires `process_events()`. The processor runs a deterministic classification cascade:
- Resolves sender to a customer (stakeholder email → domain → unknown)
- Classifies event type (new deal / field update / message / calendar)
- Routes: new Notion deals → HandoffAgent; structured field changes → direct DB sync; messages → Thread + Interaction + LLM signal classification; calendar → Meeting row + meeting prep need

Significant signals (frustrated sentiment, going dark, etc.) enqueue an `AgentTask` for the orchestrator to investigate.

[Full README →](backend/agents/signal_watcher_unified/README.md)

### Handoff Agent (`backend/agents/handoff_auto/`)
**Production. ADK LlmAgent with HITL.**

When a new deal closes in Notion, this agent:
1. Reads the entire deal history and extracts commitments, technical requirements, and goals
2. Creates a customer strategy memo + progress vectors (trust, risk_mitigation, stakeholder, value, momentum)
3. Generates a goal-driven onboarding plan — every milestone maps to a customer goal
4. Surfaces a `plan_approval_required` need for the CSM to review in the dual-pane UI

Three HITL tiers: **blockers** pause the agent and wait for an answer; **side-asks** are recorded for the sales team; **kickoff items** become agenda items for the kickoff call.

[Full README →](backend/agents/handoff_auto/README.md)

### Orchestrator (`backend/orchestrator/`)
**Production-ready. Flag-gated (`ORCHESTRATION_ENABLED`), side-by-side.**

Queue-driven autonomous worker that puts **autonomy at the decision layer and determinism at the execution layer**:

- **Worker** (`LlmAgent` + `PlanReActPlanner`) investigates an account and decides what to do — no lookup table
- **Plays** (`SequentialAgent`) execute deterministically: Research → [Strategist ⟲ Critic] → Persist → Surface
- **Self-critique loop**: the Critic scores the Strategist's output 1–5; score < 4 triggers one revision
- **Durable queue**: guarded CAS claim, restart-safe HITL, self-scheduling follow-ups
- **Zero mocks**: every rendered artifact is a real Postgres row

[Full README →](backend/orchestrator/README.md) · [Architecture deep-dive →](docs/ORCHESTRATOR_OVERVIEW.md)

---

## Quick start

### Prerequisites
- Node.js 20+ (`nvm use 20`)
- Python 3.12+
- Firebase CLI (`npm install -g firebase-tools && firebase login`)

### Start everything

```bash
# Terminal 1 — Firebase emulators (DataConnect + Firestore)
firebase emulators:start --only dataconnect,firestore --project herofy-496505

# Terminal 2 — Frontend
npm run dev:frontend

# Terminal 3 — Python backend
npm run dev:backend
# or manually:
cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 8081
```

Frontend: http://localhost:5173
Backend: http://localhost:8081

### Seed demo data

```bash
cd frontend && npx tsx seed-data.ts
```

This seeds the Northcrest portfolio: Bevelpoint Logistics (active, at-risk target), Apex Solutions (onboarding), Velmont Freight (active), plus pre-built playbooks, handbook docs, and Voice settings.

### Run the orchestrator demo

```bash
# Enable in backend/.env
ORCHESTRATION_ENABLED=true
# Restart backend, then trigger the demo worker:
curl -X POST http://localhost:8081/agents/orchestrator/demo-agent \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Environment variables

### `frontend/.env`
```
VITE_PYTHON_URL=http://localhost:8081
```

### `backend/.env`
```
DATABASE_URL=postgresql://herofy:herofy_local@localhost:5432/herofy_dev
FIREBASE_PROJECT_ID=herofy-496505
GEMINI_API_KEY=your-api-key

# Feature flags (default off; require backend restart to toggle)
ORCHESTRATION_ENABLED=false
METRIC_SNAPSHOTS_ENABLED=false

# Signal classification strategy
SIGNAL_CLASSIFICATION_MODE=threshold   # threshold | always_llm
SIGNAL_LLM_CONFIDENCE_THRESHOLD=0.5
```

Full flag reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)

---

## Key concepts

**Need-centric architecture** — Everything in the system revolves around Needs. A Need is something that requires a CSM's attention: a frustrated customer, an approaching renewal, a stalled onboarding milestone, an agent question. Every Thread, Meeting, and Milestone traces back to a Need.

**Today Queue** — AI-prioritized list of open Needs, ranked by urgency + recency + ARR. The queue is the CSM's daily starting point.

**HITL** — Agents pause and ask humans rather than proceeding with low confidence. The question surfaces as a `sidekick_question` Need in the Today queue; the answer resumes the agent. Humans are a queryable resource, not the driver.

**Handbook** — Versioned documents that define how Herofy thinks: going-dark criteria, renewal readiness framework, handoff quality standards. All agents reference the live handbook version when generating content, so changing a doc changes agent behavior.

---

## GCP resources

| Resource | Name | Location |
|----------|------|----------|
| CloudSQL Instance | herofy-fdc | us-central1 |
| Database | herofy-prod | — |
| SQL Connect Service | herofy-prod-service | us-central1 |
| Firebase Project | herofy-496505 | — |

---

## License

Proprietary — Hackathon Demo
