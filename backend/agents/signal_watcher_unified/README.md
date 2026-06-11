# SignalWatcher Unified Ingestion Pipeline

**Status**: ✅ **PRODUCTION** - This is the active ingestion pipeline

## Overview

This is the **production** SignalWatcher that processes ALL customer interactions (Gmail, Slack, Calendar, Notion) through a unified pipeline.

## Key Components

### `event_processor.py` - PRODUCTION (Main Entry Point)

The deterministic event processor that:
- Receives `ChangeEvent` objects from webhooks
- Resolves customer via cascade (stakeholder → domain → NULL)
- Classifies events using deterministic rules
- Routes to appropriate handlers

**Flow**:
```
Webhook → EventEmitter → ChangeEvent → EventProcessor → Routing
                                            ↓
                      new_customer → HandoffAuto agent
                      structured_field_update → direct sync
                      unstructured_content → Thread + Interaction
                      unknown_sender → drop
```

**Used By**:
- `routes/webhooks.py` - Gmail, Slack, Calendar webhooks
- `integrations/slack/bolt_app.py` - Slack Bolt handlers
- `routes/internal.py` - Polling fallback

### Other Files (Historical)

- `agent.py` - Old autonomous agent approach (not used in production)
- `loop_controller.py` - Pause/resume logic (not used in production)
- `confidence.py` - Confidence assessment (not used in production)

## Architecture

**Deterministic Processing**:
- ✅ No LLM decision-making in routing
- ✅ Sequential event processing
- ✅ Predictable, testable behavior

**Not Autonomous**:
Despite the historical "auto" folder name, this does NOT use autonomous agents.
The name is misleading - this is deterministic, sequential processing.

## Production Requirements

See `docs/SIGNAL_WATCHER_PRODUCTION_READINESS.md` for:
- Critical production gaps
- Error handling requirements
- Performance limits
- Monitoring setup
- Testing requirements

## Usage

```python
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor

processor = SignalWatcherEventProcessor(workspace_id)
processed_events = await processor.process_events(events)
```

## Related Documentation

- `docs/SIGNAL_WATCHER_PRODUCTION_READINESS.md` - Production checklist
- `docs/UNIFIED_INGESTION_ARCHITECTURE.md` - Architecture design
- `docs/SIGNAL_WATCHER_ACTION_PLAN.md` - Migration plan
