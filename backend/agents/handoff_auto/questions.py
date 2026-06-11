"""
Structured Question Types for HITL (Human-in-the-Loop)

This module provides Pydantic models and factory methods for creating
typed questions that agents can ask humans. The frontend renders these
questions with appropriate UI components.

Question Types:
- PICK_ONE: Single choice from options (radio buttons)
- PICK_MANY: Multiple choices from options (checkboxes)
- PICK_PERSON: Select a stakeholder (person cards)
- SLIDER: Numeric range selection
- FREEFORM: Open text input
- DATE: Date picker
- YES_NO: Binary choice

Example usage:
    from agents.handoff_auto.questions import Question, QuestionOption, PersonOption

    questions = [
        Question.pick_one(
            id="q_timeline_type",
            text="How firm is the Feb 17 launch date?",
            context="Sales noted a board commitment.",
            options=[
                QuestionOption(label="Firm — board commitment", value="firm", default=True),
                QuestionOption(label="Target — they'd prefer it", value="target"),
                QuestionOption(label="Aspiration — nice-to-have", value="aspiration"),
            ],
            allow_decide=True,
            decide_label="Sidekick, you decide",
        ),
        Question.pick_person(
            id="q_primary_champion",
            text="Who should I mark as the primary champion?",
            context="Two contacts have the role + recency to qualify.",
            people=[
                PersonOption(
                    stakeholder_id="uuid-here",
                    name="Alice Johnson",
                    role="CEO",
                    avatar_seed="alice",
                    signal="ok",
                    signal_label="ENGAGED",
                    last_contact="2h ago · email",
                ),
            ],
            allow_decide=True,
            allow_manual=True,
        ),
        Question.slider(
            id="q_silence_threshold",
            text="How many days of silence before I flag a Going Dark risk?",
            min_val=3,
            max_val=21,
            default_val=7,
            label_low="Aggressive · 3d",
            label_high="Patient · 21d",
            format_template="{value} day{s} of silence",
        ),
    ]
"""

from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    """Types of questions agents can ask humans."""

    PICK_ONE = "pick_one"
    PICK_MANY = "pick_many"
    PICK_PERSON = "pick_person"
    SLIDER = "slider"
    FREEFORM = "freeform"
    DATE = "date"
    YES_NO = "yes_no"


class QuestionOption(BaseModel):
    """A single option for pick_one/pick_many questions."""

    label: str
    value: str
    default: bool = False
    description: Optional[str] = None


class PersonOption(BaseModel):
    """A person option for pick_person questions."""

    stakeholder_id: Optional[str] = None
    name: str
    role: str
    avatar_seed: str  # For generating consistent avatars
    signal: str = "neutral"  # "ok", "warn", "neutral", "risk"
    signal_label: str = "NEUTRAL"
    last_contact: Optional[str] = None  # e.g., "2h ago · email"
    email: Optional[str] = None


class SliderMetadata(BaseModel):
    """Metadata for slider questions."""

    min: int
    max: int
    default: int
    label_low: Optional[str] = None
    label_high: Optional[str] = None
    format_template: Optional[str] = None  # e.g., "{value} day{s} of silence"
    step: int = 1


