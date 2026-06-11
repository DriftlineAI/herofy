"""
Sidekick Service
Central coordinator for Sidekick items - the AI assistant's visual feedback system.

Sidekick items appear in the UI to show what the AI is thinking, asking, or doing.
They link to AgentRun via agent_run_id for the HITL resume flow.

## Item Types

- `asking`: Questions that may block agent progress (HITL)
- `tip`: Factual suggestions/observations
- `observed`: Quieter factual notes (dimmed in UI)
- `working`: Agent is actively processing (shows pulse + progress)
- `resolved`: Completed items (checkmark, dimmed in UI)

## Architecture

```
SignalWatcher Pipeline              Handoff Auto Agent
        |                                   |
        v                                   v
 ClassifySignalsStep              LLM assesses confidence
        |                                   |
        v                                   v
 [TIP: "Frustrated tone"]         [ASKING: "What's the ARR?"]
        |                                   |
        +----> SidekickService <------------+
                    |
                    v
        DataConnect Mutation (CreateSidekickItem)
                    |
                    v
              sidekick_items table
```
"""

from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("SidekickService")


class SidekickService:
    """Service for managing Sidekick items via DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id

    async def create_tip(
        self,
        customer_id: str,
        text: str,
        need_id: str | None = None,
        timestamp_label: str | None = None,
    ) -> dict[str, Any]:
        """
        Emit a tip (passive observation) to the UI.

        Tips are factual suggestions that don't require user action.
        Example: "Detected frustrated tone in last email from Bob Smith"

        Args:
            customer_id: The customer this tip relates to
            text: The tip message to display
            need_id: Optional linked Need for context
            timestamp_label: Optional display label for timing

        Returns:
            Created sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "tip",
                "text": text,
                "needId": need_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_tip_created",
            item_id=item.get("id"),
            customer_id=customer_id,
            text=text[:50] + "..." if len(text) > 50 else text,
        )

        return item

    async def create_observed(
        self,
        customer_id: str,
        text: str,
        need_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Emit an observed item (quieter factual note) to the UI.

        Observed items are dimmed in the UI - less prominent than tips.
        Example: "Last activity was 14 days ago"

        Args:
            customer_id: The customer this observation relates to
            text: The observation message
            need_id: Optional linked Need

        Returns:
            Created sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "observed",
                "text": text,
                "needId": need_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_observed_created",
            item_id=item.get("id"),
            customer_id=customer_id,
        )

        return item

    async def create_asking(
        self,
        customer_id: str,
        question: str,
        why: str,
        is_blocking: bool = True,
        agent_run_id: str | None = None,
        need_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a HITL question that may block agent progress.

        Asking items are prominent in the UI and require user response.
        When linked to an AgentRun, resolving the question can trigger
        the agent to resume.

        Example: "Who should be the primary champion at Acme?"

        Args:
            customer_id: The customer this question relates to
            question: The question to ask the user
            why: Context for why this question matters
            is_blocking: Whether this blocks agent progress
            agent_run_id: Optional linked AgentRun for resume flow
            need_id: Optional linked Need

        Returns:
            Created sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "asking",
                "question": question,
                "why": why,
                "isBlocking": is_blocking,
                "agentRunId": agent_run_id,
                "needId": need_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_asking_created",
            item_id=item.get("id"),
            customer_id=customer_id,
            is_blocking=is_blocking,
            agent_run_id=agent_run_id,
            question=question[:50] + "..." if len(question) > 50 else question,
        )

        return item

    async def create_asking_batch(
        self,
        customer_id: str,
        agent_run_id: str,
        question_count: int,
        reason: str,
        need_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a single 'asking' item summarizing multiple HITL questions.

        Used when an agent pauses with multiple questions. The actual questions
        live in AgentRun.clarifyingQuestions - this item is for visibility in
        the nav badge, RightRail, and Today queue.

        Args:
            customer_id: The customer UUID
            agent_run_id: The paused AgentRun UUID
            question_count: Number of questions in the batch
            reason: Why the agent paused (e.g., "Need more context")
            need_id: Optional linked Need

        Returns:
            Created sidekick_item record
        """
        # Build a summary question
        if question_count == 1:
            question = "Sidekick has a question for you"
        else:
            question = f"Sidekick has {question_count} questions for you"

        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "asking",
                "question": question,
                "why": reason,
                "isBlocking": True,
                "agentRunId": agent_run_id,
                "needId": need_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_asking_batch_created",
            item_id=item.get("id"),
            customer_id=customer_id,
            agent_run_id=agent_run_id,
            question_count=question_count,
        )

        return item

    async def create_non_blocking_questions(
        self,
        customer_id: str,
        agent_run_id: str,
        question_count: int,
        routing: str,
    ) -> dict[str, Any]:
        """
        Create a visibility item for non-blocking questions (side-asks or kickoff).

        Unlike create_asking_batch, these questions do NOT block agent progress.
        The agent continues building the plan while these questions are recorded
        for later follow-up by sales or during kickoff.

        Args:
            customer_id: The customer UUID
            agent_run_id: The AgentRun UUID
            question_count: Number of questions recorded
            routing: "sales" or "kickoff" - where questions should be routed

        Returns:
            Created sidekick_item record
        """
        # Build appropriate question text based on routing
        if routing == "sales":
            if question_count == 1:
                question = "Sidekick has a question for Sales"
            else:
                question = f"Sidekick has {question_count} questions for Sales"
            why = "These questions can help refine the plan but aren't blocking"
        else:  # kickoff
            if question_count == 1:
                question = "Sidekick has a kickoff agenda item"
            else:
                question = f"Sidekick has {question_count} kickoff agenda items"
            why = "These should be discussed during the kickoff call"

        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "asking",
                "question": question,
                "why": why,
                "isBlocking": False,  # Key difference - doesn't block agent
                "agentRunId": agent_run_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_non_blocking_questions_created",
            item_id=item.get("id"),
            customer_id=customer_id,
            agent_run_id=agent_run_id,
            question_count=question_count,
            routing=routing,
        )

        return item

    async def create_working(
        self,
        customer_id: str,
        task: str,
        step: str,
        step_num: int,
        total_steps: int,
        agent_run_id: str | None = None,
        need_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Show that the agent is actively working on something.

        Working items display a pulse animation and progress indicator.
        They should be deleted when the work completes.

        Example: "Processing new customer handoff" (step 1 of 5)

        Args:
            customer_id: The customer being worked on
            task: Overall task description
            step: Current step description
            step_num: Current step number (1-indexed)
            total_steps: Total number of steps
            agent_run_id: Optional linked AgentRun
            need_id: Optional linked Need

        Returns:
            Created sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "CreateSidekickItem",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "type": "working",
                "task": task,
                "step": step,
                "stepNum": step_num,
                "totalSteps": total_steps,
                "agentRunId": agent_run_id,
                "needId": need_id,
            },
        )

        item = result.get("sidekickItem_insert", {})
        logger.info(
            "sidekick_working_created",
            item_id=item.get("id"),
            customer_id=customer_id,
            task=task,
            step=f"{step_num}/{total_steps}",
        )

        return item

    async def update_working_progress(
        self,
        item_id: str,
        step: str,
        step_num: int,
    ) -> dict[str, Any]:
        """
        Update progress on a working item.

        Called between steps to show progress to the user.

        Args:
            item_id: The sidekick_item UUID
            step: Updated step description
            step_num: Updated step number

        Returns:
            Updated sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "UpdateSidekickItemProgress",
            {
                "id": item_id,
                "step": step,
                "stepNum": step_num,
            },
        )

        logger.debug(
            "sidekick_working_progress",
            item_id=item_id,
            step=step,
            step_num=step_num,
        )

        return result.get("sidekickItem_update", {})

    async def resolve_item(
        self,
        item_id: str,
        resolution: str,
        resolved_by_user_id: str,
    ) -> dict[str, Any]:
        """
        Mark a sidekick item (usually an asking) as resolved with an answer.

        This is called when a user answers a HITL question. If the item
        is linked to an AgentRun, the agent may be triggered to resume.

        Args:
            item_id: The sidekick item UUID
            resolution: The answer/resolution text
            resolved_by_user_id: The user who resolved it

        Returns:
            Updated sidekick_item record
        """
        result = await self.dc.execute_mutation(
            "ResolveSidekickItem",
            {
                "id": item_id,
                "resolution": resolution,
                "resolvedByUserId": resolved_by_user_id,
            },
        )

        item = result.get("sidekickItem_update", {})
        logger.info(
            "sidekick_item_resolved",
            item_id=item_id,
            resolved_by=resolved_by_user_id,
        )

        return item

    async def auto_resolve_for_agent_run(
        self,
        agent_run_id: str,
        resolved_by_user_id: str,
    ) -> list[dict[str, Any]]:
        """
        Auto-resolve all asking items linked to an AgentRun.

        Called after user submits answers via the AgentRun resume flow.
        This keeps SidekickItems in sync with AgentRun status.

        Args:
            agent_run_id: The AgentRun UUID
            resolved_by_user_id: The user who submitted answers

        Returns:
            List of resolved sidekick items
        """
        # Find all sidekick items linked to this agent run
        result = await self.dc.execute_query(
            "GetSidekickItemsByAgentRun",
            {"agentRunId": agent_run_id},
        )

        items = result.get("sidekickItems", [])
        resolved_items = []

        for item in items:
            # Only resolve unresolved asking items
            if item.get("type") == "asking" and not item.get("resolvedAt"):
                try:
                    resolved = await self.dc.execute_mutation(
                        "BatchResolveSidekickItem",
                        {
                            "id": item["id"],
                            "resolution": "Answered via Sidekick question flow",
                            "resolvedByUserId": resolved_by_user_id,
                        },
                    )
                    resolved_items.append(resolved.get("sidekickItem_update", {}))
                except Exception as e:
                    # Log but don't fail - these are visibility items
                    logger.warning(
                        "sidekick_auto_resolve_failed",
                        item_id=item["id"],
                        error=str(e),
                    )

        if resolved_items:
            logger.info(
                "sidekick_items_auto_resolved",
                agent_run_id=agent_run_id,
                resolved_count=len(resolved_items),
                resolved_by=resolved_by_user_id,
            )

        return resolved_items

    async def get_items_for_agent_run(
        self,
        agent_run_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all sidekick items linked to an agent run.

        Args:
            agent_run_id: The AgentRun UUID

        Returns:
            List of sidekick items
        """
        result = await self.dc.execute_query(
            "GetSidekickItemsByAgentRun",
            {"agentRunId": agent_run_id},
        )
        return result.get("sidekickItems", [])

    async def delete_item(self, item_id: str) -> bool:
        """
        Delete a sidekick item.

        Typically used to remove 'working' items when the work completes.

        Args:
            item_id: The sidekick item UUID

        Returns:
            True if deleted successfully
        """
        await self.dc.execute_mutation(
            "DeleteSidekickItem",
            {"id": item_id},
        )

        logger.info("sidekick_item_deleted", item_id=item_id)
        return True

    async def get_item(self, item_id: str) -> dict[str, Any] | None:
        """
        Get a single sidekick item by ID.

        Args:
            item_id: The sidekick item UUID

        Returns:
            The sidekick item or None if not found
        """
        result = await self.dc.execute_query(
            "GetSidekickItem",
            {"id": item_id},
        )
        return result.get("sidekickItem")

    async def get_items_for_customer(
        self,
        customer_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all sidekick items for a customer.

        Args:
            customer_id: The customer UUID

        Returns:
            List of sidekick items
        """
        result = await self.dc.execute_query(
            "GetSidekickItems",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
            },
        )
        return result.get("sidekickItems", [])

    async def get_unanswered_count(self, customer_id: str | None = None) -> int:
        """
        Get count of unanswered asking items.

        Used for the nav badge to show pending HITL questions.

        Args:
            customer_id: Optional filter by customer

        Returns:
            Count of unresolved asking items
        """
        if customer_id:
            # Filter for specific customer
            items = await self.get_items_for_customer(customer_id)
            unanswered = [
                item for item in items
                if item.get("type") == "asking" and not item.get("resolvedAt")
            ]
            return len(unanswered)
        else:
            # Use workspace-wide query
            result = await self.dc.execute_query(
                "GetSidekickUnansweredCount",
                {"workspaceId": self.workspace_id},
            )
            return len(result.get("sidekickItems", []))

    async def get_unanswered_items(
        self,
        customer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all unanswered asking items.

        Args:
            customer_id: Optional filter by customer

        Returns:
            List of unresolved asking items
        """
        if customer_id:
            items = await self.get_items_for_customer(customer_id)
            return [
                item for item in items
                if item.get("type") == "asking" and not item.get("resolvedAt")
            ]
        else:
            # Use workspace-wide query (returns items with minimal fields)
            result = await self.dc.execute_query(
                "GetSidekickUnansweredCount",
                {"workspaceId": self.workspace_id},
            )
            return result.get("sidekickItems", [])
