"""
Herofy Pydantic Models
Type definitions matching PostgreSQL schema
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Enums (matching PostgreSQL types)
# =============================================================================


class CustomerLifecycle(str, Enum):
    PROSPECT = "prospect"
    HANDOFF = "handoff"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    RENEWING = "renewing"
    AT_RISK = "at_risk"
    CHURNED = "churned"


class HandoffStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    NEEDS_CORRECTION = "needs_correction"


class ApprovalStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class NeedType(str, Enum):
    URGENT_SUPPORT = "urgent_support"
    GOING_DARK = "going_dark"
    STALLED_MILESTONE = "stalled_milestone"
    APPROACHING_RENEWAL = "approaching_renewal"
    OPEN_COMMITMENT_OVERDUE = "open_commitment_overdue"
    FRUSTRATED_SIGNAL = "frustrated_signal"
    CHAMPION_DEPARTED = "champion_departed"
    ONBOARDING_BEHIND = "onboarding_behind"
    RENEWAL_AT_RISK = "renewal_at_risk"
    NEW_HANDOFF = "new_handoff"
    MEETING_PREP_READY = "meeting_prep_ready"
    POSITIVE_SIGNAL = "positive_signal"
    EXPANSION_SIGNAL = "expansion_signal"
    CHECK_IN_DUE = "check_in_due"
    ESCALATION = "escalation"
    PLAN_APPROVAL_REQUIRED = "plan_approval_required"
    DRAFT_RESPONSE_READY = "draft_response_ready"
    SIDEKICK_QUESTION = "sidekick_question"  # Agent needs clarification
    UNCATEGORIZED = "uncategorized"


class OwnerSide(str, Enum):
    US = "us"
    CUSTOMER = "customer"
    JOINT = "joint"


class StakeholderStatus(str, Enum):
    ACTIVE = "active"
    DEPARTED = "departed"


# =============================================================================
# Database Models
# =============================================================================


class Customer(BaseModel):
    """Customer record from customers table."""

    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    one_liner: str | None = None
    tier: str | None = None
    arr_cents: int | None = None
    lifecycle: CustomerLifecycle = CustomerLifecycle.PROSPECT
    days_to_renewal: int | None = None
    onboarding_day_current: int | None = None
    onboarding_day_total: int | None = None
    created_at: datetime
    updated_at: datetime


class Stakeholder(BaseModel):
    """Stakeholder record from stakeholders table."""

    id: UUID
    workspace_id: UUID
    customer_id: UUID
    name: str
    email: str | None = None
    role: str | None = None
    status: StakeholderStatus = StakeholderStatus.ACTIVE
    sentiment_note: str | None = None
    created_at: datetime
    updated_at: datetime


class Playbook(BaseModel):
    """Playbook record from playbooks table."""

    id: UUID
    workspace_id: UUID
    name: str
    archetype: str | None = None
    fit_note: str | None = None
    drawn_from_count: int = 0
    created_at: datetime
    updated_at: datetime


class PlaybookMilestone(BaseModel):
    """Playbook milestone from playbook_milestones table."""

    id: UUID
    playbook_id: UUID
    title: str
    owner_side: OwnerSide = OwnerSide.JOINT
    duration_days: int | None = None
    description: str | None = None
    sort_order: int = 0
    created_at: datetime


class SalesCommitment(BaseModel):
    """Sales commitment extracted from deal."""

    item: str
    details: str | None = None


class TechnicalContext(BaseModel):
    """Technical context item from deal."""

    item: str
    details: str | None = None


class HandoffBrief(BaseModel):
    """Handoff brief from handoff_briefs table."""

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None = None
    captured_at: datetime
    day_current: int | None = None
    day_total: int | None = None
    sales_commitments: list[SalesCommitment] | None = None
    technical_context: list[TechnicalContext] | None = None
    reality_check_confidence: str | None = None
    reality_check_risks: str | None = None
    status: HandoffStatus = HandoffStatus.DRAFT
    notion_deal_id: str | None = None
    notion_deal_url: str | None = None
    handbook_version_id: UUID
    model: str | None = None
    prompt_version: str | None = None
    created_at: datetime
    updated_at: datetime


class HandoffOpenQuestion(BaseModel):
    """Open question from handoff_open_questions table."""

    id: UUID
    brief_id: UUID
    text: str
    resolved: bool = False
    created_at: datetime


class PlanMilestone(BaseModel):
    """Milestone within an AI plan."""

    title: str
    owner_side: OwnerSide = OwnerSide.JOINT
    target_days: int
    description: str | None = None


class AIPlan(BaseModel):
    """AI plan from ai_plans table."""

    id: UUID
    workspace_id: UUID
    customer_id: UUID | None = None
    brief_id: UUID | None = None
    archetype_name: str | None = None
    milestone_count: int | None = None
    duration_label: str | None = None
    rationale: str | None = None
    headline: str | None = None
    milestones: list[PlanMilestone] | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING_APPROVAL
    human_edited: bool = False
    regeneration_count: int = 0
    generated_at: datetime
    model: str
    prompt_version: str
    inputs_hash: str
    handbook_version_id: UUID
    created_at: datetime
    updated_at: datetime


class Need(BaseModel):
    """Need from needs table."""

    id: UUID
    workspace_id: UUID
    customer_id: UUID
    type: NeedType
    headline: str
    lede: str | None = None
    priority_rank: int = 100
    agent_reasoning: str
    handbook_version_id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# API Request/Response Models
# =============================================================================


class HandoffChainRequest(BaseModel):
    """Request body for handoff chain trigger."""

    workspace_id: str
    customer_id: str | None = None
    notion_deal_id: str


class HandoffChainResponse(BaseModel):
    """Response from handoff chain execution."""

    run_id: str
    status: str  # "completed" | "failed"
    customer_id: str | None = None
    brief_id: str | None = None
    plan_id: str | None = None
    need_id: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"


# =============================================================================
# Agent Context Models
# =============================================================================


class DealData(BaseModel):
    """Extracted data from Notion deal page."""

    company_name: str
    arr_cents: int
    sales_commitments: list[SalesCommitment]
    technical_context: list[TechnicalContext]
    stakeholders: list[dict[str, Any]]
    timeline: str | None = None
    notes: str | None = None


class GapAnalysis(BaseModel):
    """Gap analysis between commitments and playbook."""

    confidence: str  # "high" | "medium" | "low"
    risks: list[str]
    timeline_feasible: bool
    recommendations: list[str]
    open_questions: list[str] = []
    needs_clarification: bool = False


# =============================================================================
# Autonomous Agent Types
# =============================================================================


class AgentStatus(str, Enum):
    """Execution status for autonomous agents."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"


