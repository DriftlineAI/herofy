"""Structured outputs for specialists (ADK output_schema — native validation)."""

from typing import Literal

from pydantic import BaseModel, Field


class InboundClassification(BaseModel):
    """Lane-1 inbound triage: what is this message, how charged, how hard to answer."""

    category: Literal["question", "technical", "billing", "feature_request", "complaint", "other"] = Field(
        description="What kind of message this is."
    )
    sentiment: Literal["positive", "neutral", "negative", "frustrated", "angry"] = Field(
        description="Emotional charge of THIS message, read from the customer's actual words."
    )
    complexity: Literal["simple", "moderate", "complex"] = Field(
        description="How hard this is to answer: simple = a quick known answer; complex = needs investigation or engineering."
    )
    is_actionable: bool = Field(
        description="True if this needs a reply/action; False for a pure FYI, thank-you, or auto-notification."
    )
    summary: str = Field(description="One-line summary of what the customer is asking or reporting.")


class TechnicalTriageOutput(BaseModel):
    """Support triage: is this a technical problem, and how severe / who owns it."""

    is_technical: bool = Field(description="True if this is a technical problem/blocker (vs a question, billing, relationship).")
    severity: Literal["low", "medium", "high"] = Field(description="Impact/urgency of the reported issue.")
    impact: str = Field(description="One sentence: what the customer can't do / what's broken for them.")
    needs_engineering: bool = Field(description="True if this likely requires engineering (a real bug/outage), not just a CSM answer.")
    workaround: str = Field(default="", description="A short interim workaround if one is evident, else empty.")
    summary: str = Field(description="One-line triage summary for the CSM.")


class SupportResponseOutput(BaseModel):
    """The support responder's drafted reply (maps onto a DraftResponse)."""

    subject: str = Field(description="Reply subject line.")
    body: str = Field(description="On-voice reply: acknowledge, set expectations, give the next step / workaround. Ready to send after CSM review.")


class RiskStep(BaseModel):
    label: str = Field(description="A concrete save-play action, imperative voice.")
    rationale: str = Field(description="Why this step matters / what risk it addresses.")


class RiskSaveOutput(BaseModel):
    """The risk strategist's structured assessment + save play."""

    risk_level: Literal["low", "medium", "high"] = Field(
        description="Overall renewal/churn risk."
    )
    what_changed: str = Field(
        description="One or two sentences: what changed that created this risk."
    )
    evidence_text: str = Field(
        description="The concrete evidence (signals, usage, stakeholder changes)."
    )
    play_summary: str = Field(
        description="One-line summary of the recommended save play."
    )
    steps: list[RiskStep] = Field(
        description="3-5 ordered save-play steps the CSM should run.",
        min_length=1,
    )
    observation: str = Field(
        description="A short account-level observation/tip for the CSM activity feed."
    )


class RiskOutreachDraft(BaseModel):
    """The re-engagement email the save play drafts for the customer (maps onto a DraftResponse)."""

    subject: str = Field(description="Email subject line — warm, low-pressure, specific to this account.")
    body: str = Field(
        description=(
            "On-voice re-engagement email the CSM can send after a quick review. Acknowledge the "
            "silence lightly without guilt-tripping, lead with the customer's own goal/value, offer "
            "one concrete low-friction next step (a quick async check-in), and keep it short. No "
            "fabricated facts or dates; sign off as the CSM. Plain text, ready to send."
        )
    )


class FollowupEmailDraft(BaseModel):
    """Draft recap email to send after the meeting."""

    subject: str = Field(description="Email subject line (concise, e.g. 'Acme Q2 review — recap and next steps').")
    body: str = Field(
        description=(
            "Email body in plain text. 2-4 short paragraphs: "
            "(1) brief thank-you and what was covered, "
            "(2) key outcomes or wins to reference, "
            "(3) agreed next steps with owners/dates if known. "
            "Write in the CSM's voice — direct, warm, no filler."
        )
    )


class MeetingBriefOutput(BaseModel):
    """The meeting writer's structured prep brief (maps onto create_meeting_brief)."""

    progress_narrative: str = Field(
        description="Prose summary of progress since the last touchpoint (>= 50 chars)."
    )
    talking_points: list[str] = Field(
        description="Key points the CSM should raise in the meeting.", min_length=1
    )
    progress_facts: list[str] = Field(
        default_factory=list, description="Factual bullet points (milestones, metrics)."
    )
    friction: str = Field(default="", description="Current friction/blockers, if any.")
    value_delivered: str = Field(default="", description="Value delivered so far.")
    risk_to_renewal: str = Field(default="", description="Renewal-risk assessment, if relevant.")
    expansion_signals: str = Field(default="", description="Expansion opportunity signals, if any.")
    followup_email: FollowupEmailDraft | None = Field(
        default=None,
        description=(
            "Draft recap email for after the meeting. "
            "Always include this — it saves the CSM time on follow-up. "
            "Base subject + body on the talking points and account context."
        ),
    )


class VectorUpdate(BaseModel):
    """A reconciled state change for ONE existing ProgressVector."""

    vector_id: str = Field(description="The id of an existing ProgressVector to update (from the provided list ONLY).")
    new_state: Literal["ok", "warn", "risk"] = Field(description="The vector's state after this event.")
    reason: str = Field(description="One sentence: why this event moved the vector to that state.")


class ConsolidationOutput(BaseModel):
    """Extract→reconcile result: a refreshed account memory."""

    strategy_body: str = Field(
        description="The customer's living strategy memo (markdown), RECONCILED with the prior "
        "version — merge in what changed, keep what's still true, don't discard context."
    )
    vector_updates: list[VectorUpdate] = Field(
        default_factory=list,
        description="State updates for the existing progress vectors this event actually changed "
        "(empty if none). Only reference vector ids from the provided list.",
    )
    digest: str = Field(description="One line: what the system now understands about this account.")


class CriticVerdict(BaseModel):
    """The Critic's self-evaluation of a proposed save play."""

    approved: bool = Field(
        description="True if the play is good enough to ship to the CSM (no revision needed)."
    )
    score: int = Field(description="Quality score 1-5 (5 = excellent).", ge=1, le=5)
    coverage_gaps: list[str] = Field(
        default_factory=list,
        description="Specific gaps: evidence not addressed, steps not tied to a goal, "
        "missing follow-through, ignored the workspace playbook, off-voice, etc.",
    )
    feedback: str = Field(
        description="Concrete, actionable revision guidance for the strategist. "
        "Empty/'(approved)' when approved."
    )
