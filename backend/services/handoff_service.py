"""
Handoff Service
Business logic for handoff brief creation and management
"""

from typing import Any

from db.client import DatabaseClient
from core.logging import get_logger

logger = get_logger("HandoffService")


class HandoffService:
    """Service for handoff-related business logic."""

    def __init__(self, db: DatabaseClient, workspace_id: str):
        self.db = db
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

        brief = await self.db.insert(
            "handoff_briefs",
            {
                "workspace_id": self.workspace_id,
                "customer_id": customer_id,
                "sales_commitments": deal_data.get("sales_commitments", []),
                "technical_context": deal_data.get("technical_context", []),
                "reality_check_confidence": reality_check_confidence,
                "reality_check_risks": reality_check_risks,
                "status": "draft",
                "notion_deal_id": notion_deal_id,
                "handbook_version_id": handbook_version_id,
                "model": "gemini-2.5-flash",  # Audit trail only - not used for LLM calls
                "prompt_version": "v1.0",
            },
        )

        # Create open questions from gap analysis
        open_questions = gap_analysis.get("open_questions", [])
        for question in open_questions:
            await self.db.insert(
                "handoff_open_questions",
                {
                    "brief_id": brief["id"],
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
        brief = await self.db.update(
            "handoff_briefs",
            brief_id,
            {"customer_id": customer_id},
        )

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
        brief = await self.db.query_one(
            """
            SELECT * FROM handoff_briefs
            WHERE id = $1 AND workspace_id = $2
            """,
            [brief_id, self.workspace_id],
        )

        if not brief:
            return None

        # Get open questions
        questions = await self.db.query_all(
            """
            SELECT * FROM handoff_open_questions
            WHERE brief_id = $1
            ORDER BY created_at
            """,
            [brief_id],
        )

        # Get associated plan
        plan = await self.db.query_one(
            """
            SELECT * FROM ai_plans
            WHERE brief_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [brief_id],
        )

        return {
            **brief,
            "open_questions": questions,
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
