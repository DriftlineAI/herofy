"""
Fake inbound support emails for pressure-testing the light lane (support_triage).

Each fixture is a dict with `profile` (the intended test case), `subject`, and `body`.
The test harness in routes/agents.py (`/agents/pipeline-test/inbound`) sends these
through `run_inbound_support` round-robin across the workspace's customers so we can
compare the classifier's verdict against the intended profile.

Spread:
  - simple-question  : neutral, simple — should draft a plain reply, no escalation
  - complex-technical: detailed multi-part problems — concerned/neutral, complex
  - murky            : vague/ambiguous — unclear what's wrong
  - simple-angry     : trivial issue, furious tone — escalation pressure from sentiment
  - billing          : payment/charge issues
  - positive         : thank-you / praise — should NOT be actionable or escalate
"""

INBOUND_FIXTURES = [
    # ── simple questions ──────────────────────────────────────────────────────
    {
        "profile": "simple-question",
        "subject": "How do I export my data to CSV?",
        "body": (
            "Hi there, quick question — I'm trying to pull our weekly numbers into a "
            "spreadsheet but I can't find an export option anywhere. Is there a way to "
            "download a report as a CSV? Thanks!"
        ),
    },
    {
        "profile": "simple-question",
        "subject": "Where do I find my API key?",
        "body": (
            "Hello, our developer is setting up the integration and asked me for our API "
            "key. I poked around the settings but didn't see it. Where would I find that? "
            "Appreciate the help."
        ),
    },
    {
        "profile": "simple-question",
        "subject": "Adding a second seat",
        "body": (
            "Hi — we just hired someone who'll be using the platform with me. How do I add "
            "a second seat to our account? Want to make sure she's set up before Monday."
        ),
    },
    {
        "profile": "simple-question",
        "subject": "Change notification email",
        "body": (
            "Quick one: the alert emails are going to my old work address. Can you tell me "
            "where I update the email that notifications get sent to? Thanks in advance."
        ),
    },
    # ── complex technical ─────────────────────────────────────────────────────
    {
        "profile": "complex-technical",
        "subject": "Webhook deliveries failing intermittently",
        "body": (
            "We're seeing roughly 30% of our webhook deliveries fail with a 504 since last "
            "Thursday. Our endpoint hasn't changed and responds in under 200ms on our side, "
            "so I suspect the retry logic is timing out before our handler acknowledges. "
            "Can someone look at the delivery logs for our account and tell me what timeout "
            "you're enforcing? Happy to share request IDs."
        ),
    },
    {
        "profile": "complex-technical",
        "subject": "Data sync mismatch between your API and our warehouse",
        "body": (
            "We sync your records nightly into BigQuery, and over the last week the row "
            "counts have drifted — your API reports ~14,200 active records but we're only "
            "ingesting ~13,750. Pagination cursors look correct and we're not hitting rate "
            "limits. Is it possible records are being soft-deleted and dropping out of the "
            "list endpoint mid-pagination? We'd like to understand the consistency model "
            "before we trust this data downstream."
        ),
    },
    {
        "profile": "complex-technical",
        "subject": "OAuth refresh token rotation breaking our integration",
        "body": (
            "After your update last week our integration started getting invalid_grant "
            "errors on refresh. It looks like you've moved to rotating refresh tokens, but "
            "your changelog didn't mention it and our stored token is now dead. We have "
            "about 40 customers connected through this integration who are all disconnected "
            "right now. What's the correct flow to re-establish these without forcing every "
            "customer to re-auth manually?"
        ),
    },
    # ── murky / ambiguous ─────────────────────────────────────────────────────
    {
        "profile": "murky",
        "subject": "Something feels off with the numbers",
        "body": (
            "I can't quite put my finger on it, but the dashboard numbers don't feel right "
            "this month. Nothing is obviously broken, it just doesn't match what I'd expect. "
            "Could someone take a look and let me know if everything is calculating normally?"
        ),
    },
    {
        "profile": "murky",
        "subject": "Not sure this is working right",
        "body": (
            "Hey, I set everything up a couple weeks ago but I'm honestly not sure it's "
            "actually doing anything. I haven't seen the kind of results I was expecting. "
            "Is there a way to confirm it's configured correctly?"
        ),
    },
    {
        "profile": "murky",
        "subject": "Is this expected behavior?",
        "body": (
            "When I click into a record and then go back, the filters I had set reset "
            "themselves. Is that supposed to happen? Maybe I'm doing something wrong, but it "
            "seems odd. Just wanted to check before I report it as a bug."
        ),
    },
    # ── simple but ANGRY ──────────────────────────────────────────────────────
    {
        "profile": "simple-angry",
        "subject": "WHY is the export STILL broken??",
        "body": (
            "This is the THIRD time I've written about the CSV export not working and I'm "
            "completely out of patience. I have a board meeting in two hours and I CANNOT "
            "get my data out. How is this still not fixed? Someone needs to call me NOW."
        ),
    },
    {
        "profile": "simple-angry",
        "subject": "Absolutely unacceptable — I can't log in",
        "body": (
            "I have been locked out of my own account for the entire morning and your reset "
            "link does nothing. This is absolutely unacceptable for something we pay for. "
            "Fix it immediately, I have work to do and you're costing me time."
        ),
    },
    {
        "profile": "simple-angry",
        "subject": "Are you people even testing this?",
        "body": (
            "Every single update breaks something else. Today a button that worked yesterday "
            "just spins forever. Are you people even testing this before you ship it? I'm "
            "starting to wonder why we're paying you at all."
        ),
    },
    {
        "profile": "simple-angry",
        "subject": "Tired of repeating myself",
        "body": (
            "I've explained this issue twice already and nobody has done anything. The "
            "search bar returns zero results no matter what I type. It's a SEARCH BAR. How "
            "hard can this be? I expect a real answer this time, not another canned reply."
        ),
    },
    # ── billing ───────────────────────────────────────────────────────────────
    {
        "profile": "billing",
        "subject": "Got double charged this month",
        "body": (
            "Hi — I'm looking at our card statement and it shows two identical charges from "
            "you on the same day this month. We should only be billed once. Can you refund "
            "the duplicate and let me know what happened? Thanks."
        ),
    },
    {
        "profile": "billing",
        "subject": "Need to update our payment method",
        "body": (
            "Our company card was reissued with a new number, so the one on file will start "
            "declining soon. Where do I go to update the payment method so our subscription "
            "doesn't lapse? Want to take care of it before the next billing date."
        ),
    },
    # ── positive / thank-you ──────────────────────────────────────────────────
    {
        "profile": "positive",
        "subject": "The new reporting feature is great",
        "body": (
            "Just wanted to say the new reporting view you rolled out is fantastic — it's "
            "already saving my team a ton of time on Monday morning prep. Whoever built it, "
            "please pass along our thanks!"
        ),
    },
    {
        "profile": "positive",
        "subject": "Thanks for the quick fix last week",
        "body": (
            "Hey, I never followed up but I wanted to thank you for jumping on that sync "
            "issue so quickly last week. Everything's been running smoothly since. Really "
            "appreciate the responsiveness — it's a big reason we stick with you."
        ),
    },
]
