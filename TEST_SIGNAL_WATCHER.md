# Testing SignalWatcher Pipeline Locally

This guide shows how to test the complete SignalWatcher pipeline end-to-end **without deploying** to GCP or configuring external webhooks.

## What This Tests

The test endpoint simulates the full pipeline:
1. **Fake email/Slack payload** → GmailEventEmitter/SlackEventEmitter
2. **ChangeEvent creation** with customer resolution cascade
3. **Persistence** to `change_events` table (with fingerprint dedup)
4. **SignalWatcher processing** (classification, routing, LLM if needed)
5. **Artifact creation** (Threads, Interactions, Signals, Needs)

This validates that the entire pipeline works **before you deploy and configure Pub/Sub, OAuth, etc.**

---

## Prerequisites

1. **Backend running locally**:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn main:app --reload --port 8081
   ```

2. **Firebase SQL Connect emulator running** (OR connect to CloudSQL):
   ```bash
   firebase emulators:start --only dataconnect --project herofy-496505
   ```

3. **Regenerate SDK** (we added a new query):
   ```bash
   firebase dataconnect:sdk:generate --project herofy-496505
   ```

4. **Demo scenario seed data loaded** (Northcrest workspace + customers):
   - Follow `docs/DEMO_SCENARIO.md` to create Northcrest customers in your database
   - Note the workspace ID (you'll need it for testing)

---

## Quick Test (Automated Script)

```bash
# Edit the script to set your workspace ID
nano test-signal-watcher.sh

# Change this line:
WORKSPACE_ID="your-workspace-id-here"  # Replace with Northcrest workspace ID

# Run the test
./test-signal-watcher.sh
```

This will run 4 tests:
1. Frustrated email from Aperio Analytics (escalated customer)
2. Positive email from Marlin Insights (new customer)
3. At-risk email from Foldwise (customer with complaints)
4. Unknown sender (personal email, should be filtered)

---

## Manual Test (cURL)

### Test 1: Gmail from Known Stakeholder

```bash
curl -X POST "http://localhost:8081/test/gmail-message?workspace_id=YOUR_WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "liam@aperioanalytics.com",
    "from_name": "Liam Carter",
    "subject": "Re: Postmortem document - still waiting",
    "body": "Marcus, Nina is asking for an update. This is affecting our confidence in the partnership.",
    "message_id": "test-001",
    "thread_id": "thread-001"
  }'
```

**Expected Result**:
```json
{
  "success": true,
  "change_event_id": "uuid-here",
  "customer_id": "uuid-of-aperio",
  "event_class": "unstructured_content",
  "artifacts_created": {
    "interactions": ["uuid"],
    "signals": ["uuid"],
    "needs": ["uuid"]
  },
  "processing_error": null,
  "steps": [
    "Creating fake Gmail message payload",
    "Converting to ChangeEvent via GmailEventEmitter",
    "ChangeEvent created: uuid",
    "Customer resolved: uuid",
    "Persisting ChangeEvent to database",
    "Processing via SignalWatcherEventProcessor",
    "SignalWatcher processing completed",
    "Artifacts created: {...}"
  ]
}
```

### Test 2: Slack from Known Stakeholder

```bash
curl -X POST "http://localhost:8081/test/slack-message?workspace_id=YOUR_WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "user_email": "sarah@marlininsights.com",
    "user_name": "Sarah Chen",
    "text": "Excited about the kickoff! Quick question on the Outreach connector timeline.",
    "channel_id": "C123456",
    "channel_name": "marlin-implementation",
    "timestamp": "1234567890.123456"
  }'
```

### Test 3: Unknown Sender (Should Be Filtered)

```bash
curl -X POST "http://localhost:8081/test/gmail-message?workspace_id=YOUR_WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "spam@gmail.com",
    "from_name": "Random Person",
    "subject": "Random inquiry",
    "body": "This should be filtered.",
    "message_id": "test-002",
    "thread_id": "thread-002"
  }'
```

**Expected**: `customer_id: null`, `event_class: "unknown_sender"`

---

## Verify Results

### Check ChangeEvents Table
```sql
SELECT
  id,
  source,
  source_event_type,
  customer_id,
  event_class,
  processed,
  processing_error
FROM change_events
WHERE workspace_id = 'YOUR_WORKSPACE_ID'
ORDER BY created_at DESC
LIMIT 10;
```

### Check Threads Created
```sql
SELECT
  id,
  customer_id,
  thread_type,
  subject,
  status,
  created_at