class ConfidenceLevel(str, Enum):
    """Confidence level for agent decisions."""
    HIGH = "high"      # 80%+ certain, proceed automatically
    MEDIUM = "medium"  # 50-80% certain, configurable pause
    LOW = "low"        # <50% certain, always pause or fallback


class AutonomyMode(str, Enum):
    """Workspace autonomy configuration."""
    FULL_AUTO = "full_auto"      # Never pause, always produce output
    SMART_AUTO = "smart_auto"    # Pause only on low confidence (default)
    SUPERVISED = "supervised"    # Always pause for human review


class QuestionType(str, Enum):
    """Types of clarifying questions."""
    MISSING_DATA = "missing_data"
    CLARIFICATION = "clarification"
    AMBIGUITY = "ambiguity"
    VALIDATION = "validation"


class StructuredQuestionType(str, Enum):
    """UI input types for clarifying questions."""
    FREEFORM = "freeform"          # Free text input
    PICK_ONE = "pick_one"          # Single select from options
    PICK_MANY = "pick_many"        # Multi-select from options
    PICK_PERSON = "pick_person"    # Select person from list
    SLIDER = "slider"              # Numeric slider
    YES_NO = "yes_no"              # Yes/No toggle
    DATE = "date"                  # Date picker


class IntegrationType(str, Enum):
    """Supported integration types."""
    NOTION = "notion"
    NOTION_MCP = "notion_mcp"  # Notion hosted MCP server (mcp.notion.com) — separate OAuth from REST
    SLACK = "slack"
    GMAIL = "gmail"
    HUBSPOT = "hubspot"
    CALENDAR = "calendar"


class IntegrationStatus(str, Enum):
    """Integration connection status."""
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    REVOKED = "revoked"


class ClarifyingQuestion(BaseModel):
    """
    A question the agent needs answered.

    The `structured_type` field determines how the UI renders the input:
    - freeform: text input (multiline if metadata.multiline=True)
    - pick_one: single select from options
    - pick_many: multi-select from options
    - pick_person: person selector
    - slider: numeric slider
    - yes_no: yes/no toggle
    - date: date picker
    """
    field: str  # Field this relates to (e.g., "arr_cents")
    question: str  # Human-readable question
    question_type: QuestionType = QuestionType.CLARIFICATION  # Semantic type (legacy)
    structured_type: StructuredQuestionType = StructuredQuestionType.FREEFORM  # UI input type
    context: str | None = None  # Additional context for the human
    required: bool = True
    placeholder: str | None = None
    # Options for pick_one/pick_many - each option should have 'value' and 'label'
    options: list[dict[str, Any]] | None = None
    # Type-specific metadata (yes_label, no_label, min, max, etc.)
    metadata: dict[str, Any] | None = None
    answer: str | None = None
    answered_at: datetime | None = None

    model_config = {
        "use_enum_values": True,  # Serialize enums as their values
    }


