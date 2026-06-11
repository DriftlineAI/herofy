"""
Handoff Service (DataConnect Version)
Business logic for handoff brief creation and management using Firebase Data Connect
"""

import json
from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("HandoffServiceDC")


class HandoffServiceDC:
    """Service for handoff-related business logic using DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id

    async def create_brief(
        self,
        deal_data: dict[str, Any],
        gap_analysis: dict[str, Any],
        handbook_version_id: str,
        customer_id: str | None = None,
        notion_deal_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a handoff brief from deal data and gap analysis.

        Args:
            deal_data: Extracted deal information from Notion
            gap_analysis: Gap analysis results
            handbook_version_id: For audit trail
            customer_id: Optional existing customer ID
            notion_deal_id: Notion page reference

        Returns:
            Created handoff brief record
        """
        # Format reality check from gap analysis
        reality_check_risks = self._format_risks(gap_analysis)
        reality_check_confidence = gap_analysis.get("confidence", "medium")

        # Serialize arrays to JSON strings
        sales_commitments = json.dumps(deal_data.get("sales_commitments", []))
        technical_context = json.dumps(deal_data.get("technical_context", []))

        brief_result = await self.dc.execute_mutation(
            "CreateHandoffBrief",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "salesCommitments": sales_commitments,
                "technicalContext": technical_context,
                "realityCheckConfidence": reality_check_confidence,
                "realityCheckRisks": reality_check_risks,
                "status": "draft",
                "notionDealId": notion_deal_id,
                "handbookVersionId": handbook_version_id,
                "model": "gemini-2.5-flash",  # Audit trail only - not used for LLM calls
                "promptVersion": "v1.0",
            },
        )

        brief = brief_result.get("handoffBrief_insert", {})

        # Create open questions from gap analysis
        open_questions = gap_analysis.get("open_questions", [])
        for question in open_questions:
            await self.dc.execute_mutation(
                "CreateHandoffOpenQuestion",
                {
                    "briefId": brief["id"],
                    "text": question,
                    "resolved": False,
                },
            )

        logger.info(
            "handoff_brief_created",
            brief_id=str(brief["id"]),
            questions_count=len(open_questions),
        )

        return brief

    async def link_customer(self, brief_id: str, customer_id: str) -> dict[str, Any]:
        """
        Link a customer to a handoff brief.

        Args:
            brief_id: The handoff brief UUID
            customer_id: The customer UUID

        Returns:
            Updated brief record
        """
        brief_result = await self.dc.execute_mutation(
            "LinkHandoffBriefToCustomer",
            {
                "id": brief_id,
                "customerId": customer_id,
            },
        )

        brief = brief_result.get("handoffBrief_update", {})

        if brief:
            logger.info(
                "handoff_brief_linked",
                brief_id=brief_id,
                customer_id=customer_id,
            )

        return brief

    async def get_brief_with_details(self, brief_id: str) -> dict[str, Any] | None:
        """
        Get a handoff brief with open questions and plan.

        Args:
            brief_id: The handoff brief UUID

        Returns:
            Brief with nested questions and plan, or None
        """
        result = await self.dc.execute_query(
            "GetHandoff",
            {"id": brief_id},
        )

        brief = result.get("handoffBrief")

        if not brief:
            return None

        # Transform nested data to match legacy format
        open_questions = brief.pop("handoffOpenQuestions_on_brief", [])
        ai_plans = brief.pop("aiPlans_on_brief", [])

        # Get the latest plan (first in DESC order)
        plan = ai_plans[0] if ai_plans else None

        return {
            **brief,
            "open_questions": open_questions,
            "plan": plan,
        }

    def _format_risks(self, gap_analysis: dict[str, Any]) -> str:
        """Format gap analysis risks as human-readable text."""
        risks = gap_analysis.get("risks", [])
        if not risks:
            return "No significant risks identified."

        lines = ["Key risks identified:"]
        for i, risk in enumerate(risks, 1):
            lines.append(f"{i}. {risk}")

        if not gap_analysis.get("timeline_feasible", True):
            lines.append("\n⚠️ Timeline may not be feasible based on playbook norms.")

        recommendations = gap_analysis.get("recommendations", [])
        if recommendations:
            lines.append("\nRecommendations:")
            for rec in recommendations:
                lines.append(f"• {rec}")

        return "\n".join(lines)