class Question(BaseModel):
    """
    A structured question the agent asks a human.

    The question_type determines how the frontend renders this question
    and what fields in metadata are relevant.
    """

    id: str = Field(default_factory=lambda: f"q_{uuid4().hex[:8]}")
    text: str  # The main question text
    context: Optional[str] = None  # Additional context/reasoning
    question_type: QuestionType = QuestionType.FREEFORM
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Fields for backwards compatibility with ClarifyingQuestion
    field: Optional[str] = None  # What data this relates to

    # Common options across types
    required: bool = True
    placeholder: Optional[str] = None

    class Config:
        use_enum_values = True

    # ==========================================================================
    # Factory Methods
    # ==========================================================================

    @classmethod
    def pick_one(
        cls,
        text: str,
        options: list[QuestionOption],
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        allow_decide: bool = False,
        allow_other: bool = False,
        decide_label: str = "Sidekick, you decide",
        required: bool = True,
    ) -> "Question":
        """Create a single-choice question with radio buttons."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.PICK_ONE,
            required=required,
            metadata={
                "options": [opt.model_dump() for opt in options],
                "allow_decide": allow_decide,
                "allow_other": allow_other,
                "decide_label": decide_label,
            },
        )

    @classmethod
    def pick_many(
        cls,
        text: str,
        options: list[QuestionOption],
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        min_selections: int = 1,
        max_selections: Optional[int] = None,
        allow_decide: bool = False,
        allow_other: bool = False,
        required: bool = True,
    ) -> "Question":
        """Create a multi-choice question with checkboxes."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.PICK_MANY,
            required=required,
            metadata={
                "options": [opt.model_dump() for opt in options],
                "min_selections": min_selections,
                "max_selections": max_selections,
                "allow_decide": allow_decide,
                "allow_other": allow_other,
            },
        )

    @classmethod
    def pick_person(
        cls,
        text: str,
        people: list[PersonOption],
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        allow_decide: bool = False,
        allow_manual: bool = True,  # Allow typing a new person
        multi_select: bool = False,
        required: bool = True,
    ) -> "Question":
        """Create a person picker question with stakeholder cards."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.PICK_PERSON,
            required=required,
            metadata={
                "people": [p.model_dump() for p in people],
                "allow_decide": allow_decide,
                "allow_manual": allow_manual,
                "multi_select": multi_select,
            },
        )

    @classmethod
    def slider(
        cls,
        text: str,
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        min_val: int = 0,
        max_val: int = 100,
        default_val: int = 50,
        step: int = 1,
        label_low: Optional[str] = None,
        label_high: Optional[str] = None,
        format_template: Optional[str] = None,
        required: bool = True,
    ) -> "Question":
        """Create a numeric slider question."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.SLIDER,
            required=required,
            metadata={
                "min": min_val,
                "max": max_val,
                "default": default_val,
                "step": step,
                "label_low": label_low,
                "label_high": label_high,
                "format_template": format_template,
            },
        )

    @classmethod
    def freeform(
        cls,
        text: str,
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        placeholder: Optional[str] = None,
        multiline: bool = False,
        max_length: Optional[int] = None,
        required: bool = True,
    ) -> "Question":
        """Create an open text input question."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.FREEFORM,
            placeholder=placeholder,
            required=required,
            metadata={
                "multiline": multiline,
                "max_length": max_length,
            },
        )

    @classmethod
    def date(
        cls,
        text: str,
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        min_date: Optional[str] = None,  # ISO format
        max_date: Optional[str] = None,
        default_date: Optional[str] = None,
        required: bool = True,
    ) -> "Question":
        """Create a date picker question."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.DATE,
            required=required,
            metadata={
                "min_date": min_date,
                "max_date": max_date,
                "default_date": default_date,
            },
        )

    @classmethod
    def yes_no(
        cls,
        text: str,
        *,
        id: Optional[str] = None,
        context: Optional[str] = None,
        field: Optional[str] = None,
        yes_label: str = "Yes",
        no_label: str = "No",
        default: Optional[bool] = None,
        allow_decide: bool = False,
        required: bool = True,
    ) -> "Question":
        """Create a binary yes/no question."""
        return cls(
            id=id or f"q_{uuid4().hex[:8]}",
            text=text,
            context=context,
            field=field,
            question_type=QuestionType.YES_NO,
            required=required,
            metadata={
                "yes_label": yes_label,
                "no_label": no_label,
                "default": default,
                "allow_decide": allow_decide,
            },
        )

    # ==========================================================================
    # Conversion
    # ==========================================================================

    def to_clarifying_question(self) -> dict[str, Any]:
        """
        Convert to the legacy ClarifyingQuestion format for backwards compatibility.

        This allows gradual migration - old code can still use the old format
        while new code uses the structured Question format.
        """
        from core.types import QuestionType as LegacyQuestionType

        # Map new types to legacy types
        type_mapping = {
            QuestionType.PICK_ONE: LegacyQuestionType.VALIDATION,
            QuestionType.PICK_MANY: LegacyQuestionType.VALIDATION,
            QuestionType.PICK_PERSON: LegacyQuestionType.CLARIFICATION,
            QuestionType.SLIDER: LegacyQuestionType.CLARIFICATION,
            QuestionType.FREEFORM: LegacyQuestionType.MISSING_DATA,
            QuestionType.DATE: LegacyQuestionType.MISSING_DATA,
            QuestionType.YES_NO: LegacyQuestionType.VALIDATION,
        }

        return {
            "id": self.id,
            "field": self.field or self.id,
            "question": self.text,
            "question_type": self.question_type,  # Include new type
            "context": self.context,
            "metadata": self.metadata,
            # Legacy fields
            "legacy_question_type": type_mapping.get(
                QuestionType(self.question_type), LegacyQuestionType.CLARIFICATION
            ).value,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "context": self.context,
            "question_type": self.question_type,
            "metadata": self.metadata,
            "field": self.field,
            "required": self.required,
            "placeholder": self.placeholder,
        }


