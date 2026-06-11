"""
Setup Service
Business logic for workspace setup completion, including batch agent triggering
"""

import asyncio
from typing import Any
from datetime import datetime

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger
from services.sidekick_service import SidekickService

logger = get_logger("SetupService")


class SetupService:
    """Service for handling workspace setup completion."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id
        self.sidekick = SidekickService(dc, workspace_id)

    async def trigger_onboarding_agents(
        self,
        max_retries: int = 3,
        initial_backoff: int = 30,
    ) -> dict[str, Any]:
        """
        Trigger handoff_auto agent for all customers needing onboarding.

        Filters customers by:
        - lifecycle='onboarding' (or 'handoff')
        - No existing AI plan

        For each customer:
        - Triggers handoff_auto agent with retry logic
        - 3 attempts with exponential backoff (30s, 60s, 120s)
        - Creates sidekick item on final failure

        Args:
            max_retries: Maximum retry attempts per customer (default: 3)
            initial_backoff: Initial backoff in seconds (default: 30)

        Returns:
            Summary dict with:
            - customers_analyzed: Total customers checked
            - agents_triggered: Successful triggers
            - agents_failed: Failed triggers
            - failed_customer_ids: List of customer IDs that failed
            - sidekick_items_created: Count of error items created
        """
        logger.info(
            "triggering_onboarding_agents",
            workspace_id=self.workspace_id,
            max_retries=max_retries,
        )

        # Get customers needing onboarding
        customers = await self._get_customers_needing_onboarding()

        logger.info(
            "customers_needing_onboarding",
            workspace_id=self.workspace_id,
            count=len(customers),
        )

        if not customers:
            return {
                "customers_analyzed": 0,
                "agents_triggered": 0,
                "agents_failed": 0,
                "failed_customer_ids": [],
                "sidekick_items_created": 0,
            }

        # Process each customer - agents run in background (non-blocking)
        results = {
            "customers_analyzed": len(customers),
            "agents_triggered": 0,
            "agents_failed": 0,
            "failed_customer_ids": [],
            "sidekick_items_created": 0,
        }

        for customer in customers:
            customer_id = customer["id"]
            customer_name = customer["name"]

            # Fire-and-forget: agents run in background
            success = await self._trigger_agent_with_retry(
                customer_id=customer_id,
                customer_name=customer_name,
                max_retries=max_retries,  # Unused - kept for API compatibility
                initial_backoff=initial_backoff,  # Unused
            )

            if success:
                results["agents_triggered"] += 1
            else:
                # This only happens if we fail to even start the background task
                results["agents_failed"] += 1
                results["failed_customer_ids"].append(customer_id)

        logger.info(
            "onboarding_agents_triggered",
            workspace_id=self.workspace_id,
            **results,
        )

        return results

    async def _get_customers_needing_onboarding(self) -> list[dict[str, Any]]:
        """
        Get customers that need onboarding plans.

        Criteria:
        - lifecycle='onboarding' OR lifecycle='handoff'
        - No existing AI plan (ai_plans_on_customer is empty)

        Returns:
            List of customer dicts with id, name, lifecycle
        """
        result = await self.dc.execute_query(
            "GetCustomersNeedingOnboarding",
            {"workspaceId": self.workspace_id},
        )

        # Filter out customers that already have plans
        customers_data = result.get("customers", [])
        customers_needing_plans = [
            c for c in customers_data
            if not c.get("aiPlans_on_customer")
        ]

        return customers_needing_plans

    async def _trigger_agent_with_retry(
        self,
        customer_id: str,
        customer_name: str,
        max_retries: int,
        initial_backoff: int,
    ) -> bool:
        """
        Trigger handoff_auto agent in the background (non-blocking).

        Args:
            customer_id: Customer UUID
            customer_name: Customer name (for logging)
            max_retries: Maximum retry attempts (unused - agents run in background)
            initial_backoff: Initial backoff in seconds (unused)

        Returns:
            True - agents are started in background, success tracked via agent status
        """
        try:
            logger.info(
                "triggering_handoff_agent_background",
                customer_id=customer_id,
                customer_name=customer_name,
            )

            # Fire and forget - run the agent in the background
            # The agent will update its own status in the database
            asyncio.create_task(
                self._run_agent_background(customer_id, customer_name)
            )

            logger.info(
                "handoff_agent_triggered_background",
                customer_id=customer_id,
                customer_name=customer_name,
            )
            return True

        except Exception as e:
            logger.error(
                "handoff_agent_trigger_failed",
                customer_id=customer_id,
                customer_name=customer_name,
                error=str(e),
            )
            return False

    async def _run_agent_background(
        self,
        customer_id: str,
        customer_name: str,
    ) -> None:
        """
        Run the agent in the background. Errors are logged but not raised.

        The agent can complete with these statuses:
        - completed: Plan was generated successfully
        - waiting_for_input: Agent paused to ask questions (success - this is expected)
        - failed: Something went wrong
        """
        try:
            from agents.handoff_auto.agent import run_handoff_auto
            result = await run_handoff_auto(
                workspace_id=self.workspace_id,
                customer_id=customer_id,
                trigger_type="setup_completion",
                triggered_by="system:setup_service",
            )

            # HandoffAutoResponse is a Pydantic model, not a dict
            # Access attributes directly
            from core.types import AgentStatus

            status = result.status
            run_id = result.run_id

            logger.info(
                "background_agent_completed",
                customer_id=customer_id,
                customer_name=customer_name,
                run_id=run_id,
                status=status.value if hasattr(status, 'value') else str(status),
            )

            # Both completed and waiting_for_input are successful outcomes
            # waiting_for_input means the agent is asking questions, which is expected
            if status == AgentStatus.FAILED:
                logger.warning(
                    "background_agent_returned_failed",
                    customer_id=customer_id,
                    customer_name=customer_name,
                    error=result.error,
                )
                # Don't create a sidekick item here - the agent already handles failures

        except Exception as e:
            logger.error(
                "background_agent_exception",
                customer_id=customer_id,
                customer_name=customer_name,
                error=str(e),
            )
            # Only create failure sidekick for unexpected exceptions
            # (not for agent returning failed status - agent handles its own errors)

    async def _create_failure_sidekick_item(
        self,
        customer_id: str,
        customer_name: str,
    ) -> None:
        """
        Create a sidekick item for failed agent trigger.

        The item allows the user to:
        - Retry the agent manually
        - Review error details
        - Provide additional context if needed

        Args:
            customer_id: Customer UUID
            customer_name: Customer name
        """
        await self.sidekick.create_asking(
            customer_id=customer_id,
            question=f"Failed to generate onboarding plan for {customer_name}",
            why=f"""The handoff agent couldn't generate an onboarding plan after 3 attempts during setup.

**What happened:**
The agent may have encountered rate limits, missing data, or other errors.

**What you can do:**
1. Check that the customer has basic information (ARR, stakeholders, goals)
2. Try generating the plan manually from the customer detail page
3. Review the customer's raw notes to ensure there's enough context

If the problem persists, check the agent logs or contact support.""",
            is_blocking=True,
        )

        logger.info(
            "created_failure_sidekick_item",
            customer_id=customer_id,
            customer_name=customer_name,
        )