FROM threads
WHERE workspace_id = 'YOUR_WORKSPACE_ID'
ORDER BY created_at DESC;
```

### Check Interactions Created
```sql
SELECT
  i.id,
  i.thread_id,
  t.subject as thread_subject,
  i.direction,
  i.channel,
  i.body_snippet,
  i.sent_at
FROM interactions i
JOIN threads t ON t.id = i.thread_id
WHERE t.workspace_id = 'YOUR_WORKSPACE_ID'
ORDER BY i.sent_at DESC
LIMIT 10;
```

### Check Signals Created
```sql
SELECT
  id,
  customer_id,
  kind,
  state,
  sentence,
  confidence,
  created_at
FROM signals
WHERE workspace_id = 'YOUR_WORKSPACE_ID'
ORDER BY created_at DESC;
```

### Check Needs Created (Today Queue)
```sql
SELECT
  id,
  customer_id,
  need_type,
  headline,
  workflow_status,
  created_at
FROM needs
WHERE workspace_id = 'YOUR_WORKSPACE_ID'
ORDER BY created_at DESC;
```

---

## Troubleshooting

### Test fails with "GmailEventEmitter returned None"
- **Cause**: The email was filtered as a system email (noreply@, notifications@, etc.)
- **Fix**: Use a real-looking customer email address

### Test fails with "Could not fetch processed event from database"
- **Cause**: ChangeEvent wasn't persisted (duplicate fingerprint or DB error)
- **Fix**: Check the `steps` array in the response for the exact error

### Customer ID is None but should be resolved
- **Cause**: No stakeholder or customer domain match in database
- **Fix**:
  1. Check if customer exists: `SELECT * FROM customers WHERE domain = 'aperioanalytics.com'`
  2. Check if stakeholder exists: `SELECT * FROM stakeholders WHERE email = 'liam@aperioanalytics.com'`
  3. Make sure demo scenario seed data is loaded

### No Signals or Needs created
- **Cause**: LLM confidence was too low (< 0.7 for Needs, < 0.5 for Signals)
- **Expected**: Not all emails should create Needs - only high-confidence ones
- **Check**: Look at the signals table to see if a Signal was created (even if no Need)

### Event Class is null
- **Cause**: SignalWatcher classification failed
- **Fix**: Check processing_error in change_events table

---

## Understanding the Steps Array

Each test response includes a `steps` array showing exactly what happened:

```json
{
  "steps": [
    "Creating fake Gmail message payload",        // ✓ Payload created
    "Converting to ChangeEvent via GmailEventEmitter",  // ✓ Emitter called
    "ChangeEvent created: abc123",                // ✓ ChangeEvent object created
    "Customer resolved: def456",                  // ✓ Customer linkage succeeded
    "Fingerprint: xyz789",                        // ✓ Dedup fingerprint computed
    "Persisting ChangeEvent to database",         // ✓ Database insert
    "ChangeEvent persisted successfully",         // ✓ No duplicate detected
    "Processing via SignalWatcherEventProcessor", // ✓ EventProcessor invoked
    "SignalWatcher processing completed",         // ✓ Processing succeeded
    "Fetching processed ChangeEvent from database", // ✓ Verification
    "Artifacts created: {...}"                    // ✓ Results available
  ]
}
```

If a step is missing, that's where the failure occurred.

---

## What This Does NOT Test

These features require deployed infrastructure and cannot be tested locally:

- ❌ Gmail Pub/Sub push notifications (requires public HTTPS URL + Pub/Sub topic)
- ❌ Slack Events API webhooks (requires public HTTPS URL + Slack app config)
- ❌ Calendar watch notifications (requires public HTTPS URL + valid SSL)
- ❌ OAuth flows (requires OAuth clients configured with redirect URIs)
- ❌ Cloud Scheduler jobs (requires deployed Cloud Run service)

Use this test to validate the **processing pipeline**. After deployment, test the **integration infrastructure** separately.

---

## Next Steps

Once local tests pass:
1. ✅ Deploy to Cloud Run (staging)
2. ✅ Configure Pub/Sub topic + subscription
3. ✅ Configure OAuth clients
4. ✅ Send real email to test Gmail integration
5. ✅ Test Slack integration (Socket Mode first, then webhooks)
6. ✅ Verify end-to-end: Email → Webhook → ChangeEvent → Artifacts → Today Queue
