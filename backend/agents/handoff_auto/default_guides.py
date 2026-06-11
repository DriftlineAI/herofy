"""
Smart Default Guides for Autonomous Agent

These are prompt fragments that provide reasonable defaults when
handbook docs don't exist for a workspace. They serve as fallback
guidance until the customer configures their own guides.

Guide naming follows the "How we..." pattern from the original design:
- How we onboard customers
- How we define success
- How we think about relationships
- How we prioritize attention
- What our customers care about
- How we define going dark

For this implementation, we focus on the two most critical for onboarding:
- how-we-onboard-customers
- how-we-define-success
"""

from typing import Optional


DEFAULT_GUIDES: dict[str, str] = {
    "how-we-onboard-customers": """
## How We Onboard Customers (Default Guide)

Our standard onboarding approach follows a milestone-based structure:

### Phase 1: Kickoff (Days 1-3)
- Introduction call with key stakeholders
- Set clear expectations and success criteria
- Identify primary champion and technical lead
- Agree on communication cadence (typically weekly)

### Phase 2: Technical Setup (Days 4-14)
- Core integrations configured
- Data migration or import completed
- SSO/security setup if enterprise
- Initial configuration validated

### Phase 3: Training (Days 15-21)
- Admin training sessions
- End-user training sessions
- Documentation and resources handoff
- Q&A and troubleshooting

### Phase 4: Go-Live (Days 22-30)
- Production deployment
- Hypercare period with rapid response
- First value milestone achieved
- Success review with stakeholders

### Key Principles
- Every customer gets a dedicated point of contact
- Weekly check-ins during active onboarding
- Success metrics defined in kickoff, measured at go-live
- Escalate blockers within 24 hours - don't let them linger
- Celebrate milestones with stakeholders to build momentum
- Document learnings for future customers in this segment
""",

    "how-we-define-success": """
## How We Define Success (Default Guide)

A customer is considered successful when they achieve VALUE from our product.

### Success Indicators by Lifecycle

**Onboarding Success:**
- Completed onboarding within target timeline
- All critical milestones achieved
- Primary use case is live in production
- At least one key stakeholder is proficient

**Active Customer Success:**
- Regular product usage (weekly or better for core features)
- Positive sentiment in communications
- Expanding use cases or users over time
- Proactive engagement (asking questions, requesting features)

**Renewal Success:**
- Proactive renewal discussion (not reactive)
- Clear value articulation from customer
- Expansion opportunities identified
- Multi-year or expanded contract

### Warning Signs (NOT Successful)

- Champion has departed with no identified replacement
- Product usage trending down for 30+ days
- Multiple escalations without satisfactory resolution
- Missed milestones without clear communication
- Going dark: No response to outreach for 7+ days
- Frustrated sentiment in recent communications

### How We Measure

1. **Adoption**: Are they using the core features we sold them?
2. **Engagement**: Are stakeholders responsive and active?
3. **Value**: Can they articulate the value they're receiving?
4. **Health**: Are there any warning signals in their behavior?

When in doubt, ask: "Would this customer enthusiastically recommend us?"
""",

    "how-we-define-going-dark": """
## How We Define Going Dark (Default Guide)

A customer is "going dark" when communication has broken down.

### Triggers

A customer should be flagged as going dark when ANY of these occur:

1. **No response to outreach**
   - 2+ attempts over 7 days with no reply
   - Includes email, Slack, and calendar invites

2. **Missed meetings**
   - No-show to scheduled call without prior notice
   - Declined meeting with no reschedule

3. **Usage drop**
   - No product activity for 14+ days
   - Significant decline (>50%) from baseline

### Response Protocol

1. **Day 1-3**: Alternate channels (try Slack if email silent)
2. **Day 4-7**: Escalate to secondary contact or champion's manager
3. **Day 7+**: Flag as at-risk, consider executive outreach

### Don't Overreact

Some silence is normal:
- Holidays and vacation periods
- End of quarter/fiscal year busy periods
- Known company events (M&A, reorgs)

Check context before escalating.
""",
}


def get_default_guide(slug: str) -> Optional[str]:
    """
    Get a default guide by slug.

    Args:
        slug: The guide identifier (e.g., "how-we-onboard-customers")

    Returns:
        The default guide content, or None if no default exists for this slug
    """
    return DEFAULT_GUIDES.get(slug)


def get_default_guide_for_topic(topic: str) -> Optional[str]:
    """
    Get a default guide by topic keyword.

    Matches common topics to their guide slugs:
    - "onboarding", "onboard" -> how-we-onboard-customers
    - "success", "successful" -> how-we-define-success
    - "dark", "silent", "going dark" -> how-we-define-going-dark

    Args:
        topic: A keyword or phrase describing the topic

    Returns:
        The default guide content, or None if no match
    """
    topic_lower = topic.lower()

    if any(kw in topic_lower for kw in ["onboard", "implementation", "kickoff", "go-live"]):
        return DEFAULT_GUIDES.get("how-we-onboard-customers")

    if any(kw in topic_lower for kw in ["success", "successful", "value", "outcome"]):
        return DEFAULT_GUIDES.get("how-we-define-success")

    if any(kw in topic_lower for kw in ["dark", "silent", "unresponsive", "ghosting"]):
        return DEFAULT_GUIDES.get("how-we-define-going-dark")

    return None


def get_all_default_guides() -> dict[str, str]:
    """
    Get all default guides.

    Returns:
        Dictionary mapping slug to guide content
    """
    return DEFAULT_GUIDES.copy()


def get_onboarding_defaults_summary() -> str:
    """
    Get a condensed summary of onboarding defaults for injection into agent prompts.

    This is a shorter version suitable for including in system instructions
    when no handbook exists.
    """
    return """
## Default Onboarding Guidance

Since no custom handbook exists for this workspace, use these defaults:

**Standard Timeline:** 30 days (Kickoff → Setup → Training → Go-Live)

**Key Milestones:**
1. Kickoff call completed (Day 1-3)
2. Technical setup complete (Day 14)
3. Training delivered (Day 21)
4. Go-live achieved (Day 30)

**Success Criteria:**
- Primary use case live in production
- Key stakeholder proficient
- Customer can articulate value

**Red Flags to Watch:**
- Champion departed
- Usage declining
- Going dark (7+ days no response)
- Multiple unresolved escalations

Ask the customer to define THEIR success criteria - these are just defaults.
"""