class ConfidenceAssessment(BaseModel):
    """Assessment of agent's confidence in proceeding."""
    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0)  # 0.0 - 1.0
    reasons: list[str]  # Why this confidence level
    questions: list[ClarifyingQuestion] | None = None  # If pausing


class AgentRun(BaseModel):
    """Agent run record from agent_runs table."""
    id: UUID
    workspace_id: UUID
    agent_name: str
    status: AgentStatus
    trigger_type: str | None = None
    triggered_by: str | None = None
    input_params: dict[str, Any] = {}
    current_step: str | None = None
    context_snapshot: dict[str, Any] | None = None
    confidence_level: ConfidenceLevel | None = None
    confidence_score: float | None = None
    confidence_reasons: list[str] | None = None
    paused_at: datetime | None = None
    pause_reason: str | None = None
    blocking_need_id: UUID | None = None
    clarifying_questions: list[ClarifyingQuestion] | None = None
    resumed_at: datetime | None = None
    resume_answers: dict[str, Any] | None = None
    customer_id: UUID | None = None
    brief_id: UUID | None = None
    plan_id: UUID | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceIntegration(BaseModel):
    """Integration configuration from workspace_integrations table."""
    id: UUID
    workspace_id: UUID
    integration_type: IntegrationType
    config: dict[str, Any] = {}
    status: IntegrationStatus = IntegrationStatus.PENDING
    last_sync_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotionConfig(BaseModel):
    """Notion-specific integration config."""
    database_id: str
    database_name: str | None = None
    field_mappings: dict[str, str] | None = None  # Notion field -> our field


class NotionDeal(BaseModel):
    """Deal data fetched from Notion (or other CRM sources)."""
    page_id: str | None = None  # Optional - may not have Notion deal linked
    company_name: str
    arr_cents: int | None = None
    closed_at: datetime | None = None
    timeline: str | None = None
    sales_commitments: list[SalesCommitment] = []
    technical_context: list[TechnicalContext] = []
    stakeholders: list[dict[str, Any]] = []
    notes: str | None = None
    raw_properties: dict[str, Any] | None = None


class WorkspaceAgentSettings(BaseModel):
    """Agent settings per workspace."""
    id: UUID
    workspace_id: UUID
    agent_name: str
    autonomy_mode: AutonomyMode = AutonomyMode.SMART_AUTO
    pause_on_medium_confidence: bool = True
    question_timeout_hours: int = 24
    fallback_on_timeout: bool = True
    notify_on_pause: bool = True
    notify_on_complete: bool = False
    notification_channel: str = "app"
    poll_enabled: bool = True
    poll_interval_minutes: int = 15
    enabled: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Autonomous Agent Request/Response
# =============================================================================


class HandoffAutoRequest(BaseModel):
    """Request body for autonomous handoff trigger."""
    workspace_id: str
    customer_id: str | None = None  # Existing customer ID (for setup wizard flow)
    notion_deal_id: str | None = None  # If None, poll for deals
    trigger_type: str = "manual"  # 'manual', 'webhook', 'poll', 'setup_wizard'
    settings_override: dict[str, Any] | None = None  # Override workspace settings


class HandoffAutoResponse(BaseModel):
    """Response from autonomous handoff execution."""
    run_id: str
    status: AgentStatus
    customer_id: str | None = None
    brief_id: str | None = None
    plan_id: str | None = None
    need_id: str | None = None  # If paused for input
    confidence: ConfidenceAssessment | None = None
    paused_for_questions: list[ClarifyingQuestion] | None = None
    error: str | None = None
    used_fallback: bool = False


class ResumeAgentRequest(BaseModel):
    """Request to resume a paused agent run."""
    answers: dict[str, Any]  # Field -> answer mapping


class AgentRunStatusResponse(BaseModel):
    """Status check response for an agent run."""
    run_id: str
    status: AgentStatus
    current_step: str | None = None
    paused_at: datetime | None = None
    questions: list[ClarifyingQuestion] | None = None
    progress_pct: int | None = None  # 0-100
    customer_id: str | None = None
    brief_id: str | None = None
    plan_id: str | None = None
