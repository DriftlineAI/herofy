"""
Plan Service (DataConnect Version)
Business logic for AI plan generation and milestone management using Firebase Data Connect
"""

import hashlib
import json
from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("PlanServiceDC")


class PlanServiceDC:
    """Service for AI plan generation and management using DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id

    async def create_plan(
        self,
        brief_id: str | None,
        customer_id: str | None,
        playbook: dict[str, Any],
        milestones: list[dict[str, Any]],
        headline: str,
        rationale: str,
        handbook_version_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an AI-generated onboarding plan.

        Args:
            brief_id: The handoff brief UUID (optional for existing customers)
            customer_id: The customer UUID (can be None)
            playbook: Playbook used as template
            milestones: Adapted milestones for this customer
            headline: Plan headline
            rationale: Why this plan was generated
            handbook_version_id: For audit trail (optional)

        Returns:
            Created AI plan record
        """
        # Calculate total duration from milestones
        total_days = max(m.get("target_days", 0) for m in milestones) if milestones else 45
        duration_label = f"{total_days} days"

        # Create inputs hash for deduplication
        inputs_hash = self._create_inputs_hash(brief_id, milestones)

        # Build variables - include all fields, with None for optional UUIDs
        variables = {
            "workspaceId": self.workspace_id,
            "archetypeName": playbook.get("archetype", "Standard"),
            "headline": headline,
            "rationale": rationale,
            "milestones": json.dumps(milestones),
            "milestoneCount": len(milestones),
            "durationLabel": duration_label,
            "model": "gemini-2.5-flash",  # Audit trail only - not used for LLM calls
            "promptVersion": "v1.0",
            "inputsHash": inputs_hash,
            # Optional UUID fields - pass None for nullable FKs
            "customerId": customer_id,
            "briefId": brief_id,
            "handbookVersionId": handbook_version_id,
        }

        result = await self.dc.execute_mutation("CreateAiPlan", variables)

        plan = result.get("aiPlan_insert", {})

        logger.info(
            "ai_plan_created",
            plan_id=str(plan.get("id")),
            brief_id=brief_id,
            milestone_count=len(milestones),
            duration_label=duration_label,
        )

        return {
            "id": plan.get("id"),
            "milestone_count": len(milestones),
            "duration_label": duration_label,
            "status": "pending_approval",
        }

    async def adapt_milestones(
        self,
        playbook_milestones: list[dict[str, Any]],
        deal_data: dict[str, Any],
        gap_analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Adapt playbook milestones based on deal specifics.

        This is a rule-based adaptation. For more sophisticated
        adaptation, the agent can call an LLM directly.

        Args:
            playbook_milestones: Template milestones from playbook
            deal_data: Deal information from Notion
            gap_analysis: Gap analysis results

        Returns:
            Adapted milestones with target_days calculated
        """
        adapted = []
        cumulative_days = 0

        # Check if timeline is tight
        timeline_tight = not gap_analysis.get("timeline_feasible", True)
        compression_factor = 0.8 if timeline_tight else 1.0

        for milestone in playbook_milestones:
            duration = milestone.get("duration_days", 7)
            if timeline_tight:
                # Compress timeline by 20%
                duration = max(3, int(duration * compression_factor))

            cumulative_days += duration

            adapted.append({
                "title": milestone["title"],
                "owner_side": milestone.get("owner_side", "joint"),
                "target_days": cumulative_days,
                "description": milestone.get("description"),
            })

        logger.info(
            "milestones_adapted",
            count=len(adapted),
            total_days=cumulative_days,
            compressed=timeline_tight,
        )

        return adapted

    async def link_customer(self, plan_id: str, customer_id: str) -> dict[str, Any]:
        """
        Link a customer to an AI plan.

        Args:
            plan_id: The AI plan UUID
            customer_id: The customer UUID

        Returns:
            Updated plan record
        """
        result = await self.dc.execute_mutation(
            "LinkAiPlanToCustomer",
            {
                "id": plan_id,
                "customerId": customer_id,
            },
        )

        plan = result.get("aiPlan_update", {})

        if plan:
            logger.info(
                "ai_plan_linked",
                plan_id=plan_id,
                customer_id=customer_id,
            )

        return plan

    async def get_pending_plans(self) -> list[dict[str, Any]]:
        """Get all plans pending approval in this workspace."""
        result = await self.dc.execute_query(
            "GetPendingPlans",
            {"workspaceId": self.workspace_id},
        )

        plans = result.get("aiPlans", [])

        # Transform nested customer data to match legacy format (customer_name field)
        for plan in plans:
            customer = plan.pop("customer", None)
            if customer:
                plan["customer_name"] = customer.get("name")
                plan["customer_id"] = customer.get("id")
            else:
                plan["customer_name"] = None
                plan["customer_id"] = None

        return plans

    def _create_inputs_hash(
        self, brief_id: str, milestones: list[dict[str, Any]]
    ) -> str:
        """Create a hash of inputs for deduplication."""
        data = {
            "brief_id": brief_id,
            "milestones": milestones,
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
