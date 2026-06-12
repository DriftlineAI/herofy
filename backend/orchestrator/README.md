# Orchestrator — Queue-Driven Autonomous Worker

**What it does**: Investigates at-risk customer accounts, decides what to do about them, runs deterministic save plays, self-critiques the output, writes real database rows, and schedules follow-ups — all without a human in the loop unless it needs one.

**Status**: Built and verified (Phase 0–2, critic loop). Side-by-side with the existing agents behind a feature flag (`ORCHESTRATION_ENABLED`, default off).

---

## The core idea

We replaced the "one big agent with 20 tools" model with a **queue-driven worker that puts autonomy at the decision layer and determinism at the execution layer**.

| Layer | Technology | Why |
|-------|------------|-----|
| **Worker** (decision) | `LlmAgent` + `PlanReActPlanner` | Genuine judgment under ambiguity |
| **Plays** (execution) | `SequentialAgent` | Reliability, testability, no hallucinated steps |
| **Queue** (spine) | Durable Postgres | Triggers → action, restart-safe HITL, self-scheduling |

The same system hosts every AI use case — risk/save today; onboarding, renewals, support, briefings next — without building N separate monolithic agents.

---

## Three-layer architecture

```
PRODUCERS
 • /demo-agent (demo)
 • signal_watcher (prod) ──► AgentTask QUEUE (Postgres) ──► AUTONOMOUS WORKER
 • Cloud Scheduler (prod)     status / payload / customer     (LlmAgent + PlanReActPlanner)
 • plays (self-enqueue)       priority / scheduledFor           1. claim task (guarded CAS)
                                                                2. investigate account
                                                                3. DECIDE what to do
                                                                4. dispatch play(s)
                                                                5. record observation + schedule follow-up
                                                                          ↓
                         ┌─── PLAYS (deterministic SequentialAgent) ──────────────────┐
                         │  Risk/Save: Research → [Strategist ⟲ Critic] → Persist → Surface │
                         │  Meeting Brief · Support · Inbound                                 │
                         └──────────────────────────────────────────────────────────────────┘
                                                                          ↓
                                          ┌── SPECIALISTS (small, reusable sub-agents) ──┐
                                          │  Researcher · Strategist · Critic            │
                                          └──────────────────────────────────────────────┘
```

---

## End-to-end lifecycle (the demo path)

1. **Trigger** — `POST /agents/orchestrator/demo-agent` seeds a real "went dark" `Signal` row for the target customer and enqueues an `AgentTask`. Re-runs auto-reset prior demo artifacts so they never duplicate.

2. **Claim** — The consumer drains the queue. It claims the task with a guarded compare-and-swap: `pending → in_progress` conditionally; `affected_rows == 1` is the win. No double-processing without `SELECT FOR UPDATE`.

3. **Investigate** — The worker loads scoped context (who we are, workspace mission, customer profile) and calls `investigate_account` + `memory_recall` to build a picture of the account.

4. **Decide** — Open-ended reasoning via `PlanReActPlanner`: "champion departed, usage down 60%, renewal in 60 days → save situation." It chooses to run the Risk/Save play. This is **not a lookup table** — the path depends on what the worker finds.

5. **Execute play** — Dispatched as an ADK `AgentTool`. For Risk/Save:
   - **Researcher** gathers evidence (signals, threads, stakeholders, meetings, strategy memo)
   - **Strategist** produces structured output: risk level (1–5), evidence bullets, save steps with owners and timelines
   - **Critic** scores the plan 1–5 and gives feedback
   - **Gate** — if score < 4, the LoopAgent runs the strategist once more with feedback; if score ≥ 4, escalates to stop
   - **Persist** — `artifacts.py` writes real `RiskBrief` + `RiskPlayStep` rows to Postgres
   - **Surface** — creates a real `renewal_at_risk` Need in the Today queue