# =============================================================================
# Question Builder for Agents
# =============================================================================


class QuestionBuilder:
    """
    Helper class for agents to build questions with context.

    Example:
        builder = QuestionBuilder(customer_name="Acme Corp")

        questions = [
            builder.timeline_firmness(),
            builder.champion_picker(stakeholders),
            builder.silence_threshold(),
        ]
    """

    def __init__(
        self,
        customer_name: str,
        workspace_id: Optional[str] = None,
    ):
        self.customer_name = customer_name
        self.workspace_id = workspace_id

    def timeline_firmness(
        self,
        deadline: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Question:
        """Ask how firm a timeline/deadline is."""
        text = f"How firm is the {deadline or 'launch date'} for {self.customer_name}?"
        context = f"Sales noted: {source}" if source else None

        return Question.pick_one(
            id="q_timeline_firmness",
            text=text,
            context=context,
            field="timeline_firmness",
            options=[
                QuestionOption(
                    label="Firm — board commitment",
                    value="firm",
                    description="Missing this date has real consequences",
                ),
                QuestionOption(
                    label="Target — they'd prefer it",
                    value="target",
                    default=True,
                    description="Important but some flexibility",
                ),
                QuestionOption(
                    label="Aspiration — nice-to-have",
                    value="aspiration",
                    description="Would be great but not critical",
                ),
            ],
            allow_decide=True,
        )

    def champion_picker(
        self,
        stakeholders: list[dict[str, Any]],
    ) -> Question:
        """Ask who the primary champion is."""
        people = [
            PersonOption(
                stakeholder_id=s.get("id"),
                name=s.get("name", "Unknown"),
                role=s.get("role", "Contact"),
                avatar_seed=s.get("name", "unknown").lower().replace(" ", ""),
                signal=s.get("signal_state", "neutral"),
                signal_label=s.get("signal_label", "NEUTRAL"),
                last_contact=s.get("last_contact"),
                email=s.get("email"),
            )
            for s in stakeholders
        ]

        return Question.pick_person(
            id="q_primary_champion",
            text=f"Who should I mark as the primary champion for {self.customer_name}?",
            context=f"{len(stakeholders)} contacts found with engagement signals.",
            field="primary_champion",
            people=people,
            allow_decide=True,
            allow_manual=True,
        )

    def silence_threshold(
        self,
        current_value: int = 7,
    ) -> Question:
        """Ask how many days of silence before flagging risk."""
        return Question.slider(
            id="q_silence_threshold",
            text="How many days of silence before I flag a Going Dark risk?",
            context=f"Current default: {current_value} days",
            field="silence_threshold_days",
            min_val=3,
            max_val=21,
            default_val=current_value,
            label_low="Aggressive · 3d",
            label_high="Patient · 21d",
            format_template="{value} days of silence",
        )

    def milestone_priority(
        self,
        milestones: list[str],
    ) -> Question:
        """Ask which milestones are most critical."""
        options = [
            QuestionOption(label=m, value=m.lower().replace(" ", "_"))
            for m in milestones[:6]  # Limit to 6 for UI
        ]

        return Question.pick_many(
            id="q_critical_milestones",
            text=f"Which milestones are most critical for {self.customer_name}?",
            context="Select the must-have milestones that define success.",
            field="critical_milestones",
            options=options,
            min_selections=1,
            max_selections=3,
        )

    def custom_success_criteria(self) -> Question:
        """Ask for any custom success criteria."""
        return Question.freeform(
            id="q_success_criteria",
            text=f"Any specific success criteria for {self.customer_name}?",
            context="E.g., 'Must integrate with Salesforce by Day 15'",
            field="custom_success_criteria",
            placeholder="Enter success criteria or leave blank...",
            multiline=True,
            required=False,
        )

    def target_go_live_date(
        self,
        suggested_date: Optional[str] = None,
    ) -> Question:
        """Ask for the target go-live date."""
        return Question.date(
            id="q_go_live_date",
            text=f"When should {self.customer_name} go live?",
            context=f"Suggested: {suggested_date}" if suggested_date else None,
            field="target_go_live_date",
            default_date=suggested_date,
        )

    def needs_technical_resources(self) -> Question:
        """Ask if customer has technical resources for integration."""
        return Question.yes_no(
            id="q_has_technical_resources",
            text=f"Does {self.customer_name} have technical resources for integration?",
            context="This affects which milestones we recommend.",
            field="has_technical_resources",
            yes_label="Yes, they have developers",
            no_label="No, they need our help",
            allow_decide=True,
        )
