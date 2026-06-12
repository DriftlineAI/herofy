# Handoff Auto Agent

**What it does**: When a B2B deal closes in Notion, this agent picks up everything sales captured, builds a structured handoff brief for the CSM, generates a goal-driven onboarding plan, and surfaces a review need in the Today queue — all autonomously, pausing only when it genuinely needs a human answer to proceed.

---

## The problem it solves

The gap between "deal closed" and "first CSM call" is where onboardings fail. Sales captured commitments, technical requirements, and customer goals somewhere in Notion — but no CSM has time to re-read three months of deal notes before a kickoff call. This agent reads it all, extracts what matters, flags what's missing or risky, and hands the CSM a brief they can trust on day one.

---

## Architecture

Built on **Google ADK 1.20** with an `LlmAgent` + `PlanReActPlanner`. The planner makes the reasoning chain visible (each step is logged as a plan trace) and keeps the agent from getting stuck in loops.

```
routes/agents.py
    └── POST /agents/handoff-auto/run
            └── run_handoff_auto(workspace_id, customer_id)
                    └── ADK LlmAgent (Gemini 2.5 Flash)
                            ├── Context tools (read-only)
                            │   ├── get_customer_info
                            │   ├── get_workspace_settings
                            │   ├── get_customer_goals
                            │   ├── get_playbook_for_workspace
                            │   ├── get_milestone_blocks
                            │   ├── get_handbook_guide
                            │   └── recall_memory
                            ├── Artifact tools (write)
                            │   ├── set_primary_goal / set_customer_goals
                            │   ├── create_progress_vectors
                            │   ├── create_customer_strategy
                            │   ├── create_handoff_brief / update_handoff_brief
                            │   ├── generate_onboarding_plan / update_plan
                            │   └── surface_need_for_review
                            └── HITL tools
                                ├── pause_for_human_input     ← BLOCKERS
                                ├── add_handoff_questions     ← SIDE-ASKS / KICKOFF
                                └── update_plan_from_answers  ← on resume
```

---

## What the agent produces

### 1. Handoff Brief
The artifact the CSM opens before the kickoff call. Contains:
- **Sales commitments** — quoted with source, not paraphrased. If sales said "30-day go-live", the brief says "30-day go-live (Notion deal page, section: Timeline)."
- **Technical context** — API access method, SSO requirements, data residency, integration points
- **Reality check risks** — what the agent flagged as concerning or inconsistent with the playbook
- **Confidence score** — HIGH / MEDIUM / LOW based on completeness of sales notes

### 2. Customer Goals + Progress Vectors
- Extracts the customer's actual business goals from the deal notes (not just "onboard them")
- Marks one as the **primary goal** (the Mission Objective)
- Creates **progress vectors** tracking movement toward the goal across five dimensions: trust, risk_mitigation, stakeholder, value, momentum

### 3. AI Onboarding Plan
- Goal-driven milestones — every milestone carries a `goal_id` and `goal_rationale`
- If a goal has no milestone supporting it, the agent adapts the playbook rather than skipping the goal
- Owners assigned per milestone (us / customer / joint)
- Accelerated or standard timeline based on sales commitments

### 4. Customer Strategy Memo
A living markdown memo capturing the strategic context: why this customer bought, what success looks like to them, and what risks we're managing going in.

### 5. Review Need in Today Queue
A `plan_approval_required` need surfaces in the CSM's Today queue, linking to the dual-pane HITL review UI (left: brief, right: plan).

---

## HITL model — three tiers

The agent distinguishes three kinds of uncertainty:

| Tier | Tool | Behavior | Example |
|------|------|----------|---------|
| **BLOCKER** | `pause_for_human_input()` | Agent pauses; run is `waiting_for_input`; resumes when answered | "Is the custom integration in scope or a post-go-live add?" |
| **SIDE-ASK** | `add_handoff_questions(routing="sales")` | Recorded but doesn't pause; answered after kickoff | "Which Salesforce instance is this?" |
| **KICKOFF ITEM** | `add_handoff_questions(routing="kickoff")` | Recorded as agenda item; raised in kickoff call | "Confirm API credentials are ready before kickoff" |

Blockers are rare — the agent is instructed to only pause when proceeding without an answer would produce a meaningfully wrong plan. Side-asks and kickoff items are surfaced in the HITL review UI as structured questions for the CSM to address.

**Resume flow**: `POST /api/workspaces/:id/agent-runs/:id/answers` → `resume_handoff_auto(run_id, answers)` → agent continues from where it paused, using answers to fill gaps before generating the plan.

---

## Confidence model

`confidence.py` aggregates four signals into a HIGH / MEDIUM / LOW assessment:

1. **Data completeness** — are required fields present (ARR, timeline, technical requirements)?
2. **Data quality** — are sales notes substantive or vague?
3. **Pattern matching** — does this deal match known playbook archetypes?
4. **LLM self-assessment** — the agent explicitly scores its own confidence in the plan rationale

HIGH → proceeds automatically. MEDIUM → configurable (pause or auto per workspace settings). LOW → always pauses.

---

## Key files

| File | Purpose |
|------|---------|
| `agent.py` | ADK `LlmAgent` wiring, system prompt, tool registration, run/resume entry points |
| `confidence.py` | Confidence assessment and threshold logic |
| `tools/` | All tool callables (context read, artifact write, HITL) |
| `tools/hitl.py` | Pause state management; pause/resume signal protocol |
| `tools/artifacts.py` | DB writes: brief, plan, goals, vectors, strategy, need |
| `tools/context.py` | Read-only DB queries: customer info, workspace settings, playbooks |
| `memory.py` | Agent memory state management across tool calls |
| `default_guides.py` | Fallback onboarding playbook templates used when no workspace playbook matches |
| `questions.py` | Structured question types and routing logic |
| `ARCHIVE/` | Pre-ADK implementations (kept for reference) |

---

## How to trigger

```bash
# Trigger for a specific customer
curl -X POST http://localhost:8081/agents/handoff-auto/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id": "...", "customer_id": "..."}'

# Resume after HITL
curl -X POST http://localhost:8081/api/workspaces/$WS/agent-runs/$RUN_ID/answers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answers": {"question_id": "answer text"}}'
```

---

## Design philosophy

> The CSM reviews everything this agent produces. It is preparing the CSM to run a great onboarding, not making customer-facing decisions itself.

The agent quotes sources for every commitment, surfaces risks it found rather than smoothing them over, and never invents information it doesn't have. When it's unsure, it asks — but only when asking matters.
