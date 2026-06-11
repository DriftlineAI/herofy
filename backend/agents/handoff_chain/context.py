"""
HandoffChain Context
Shared state passed between agent steps
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class HandoffContext:
    """
    Context object passed between HandoffChain steps.
    Accumulates data as each step executes.
    """

    # Input parameters
    workspace_id: str
    notion_deal_id: str
    customer_id: str | None = None

    # Run metadata
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.utcnow)
    handbook_version_id: str | None = None

    # Step outputs
    deal_data: dict[str, Any] | None = None
    playbook: dict[str, Any] | None = None
    playbook_milestones: list[dict[str, Any]] | None = None
    gap_analysis: dict[str, Any] | None = None
    handoff_brief: dict[str, Any] | None = None
    ai_plan: dict[str, Any] | None = None
    customer: dict[str, Any] | None = None
    need: dict[str, Any] | None = None

    # Error tracking
    errors: list[str] = field(default_factory=list)
    failed_step: str | None = None

    def with_deal_data(self, deal_data: dict[str, Any]) -> "HandoffContext":
        """Return new context with deal data."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=self.need,
            errors=self.errors,
        )

    def with_playbook(
        self, playbook: dict[str, Any], milestones: list[dict[str, Any]]
    ) -> "HandoffContext":
        """Return new context with playbook data."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=playbook,
            playbook_milestones=milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=self.need,
            errors=self.errors,
        )

    def with_gap_analysis(self, gap_analysis: dict[str, Any]) -> "HandoffContext":
        """Return new context with gap analysis."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=self.need,
            errors=self.errors,
        )

    def with_handoff_brief(self, brief: dict[str, Any]) -> "HandoffContext":
        """Return new context with handoff brief."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=self.need,
            errors=self.errors,
        )

    def with_ai_plan(self, plan: dict[str, Any]) -> "HandoffContext":
        """Return new context with AI plan."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=plan,
            customer=self.customer,
            need=self.need,
            errors=self.errors,
        )

    def with_customer(self, customer: dict[str, Any]) -> "HandoffContext":
        """Return new context with customer."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=str(customer["id"]),
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=customer,
            need=self.need,
            errors=self.errors,
        )

    def with_need(self, need: dict[str, Any]) -> "HandoffContext":
        """Return new context with surfaced need."""
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=need,
            errors=self.errors,
        )

    def with_error(self, step_name: str, error: str) -> "HandoffContext":
        """Return new context with error recorded."""
        new_errors = self.errors.copy()
        new_errors.append(f"{step_name}: {error}")
        return HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=self.notion_deal_id,
            customer_id=self.customer_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            deal_data=self.deal_data,
            playbook=self.playbook,
            playbook_milestones=self.playbook_milestones,
            gap_analysis=self.gap_analysis,
            handoff_brief=self.handoff_brief,
            ai_plan=self.ai_plan,
            customer=self.customer,
            need=self.need,
            errors=new_errors,
            failed_step=step_name,
        )

    @property
    def is_failed(self) -> bool:
        """Check if any step has failed."""
        return self.failed_step is not None

    @property
    def company_name(self) -> str:
        """Get company name from deal data."""
        if self.deal_data:
            return self.deal_data.get("company_name", "Unknown")
        return "Unknown"

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary for storage."""
        return {
            "workspace_id": self.workspace_id,
            "notion_deal_id": self.notion_deal_id,
            "customer_id": self.customer_id,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "handbook_version_id": self.handbook_version_id,
            "deal_data": self.deal_data,
            "playbook": self.playbook,
            "playbook_milestones": self.playbook_milestones,
            "gap_analysis": self.gap_analysis,
            "handoff_brief": self.handoff_brief,
            "ai_plan": self.ai_plan,
            "customer": self.customer,
            "need": self.need,
            "errors": self.errors,
            "failed_step": self.failed_step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffContext":
        """Deserialize context from dictionary."""
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elif started_at is None:
            started_at = datetime.utcnow()

        return cls(
            workspace_id=data["workspace_id"],
            notion_deal_id=data["notion_deal_id"],
            customer_id=data.get("customer_id"),
            run_id=data.get("run_id", str(uuid4())),
            started_at=started_at,
            handbook_version_id=data.get("handbook_version_id"),
            deal_data=data.get("deal_data"),
            playbook=data.get("playbook"),
            playbook_milestones=data.get("playbook_milestones"),
            gap_analysis=data.get("gap_analysis"),
            handoff_brief=data.get("handoff_brief"),
            ai_plan=data.get("ai_plan"),
            customer=data.get("customer"),
            need=data.get("need"),
            errors=data.get("errors", []),
            failed_step=data.get("failed_step"),
        )
