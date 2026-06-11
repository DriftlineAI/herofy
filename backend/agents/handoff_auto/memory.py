"""
Agent Memory System
Long-term memory for the autonomous agent

Uses DataConnect queries for data access. Designed to be swappable with vector memory later.
The interface stays the same - just swap the implementation.
"""

from datetime import datetime
from typing import Any

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger

logger = get_logger("AgentMemory")


class AgentMemory:
    """
    Long-term memory for the autonomous agent.

    Remembers:
    - Past plans and their outcomes (approved, edited, rejected)
    - User edits to plans (what did they change?)
    - HITL answers (what clarifications were needed?)
    - Success patterns (what plans get approved fastest?)

    Uses DataConnect for queries. TODO: Add vector search when ready.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()

    async def recall_past_plans(
        self,
        customer_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Recall past plans created for this workspace.

        Args:
            customer_id: Optional - filter to specific customer
            limit: Max plans to return

        Returns:
            List of past plans with outcomes
        """
        try:
            variables = {
                "workspaceId": self.workspace_id,
                "limit": limit,
            }
            if customer_id:
                variables["customerId"] = customer_id

            result = await self.dc.execute_query("GetPastPlans", variables)
            plans = result.get("aiPlans", [])

            return [
                {
                    "id": str(p.get("id")),
                    "headline": p.get("headline"),
                    "status": p.get("status"),
                    "milestone_count": p.get("milestoneCount"),
                    "duration_label": p.get("durationLabel"),
                    "archetype": p.get("archetypeName"),
                    "was_edited": p.get("humanEdited", False),
                    "customer_name": p.get("customer", {}).get("name") if p.get("customer") else None,
                    "customer_tier": p.get("customer", {}).get("tier") if p.get("customer") else None,
                    "arr_cents": p.get("customer", {}).get("arrCents") if p.get("customer") else None,
                    "created_at": p.get("createdAt"),
                    "approved_at": p.get("approvedAt"),
                    "time_to_approval_hours": self._calc_approval_time(p),
                }
                for p in plans
            ]
        except Exception as e:
            logger.warning("recall_past_plans_failed", error=str(e))
            return []

    async def recall_similar_customers(
        self,
        tier: str | None = None,
        arr_cents: int | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Find similar customers based on tier/ARR.

        Used to learn from past onboarding successes.
        """
        try:
            # Build ARR range (within 50%)
            arr_low = 0
            arr_high = 999999999
            if arr_cents:
                arr_low = int(arr_cents * 0.5)
                arr_high = int(arr_cents * 1.5)

            variables = {
                "workspaceId": self.workspace_id,
                "arrLow": arr_low,
                "arrHigh": arr_high,
                "limit": limit,
            }
            # Note: tier filtering removed from query for simplicity
            # ARR range is the primary similarity metric

            result = await self.dc.execute_query("GetSimilarCustomers", variables)
            customers = result.get("customers", [])

            return [
                {
                    "id": str(c.get("id")),
                    "name": c.get("name"),
                    "tier": c.get("tier"),
                    "arr_cents": c.get("arrCents"),
                    "lifecycle": c.get("lifecycle"),
                }
                for c in customers
            ]
        except Exception as e:
            logger.warning("recall_similar_customers_failed", error=str(e))
            return []

    async def recall_success_patterns(self) -> dict[str, Any]:
        """
        Analyze what plans get approved fastest and with fewest edits.

        Returns patterns like:
        - Average time to approval by archetype
        - Most successful playbook archetypes
        - Common edit patterns (what do users change?)
        """
        try:
            # Get all past plans to analyze
            result = await self.dc.execute_query("GetPastPlans", {
                "workspaceId": self.workspace_id,
                "limit": 100,  # Get more for analysis
            })
            plans = result.get("aiPlans", [])

            if not plans:
                return {"archetype_performance": [], "tier_patterns": [], "insights": []}

            # Analyze by archetype
            archetype_stats = {}
            tier_stats = {}

            for p in plans:
                archetype = p.get("archetypeName", "Unknown")
                if archetype not in archetype_stats:
                    archetype_stats[archetype] = {
                        "total": 0, "approved": 0, "edited": 0, "approval_hours": []
                    }
                archetype_stats[archetype]["total"] += 1
                if p.get("status") == "approved":
                    archetype_stats[archetype]["approved"] += 1
                if p.get("humanEdited"):
                    archetype_stats[archetype]["edited"] += 1
                approval_time = self._calc_approval_time(p)
                if approval_time:
                    archetype_stats[archetype]["approval_hours"].append(approval_time)

                # Tier stats
                customer = p.get("customer") or {}
                tier = customer.get("tier", "Unknown")
                if tier not in tier_stats:
                    tier_stats[tier] = {
                        "total": 0, "approved": 0, "milestones": []
                    }
                tier_stats[tier]["total"] += 1
                if p.get("status") == "approved":
                    tier_stats[tier]["approved"] += 1
                if p.get("milestoneCount"):
                    tier_stats[tier]["milestones"].append(p.get("milestoneCount"))

            return {
                "archetype_performance": [
                    {
                        "archetype": arch,
                        "total_plans": stats["total"],
                        "approval_rate": (stats["approved"] / stats["total"]) * 100 if stats["total"] > 0 else 0,
                        "edit_rate": (stats["edited"] / stats["total"]) * 100 if stats["total"] > 0 else 0,
                        "avg_approval_hours": round(sum(stats["approval_hours"]) / len(stats["approval_hours"]), 1) if stats["approval_hours"] else None,
                    }
                    for arch, stats in archetype_stats.items()
                ],
                "tier_patterns": [
                    {
                        "tier": tier,
                        "total_plans": stats["total"],
                        "avg_milestones": round(sum(stats["milestones"]) / len(stats["milestones"]), 1) if stats["milestones"] else None,
                        "approval_rate": (stats["approved"] / stats["total"]) * 100 if stats["total"] > 0 else 0,
                    }
                    for tier, stats in tier_stats.items()
                ],
                "insights": self._generate_insights(archetype_stats, tier_stats),
            }
        except Exception as e:
            logger.warning("recall_success_patterns_failed", error=str(e))
            return {"archetype_performance": [], "tier_patterns": [], "insights": []}

    async def recall_hitl_patterns(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Recall patterns from HITL interactions.

        What questions needed clarification? What answers were given?
        """
        try:
            result = await self.dc.execute_query("GetHitlPatterns", {
                "workspaceId": self.workspace_id,
                "limit": limit,
            })
            runs = result.get("agentRuns", [])

            return [
                {
                    "run_id": str(r.get("id")),
                    "agent": r.get("agentName"),
                    "pause_reason": r.get("pauseReason"),
                    "questions": r.get("clarifyingQuestions"),
                    "answers": r.get("resumeAnswers"),
                    "created_at": r.get("createdAt"),
                }
                for r in runs
            ]
        except Exception as e:
            logger.warning("recall_hitl_patterns_failed", error=str(e))
            return []

    async def store_outcome(
        self,
        plan_id: str,
        outcome: str,
        edits_made: list[str] | None = None,
        feedback: str | None = None,
    ) -> None:
        """
        Store the outcome of a plan for future learning.

        This updates the plan record and optionally stores feedback.

        TODO: When vector memory is added, also embed the outcome
        for semantic search.
        """
        try:
            # For now, this is handled by the existing approval flow
            # But we log it for future vector embedding
            logger.info(
                "outcome_recorded",
                plan_id=plan_id,
                outcome=outcome,
                edits_made=edits_made,
                feedback=feedback,
            )

            # TODO: Add to vector store when ready
            # await self.vector_store.add({
            #     "type": "plan_outcome",
            #     "plan_id": plan_id,
            #     "outcome": outcome,
            #     "edits": edits_made,
            #     "feedback": feedback,
            # })
        except Exception as e:
            logger.error("store_outcome_failed", error=str(e))

    def _calc_approval_time(self, plan: dict) -> float | None:
        """Calculate hours between creation and approval."""
        approved_at = plan.get("approvedAt")
        created_at = plan.get("createdAt")
        if approved_at and created_at:
            try:
                if isinstance(approved_at, str):
                    approved_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                delta = approved_at - created_at
                return round(delta.total_seconds() / 3600, 1)
            except Exception:
                pass
        return None

    def _generate_insights(
        self,
        archetype_stats: dict,
        tier_stats: dict,
    ) -> list[str]:
        """Generate human-readable insights from the data."""
        insights = []

        if archetype_stats:
            # Best performing archetype
            best = max(
                archetype_stats.items(),
                key=lambda x: x[1].get("approved", 0),
                default=None,
            )
            if best and best[1].get("approved", 0) > 0:
                insights.append(
                    f"{best[0]} archetype has highest approval count ({best[1]['approved']} plans)"
                )

            # Fastest approval
            fastest = None
            fastest_time = float("inf")
            for arch, stats in archetype_stats.items():
                if stats.get("approval_hours"):
                    avg_time = sum(stats["approval_hours"]) / len(stats["approval_hours"])
                    if avg_time < fastest_time:
                        fastest_time = avg_time
                        fastest = arch
            if fastest:
                insights.append(
                    f"{fastest} plans approved fastest (avg {fastest_time:.1f}h)"
                )

        if tier_stats:
            # Enterprise vs SMB
            enterprise = tier_stats.get("Enterprise") or tier_stats.get("enterprise")
            if enterprise and enterprise.get("milestones"):
                avg = sum(enterprise["milestones"]) / len(enterprise["milestones"])
                insights.append(
                    f"Enterprise customers average {avg:.1f} milestones"
                )

        return insights