6. **Close the loop** — The worker records an account observation (visible in the customer's activity rail) and **self-schedules a follow-up** `AgentTask` 3 days out via `scheduledFor`.

7. **Stream + complete** — Every stage streams progress to Firestore (`load_context → research → strategist → critic → persist → surface → done`, 10→100%). The `AgentTask` and `AgentRun` are marked complete.

Everything renders from **real Postgres rows** — zero UI mocks.

---

## The self-critique loop

The Strategist → Critic → [optionally revise] loop is the quality gate for every play:

```
Strategist  →  structured output (risk level, evidence, save steps)
                        ↓
                     Critic  →  score: 1–5, feedback text
                        ↓
              score ≥ 4 → escalate (stop)
              score < 4 → send feedback back to Strategist (loop once)
                        ↓
              revised output → Persist
```

The self-review score surfaces on the created Need (`[self-review: 5/5]`) so the CSM knows whether the plan went through one or two passes.

---

## HITL (Human-in-the-Loop)

The worker can pause mid-flight by calling `ask_human`. This:
1. Sets the `AgentTask` status to `waiting` and stores `blockingNeedId`
2. Creates a `sidekick_question` Need in the Today queue with the question
3. When the CSM answers via `POST /api/workspaces/:id/agent-runs/:id/answers`, the consumer resumes the task from where it paused

This reuses the same HITL infrastructure as the handoff agent — the worker just calls the same `/answers` endpoint.

---

## ADK primitives used

| Need | Primitive |
|------|-----------|
| Autonomous worker with open-ended reasoning | `LlmAgent` + `PlanReActPlanner` |
| Deterministic play execution | `SequentialAgent` |
| Self-critique and revision loop | `LoopAgent` (gate escalates to stop) |
| Typed specialist output | Pydantic `output_schema` |
| Stage-to-stage data passing | `output_key` + shared session `state` |
| Play dispatched as a tool | `AgentTool` wrapping a `SequentialAgent` |
| Runaway guardrail | `RunConfig(max_llm_calls=60)` |
| Sessions, memory, artifacts | ADK `SessionService`, `MemoryService`, `ArtifactService` |
| Cross-cutting callbacks | `before_agent` / `after_agent` callbacks (streaming, Langfuse tracing) |

---

## Directory structure

```
orchestrator/
├── worker/
│   └── agent.py          # Autonomous LlmAgent + PlanReActPlanner
├── plays/
│   ├── risk_save.py       # Risk/Save SequentialAgent (the live demo play)
│   ├── meeting_brief.py   # Meeting prep brief
│   ├── support.py         # Support triage + response
│   └── inbound_fixtures.py# Inbound request handling
├── specialists/
│   ├── researcher.py      # Evidence gathering sub-agent
│   ├── risk_strategist.py # Risk assessment + save steps (structured output)
│   ├── critic.py          # Self-review scorer
│   ├── consolidator.py    # Memory write path (post-event reconciliation)
│   ├── meeting_writer.py  # Meeting brief drafter
│   ├── support.py         # Support responder
│   └── schemas.py         # Pydantic output schemas
├── queue/
│   ├── repository.py      # AgentTask CRUD + lifecycle (enqueue/claim/pause/resume/complete/fail)
│   └── consumer.py        # Drains queue, claims tasks, invokes worker
├── memory/
│   ├── context.py         # Scoped context assembly (user + workspace + customer → markdown)
│   ├── recall.py          # On-demand memory lookups
│   └── ingest.py          # Post-event memory consolidation (write path)
├── runtime/
│   ├── runner.py          # Builds ADK Runner + RunConfig
│   ├── services.py        # Session, Memory, Artifact service factories
│   ├── callbacks.py       # Progress streaming, Langfuse integration
│   └── state.py           # Shared session state key constants
├── artifacts.py           # DB writes: RiskBrief, RiskPlayStep, Need, Observation (real rows)
└── demo/
    ├── fixture.py         # Northcrest demo workspace fixture (single source of truth)
    ├── seeder.py          # Turns fixture into real DB rows
    ├── reset.py           # Idempotent reset for re-runs
    └── ids.py             # Deterministic ID generation for demo rows
```

---

## Available plays

| Play | Trigger | What it produces |
|------|---------|-----------------|
| `risk_save` | Worker decides account is at risk | `RiskBrief` + `RiskPlayStep` rows + `renewal_at_risk` Need |
| `meeting_brief` | Meeting within 24–48 hours | Meeting prep brief with talking points and open items |
| `support` | Frustrated signal or unresolved support need | Triage assessment + recommended response |
| `inbound_fixtures` | Customer inbound request | Routed response + any follow-up needs |

The worker can also decide **not** to run any play — recording an observation and scheduling a check-in is a valid outcome.

---

## Queue semantics

`AgentTask` states: `pending → in_progress → completed | failed | waiting (HITL)`

**Claim** uses a guarded optimistic compare-and-swap through the GraphQL layer (DataConnect has no `SELECT FOR UPDATE`):
```sql
UPDATE AgentTask SET status='in_progress' WHERE id=? AND status='pending'
-- affected_rows == 1 → won the claim
-- affected_rows == 0 → lost the race, skip
```

**Self-scheduling**: Plays enqueue their own follow-up `AgentTask` with `scheduledFor = now + 3 days`. The `/sweep` endpoint (Cloud Scheduler in prod) drains due tasks.

**HITL via queue**: When the worker calls `ask_human`, the task transitions to `waiting` with `blockingNeedId`. Answering the need via the existing `/answers` endpoint transitions it back to `pending`, and the next sweep picks it up.

---

## Feature flag

`ORCHESTRATION_ENABLED` env var (default `false`). When false, the orchestrator router, queue, and consumer are never imported — the backend behaves exactly as before. Flip and restart to enable; flip back and restart to revert with zero data loss.

---

## API endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /agents/orchestrator/demo-agent` | Demo producer: reset + seed + enqueue for target customer |
| `POST /agents/orchestrator/sweep` | Drain due tasks (Cloud Scheduler in prod; `curl` in dev) |
| `POST /agents/orchestrator/huddle-mention` | Handle `@sidekick` mention in a huddle (flag-gated) |
| `GET /api/workspaces/:id/agent-runs` | List agent runs (HITL UI) |
| `POST /api/workspaces/:id/agent-runs/:id/answers` | Submit HITL answers → resumes waiting task |

---

## How to run the demo

```bash
# Requires ORCHESTRATION_ENABLED=true in backend/.env + backend restart

# Trigger the demo (targets Bevelpoint Logistics by default)
curl -X POST http://localhost:8081/agents/orchestrator/demo-agent \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# Watch it run (the Today queue updates in real-time via Firestore)
# Then drain any scheduled follow-ups
curl -X POST http://localhost:8081/agents/orchestrator/sweep \
  -H "Authorization: Bearer $TOKEN"
```
