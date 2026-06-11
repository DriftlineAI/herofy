# SignalWatcher Legacy (DEPRECATED)

**Status**: ❌ **DEPRECATED** - Do NOT use in production

## ⚠️ Warning

This is the **old** SignalWatcher implementation using the `RawSignal` model.

**DO NOT USE THIS CODE**. Use `signal_watcher_unified` instead.

## Why Deprecated?

1. **Old data model**: Uses `RawSignal` instead of `ChangeEvent`
2. **Pull-based**: Fetches signals directly from sources (not webhook-driven)
3. **Not event-driven**: Doesn't integrate with unified ingestion pipeline
4. **Not used**: Production webhooks use `signal_watcher_unified`

## Migration Path

If you're using this code, migrate to:
```python
# OLD (deprecated)
from agents.signal_watcher_legacy import run_signal_watcher_chain

# NEW (production)
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor
```

## What to Use Instead

### For Production Event Processing
Use `signal_watcher_unified/event_processor.py`:
```python
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor

processor = SignalWatcherEventProcessor(workspace_id)
processed = await processor.process_events(change_events)
```

### For Webhook Handling
Webhooks already use the unified pipeline:
- `routes/webhooks.py` - Gmail, Slack, Calendar
- `integrations/slack/bolt_app.py` - Slack Bolt

### For Polling/Batch Processing
Use event emitters:
```python
from services.event_emitters.gmail_emitter import GmailEventEmitter

emitter = GmailEventEmitter(workspace_id, integration_service)
events = await emitter.poll_and_emit()
```

## Removal Timeline

- **Now**: Marked as DEPRECATED
- **+30 days**: Remove endpoints from `routes/agents.py`
- **+90 days**: Delete folder entirely

## Questions?

See:
- `docs/SIGNAL_WATCHER_PRODUCTION_READINESS.md`
- `docs/UNIFIED_INGESTION_ARCHITECTURE.md`
- `signal_watcher_unified/README.md`
