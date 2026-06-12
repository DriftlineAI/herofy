# Signal Watcher

**What it does**: Turns every inbound Gmail message, Slack event, Calendar notification, and Notion change into a structured customer signal — routing each event to the right handler, creating interaction records, classifying content via LLM, surfacing significant signals as needs in the Today queue, and triggering the handoff agent whenever a new deal lands in Notion.

---

## The problem it solves

Every customer interaction happens somewhere else: an email thread, a Slack channel, a calendar invite, a Notion deal page. Without automation, those signals either go unseen or get manually triaged — which doesn't scale past 20 accounts. The signal watcher is the ingestion layer that watches all of those surfaces and translates raw events into structured context the rest of the system can act on.

---

## Architecture

The signal watcher is **event-driven, not polled**. Webhooks from Gmail, Slack, Calendar, and Notion emit `ChangeEvent` objects. The `SignalWatcherEventProcessor` processes each event through a four-step cascade:

```
Webhook (Gmail push / Slack Events / Calendar / Notion)
    ↓
routes/webhooks.py  →  SignalWatcherEventProcessor.process_events(events)
                              ↓
                    1. Dedup by fingerprint (skip already-processed)
                    2. Resolve customer (stakeholder email → domain → unknown)
                    3. Classify event type (deterministic, no LLM)
                    4. Route to handler
                              ↓
              ┌───────────────┼───────────────┬──────────────────┐
              ↓               ↓               ↓                  ↓
       NEW_CUSTOMER   STRUCTURED_FIELD   UNSTRUCTURED        UNKNOWN
       (Notion deal)   UPDATE (Notion      CONTENT             SENDER
                        field change)    (Gmail/Slack msg,
                                          Notion content)
              ↓               ↓               ↓                  ↓
      Create customer   Sync field to   Thread + Interaction  Quarantine
      + enrich          Customer row    + LLM classification  thread
      + trigger            (no LLM)     + Signal/Need
      HandoffAuto                       + route to orchestrator
```

---

## Four event handlers

### `NEW_CUSTOMER` — Notion deal page created
When Notion fires a webhook for a new CRM record:
1. **Create Customer** via `CustomerFactory` — maps Notion properties to Customer fields using the workspace's configured field mappings
2. **Auto-link Notion page** — fetches and stores the page body so agents have rich context
3. **Enrichment** — runs `enrich_single_customer` to pull additional data (best-effort)
4. **Trigger HandoffAuto** — invokes the handoff agent with the new `customer_id`; the agent reads the Notion page and builds the brief + plan

### `STRUCTURED_FIELD_UPDATE` — Notion property changed
When a mapped field changes (ARR, lifecycle, tier, etc.):
- Syncs directly to the Customer row via explicit DataConnect mutations
- No LLM involved — pure deterministic field mapping
- Security: uses a hardcoded allowlist of fields and per-field mutations (no dynamic SQL)

### `UNSTRUCTURED_CONTENT` — Gmail/Slack message or Notion content update
The main path for ongoing customer signals:
1. **Thread management** — finds or creates the Thread by `externalThreadId`; links message to customer
2. **Interaction record** — creates an `Interaction` row with direction, sender, body, timestamp
3. **OOO detection** — checks for out-of-office autoreplies before updating engagement metrics
4. **Response latency** — pairs inbound replies against our last outbound to measure response time
5. **LLM signal classification** (`SignalClassificationService`) — determines if the content is routine, informational, or action-required; creates `Signal` row + `Need` if confidence ≥ 70%
6. **Thread→Need link** — links the thread to the first created need so Today queue and Conversations show the same item
7. **Route to orchestrator** — significant signals (with `signal_kind` + `signal_state`) are enqueued as `AgentTask` for the autonomous worker to investigate

### `UNKNOWN_SENDER` — Email or Slack from an unrecognized contact
- Creates a quarantined thread under a special "Unknown Contacts" pseudo-customer
- Preserves the message content for manual review

---

## Customer resolution cascade

Every inbound event goes through the same resolution before classification:

```
1. Exact stakeholder email match
        ↓ (if no match)
2. Domain match against customer domains
   (personal domains like gmail.com skipped)
   → auto-creates Stakeholder record on match
        ↓ (if no match)
3. UNKNOWN_SENDER → quarantine
```

---

## Calendar events

Calendar events take a parallel path through `_handle_calendar_event`:
- **created** → creates or updates a `Meeting` row; if the meeting is within 48 hours, creates a `meeting_prep_ready` need (priority scales with imminence: <4h = urgent, <24h = today, <48h = tomorrow)
- **canceled** → soft-deletes the Meeting (status = "canceled")

---

## What gets written to the database

| Entity | When |
|--------|------|
| `Customer` | New Notion deal (via CustomerFactory) |
| `Stakeholder` | Auto-created on domain match |
| `Thread` | First message in a conversation |
| `Interaction` | Every Gmail/Slack message |
| `Meeting` | Calendar event created/modified |
| `Signal` | LLM classifies content as significant |
| `Need` | Signal confidence ≥ 70%, or meeting prep |
| `AgentTask` | Significant signals enqueued for orchestrator |
| `ChangeEvent` | Marked processed + artifacts attached |

---

## Key files

| File | Purpose |
|------|---------|
| `event_processor.py` | The production processor — classification cascade + all four handlers |
| `agent.py` | Legacy autonomous loop entry point (not used in production routing) |
| `loop_controller.py` | Legacy pause/resume state machine (not used in production routing) |
| `confidence.py` | Legacy batch confidence scoring (not used in production routing) |

---

## How to invoke

```python
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor

processor = SignalWatcherEventProcessor(workspace_id)
processed_events = await processor.process_events(events)
```

In development, webhooks can be injected via the test harness:

```bash
# Inject a Gmail message event
curl -X POST http://localhost:8081/test/gmail-message \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"sender_email": "cto@customer.com", "subject": "Re: onboarding", "body": "..."}'

# Inject a Slack event
curl -X POST http://localhost:8081/test/slack-message ...

# Inject a Calendar event
curl -X POST http://localhost:8081/test/calendar-event ...
```

---

## Design philosophy

The signal watcher's job is to make every customer touchpoint legible to the rest of the system — without surfacing noise. Routing is deterministic so behavior is predictable and testable. The LLM only enters at the signal classification step, where the question is genuinely semantic: is this message routine or does it indicate something that needs a CSM's attention today?
