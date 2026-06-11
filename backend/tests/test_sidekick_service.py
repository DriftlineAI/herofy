"""
SidekickService Unit Tests
Tests for Sidekick item management via DataConnect
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSidekickServiceCreateTip:
    """Tests for creating tip items."""

    @pytest.mark.asyncio
    async def test_create_tip_calls_correct_mutation(self):
        """Test that create_tip calls CreateSidekickItem with type=tip."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "tip-123"}
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.create_tip(
            customer_id="customer-456",
            text="Detected frustrated tone in email",
            need_id="need-789",
        )

        mock_dc.execute_mutation.assert_called_once_with(
            "CreateSidekickItem",
            {
                "workspaceId": workspace_id,
                "customerId": "customer-456",
                "type": "tip",
                "text": "Detected frustrated tone in email",
                "needId": "need-789",
            },
        )
        assert result == {"id": "tip-123"}

    @pytest.mark.asyncio
    async def test_create_tip_without_need_id(self):
        """Test that create_tip works without need_id."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "tip-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        await service.create_tip(
            customer_id="customer-456",
            text="Some observation",
        )

        call_args = mock_dc.execute_mutation.call_args[0][1]
        assert call_args["needId"] is None


class TestSidekickServiceCreateObserved:
    """Tests for creating observed items."""

    @pytest.mark.asyncio
    async def test_create_observed_calls_correct_mutation(self):
        """Test that create_observed calls CreateSidekickItem with type=observed."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "observed-123"}
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.create_observed(
            customer_id="customer-456",
            text="Last activity was 14 days ago",
        )

        mock_dc.execute_mutation.assert_called_once()
        call_args = mock_dc.execute_mutation.call_args[0][1]
        assert call_args["type"] == "observed"
        assert call_args["text"] == "Last activity was 14 days ago"


class TestSidekickServiceCreateAsking:
    """Tests for creating asking (HITL question) items."""

    @pytest.mark.asyncio
    async def test_create_asking_includes_all_fields(self):
        """Test that create_asking includes question, why, and blocking status."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "asking-123"}
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.create_asking(
            customer_id="customer-456",
            question="Who is the primary champion?",
            why="Need to confirm contact before proceeding",
            is_blocking=True,
            agent_run_id="run-789",
            need_id="need-101",
        )

        mock_dc.execute_mutation.assert_called_once()
        call_args = mock_dc.execute_mutation.call_args[0][1]

        assert call_args["type"] == "asking"
        assert call_args["question"] == "Who is the primary champion?"
        assert call_args["why"] == "Need to confirm contact before proceeding"
        assert call_args["isBlocking"] is True
        assert call_args["agentRunId"] == "run-789"
        assert call_args["needId"] == "need-101"

    @pytest.mark.asyncio
    async def test_create_asking_defaults_is_blocking_to_true(self):
        """Test that is_blocking defaults to True."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "asking-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        await service.create_asking(
            customer_id="customer-456",
            question="What is the ARR?",
            why="Required for prioritization",
        )

        call_args = mock_dc.execute_mutation.call_args[0][1]
        assert call_args["isBlocking"] is True

    @pytest.mark.asyncio
    async def test_create_asking_can_be_non_blocking(self):
        """Test that asking items can be non-blocking."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "asking-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        await service.create_asking(
            customer_id="customer-456",
            question="Optional question",
            why="Not critical",
            is_blocking=False,
        )

        call_args = mock_dc.execute_mutation.call_args[0][1]
        assert call_args["isBlocking"] is False


class TestSidekickServiceCreateWorking:
    """Tests for creating working (progress) items."""

    @pytest.mark.asyncio
    async def test_create_working_includes_progress_fields(self):
        """Test that create_working includes task, step, and progress info."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "working-123"}
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.create_working(
            customer_id="customer-456",
            task="Processing new customer handoff",
            step="Analyzing deal notes",
            step_num=2,
            total_steps=5,
            agent_run_id="run-789",
        )

        mock_dc.execute_mutation.assert_called_once()
        call_args = mock_dc.execute_mutation.call_args[0][1]

        assert call_args["type"] == "working"
        assert call_args["task"] == "Processing new customer handoff"
        assert call_args["step"] == "Analyzing deal notes"
        assert call_args["stepNum"] == 2
        assert call_args["totalSteps"] == 5
        assert call_args["agentRunId"] == "run-789"


class TestSidekickServiceResolveItem:
    """Tests for resolving sidekick items."""

    @pytest.mark.asyncio
    async def test_resolve_item_calls_correct_mutation(self):
        """Test that resolve_item calls ResolveSidekickItem mutation."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_update": {"id": "item-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.resolve_item(
            item_id="item-123",
            resolution="Champion confirmed as Sarah Chen",
            resolved_by_user_id="user-456",
        )

        mock_dc.execute_mutation.assert_called_once_with(
            "ResolveSidekickItem",
            {
                "id": "item-123",
                "resolution": "Champion confirmed as Sarah Chen",
                "resolvedByUserId": "user-456",
            },
        )


class TestSidekickServiceDeleteItem:
    """Tests for deleting sidekick items."""

    @pytest.mark.asyncio
    async def test_delete_item_calls_correct_mutation(self):
        """Test that delete_item calls DeleteSidekickItem mutation."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {}

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.delete_item("item-123")

        mock_dc.execute_mutation.assert_called_once_with(
            "DeleteSidekickItem",
            {"id": "item-123"},
        )
        assert result is True


class TestSidekickServiceGetItem:
    """Tests for fetching single sidekick items."""

    @pytest.mark.asyncio
    async def test_get_item_returns_item_data(self):
        """Test that get_item returns the item from query."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItem": {
                "id": "item-123",
                "type": "asking",
                "question": "Test question?",
            }
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_item("item-123")

        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickItem",
            {"id": "item-123"},
        )
        assert result["id"] == "item-123"
        assert result["type"] == "asking"

    @pytest.mark.asyncio
    async def test_get_item_returns_none_when_not_found(self):
        """Test that get_item returns None when item doesn't exist."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {"sidekickItem": None}

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_item("nonexistent-123")

        assert result is None


class TestSidekickServiceGetItemsForCustomer:
    """Tests for fetching items for a customer."""

    @pytest.mark.asyncio
    async def test_get_items_for_customer_returns_items(self):
        """Test that get_items_for_customer returns list of items."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "tip"},
                {"id": "item-2", "type": "asking"},
            ]
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.get_items_for_customer("customer-456")

        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickItems",
            {
                "workspaceId": workspace_id,
                "customerId": "customer-456",
            },
        )
        assert len(result) == 2
        assert result[0]["id"] == "item-1"

    @pytest.mark.asyncio
    async def test_get_items_for_customer_returns_empty_list(self):
        """Test that get_items_for_customer returns empty list when none exist."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {"sidekickItems": []}

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_items_for_customer("customer-456")

        assert result == []


class TestSidekickServiceGetUnansweredCount:
    """Tests for counting unanswered questions."""

    @pytest.mark.asyncio
    async def test_get_unanswered_count_workspace_wide(self):
        """Test that workspace-wide count uses GetSidekickUnansweredCount."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1"},
                {"id": "item-2"},
                {"id": "item-3"},
            ]
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.get_unanswered_count()

        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickUnansweredCount",
            {"workspaceId": workspace_id},
        )
        assert result == 3

    @pytest.mark.asyncio
    async def test_get_unanswered_count_for_customer(self):
        """Test that customer-specific count filters asking items."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "asking", "resolvedAt": None},
                {"id": "item-2", "type": "asking", "resolvedAt": "2024-01-01"},
                {"id": "item-3", "type": "tip", "resolvedAt": None},
            ]
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_unanswered_count(customer_id="customer-456")

        # Should only count asking items without resolvedAt
        assert result == 1


class TestSidekickServiceGetUnansweredItems:
    """Tests for fetching unanswered questions."""

    @pytest.mark.asyncio
    async def test_get_unanswered_items_for_customer(self):
        """Test that get_unanswered_items filters correctly."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "asking", "resolvedAt": None},
                {"id": "item-2", "type": "asking", "resolvedAt": "2024-01-01"},
                {"id": "item-3", "type": "tip", "resolvedAt": None},
            ]
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_unanswered_items(customer_id="customer-456")

        # Should only return unresolved asking items
        assert len(result) == 1
        assert result[0]["id"] == "item-1"

    @pytest.mark.asyncio
    async def test_get_unanswered_items_workspace_wide(self):
        """Test workspace-wide unanswered items uses GetSidekickUnansweredCount."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1"},
                {"id": "item-2"},
            ]
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.get_unanswered_items()

        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickUnansweredCount",
            {"workspaceId": workspace_id},
        )
        assert len(result) == 2


class TestSidekickServiceCreateAskingBatch:
    """Tests for creating batch asking items."""

    @pytest.mark.asyncio
    async def test_create_asking_batch_creates_summary_item(self):
        """Test that create_asking_batch creates a summary item for multiple questions."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "asking-batch-123"}
        }

        workspace_id = "workspace-123"
        service = SidekickService(mock_dc, workspace_id)

        result = await service.create_asking_batch(
            customer_id="customer-456",
            agent_run_id="run-789",
            question_count=3,
            reason="Need more context about customer goals",
            need_id="need-101",
        )

        mock_dc.execute_mutation.assert_called_once()
        call_args = mock_dc.execute_mutation.call_args[0][1]

        assert call_args["type"] == "asking"
        assert call_args["question"] == "Sidekick has 3 questions for you"
        assert call_args["why"] == "Need more context about customer goals"
        assert call_args["agentRunId"] == "run-789"
        assert call_args["needId"] == "need-101"
        assert call_args["isBlocking"] is True

    @pytest.mark.asyncio
    async def test_create_asking_batch_singular_question(self):
        """Test singular phrasing for single question."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_insert": {"id": "asking-batch-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        await service.create_asking_batch(
            customer_id="customer-456",
            agent_run_id="run-789",
            question_count=1,
            reason="Need champion confirmation",
        )

        call_args = mock_dc.execute_mutation.call_args[0][1]
        assert call_args["question"] == "Sidekick has a question for you"


class TestSidekickServiceUpdateWorkingProgress:
    """Tests for updating working item progress."""

    @pytest.mark.asyncio
    async def test_update_working_progress(self):
        """Test that update_working_progress calls correct mutation."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_update": {"id": "working-123"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.update_working_progress(
            item_id="working-123",
            step="Classifying signals",
            step_num=2,
        )

        mock_dc.execute_mutation.assert_called_once_with(
            "UpdateSidekickItemProgress",
            {
                "id": "working-123",
                "step": "Classifying signals",
                "stepNum": 2,
            },
        )


class TestSidekickServiceAutoResolve:
    """Tests for auto-resolving items by agent run."""

    @pytest.mark.asyncio
    async def test_auto_resolve_resolves_asking_items(self):
        """Test that auto_resolve_for_agent_run resolves unresolved asking items."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "asking", "resolvedAt": None},
                {"id": "item-2", "type": "asking", "resolvedAt": "2024-01-01"},  # Already resolved
                {"id": "item-3", "type": "working", "resolvedAt": None},  # Not asking type
            ]
        }
        mock_dc.execute_mutation.return_value = {
            "sidekickItem_update": {"id": "item-1"}
        }

        service = SidekickService(mock_dc, "workspace-123")

        resolved = await service.auto_resolve_for_agent_run(
            agent_run_id="run-789",
            resolved_by_user_id="user-456",
        )

        # Should query for items
        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickItemsByAgentRun",
            {"agentRunId": "run-789"},
        )

        # Should only resolve the unresolved asking item
        assert mock_dc.execute_mutation.call_count == 1
        call_args = mock_dc.execute_mutation.call_args[0]
        assert call_args[0] == "BatchResolveSidekickItem"
        assert call_args[1]["id"] == "item-1"
        assert call_args[1]["resolvedByUserId"] == "user-456"

    @pytest.mark.asyncio
    async def test_auto_resolve_handles_no_items(self):
        """Test that auto_resolve handles no items gracefully."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {"sidekickItems": []}

        service = SidekickService(mock_dc, "workspace-123")

        resolved = await service.auto_resolve_for_agent_run(
            agent_run_id="run-789",
            resolved_by_user_id="user-456",
        )

        assert resolved == []
        mock_dc.execute_mutation.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_resolve_continues_on_individual_failure(self):
        """Test that auto_resolve continues if one item fails to resolve."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "asking", "resolvedAt": None},
                {"id": "item-2", "type": "asking", "resolvedAt": None},
            ]
        }
        # First call succeeds, second fails
        mock_dc.execute_mutation.side_effect = [
            {"sidekickItem_update": {"id": "item-1"}},
            Exception("Database error"),
        ]

        service = SidekickService(mock_dc, "workspace-123")

        resolved = await service.auto_resolve_for_agent_run(
            agent_run_id="run-789",
            resolved_by_user_id="user-456",
        )

        # Should have resolved one item despite the error
        assert len(resolved) == 1
        assert resolved[0]["id"] == "item-1"


class TestSidekickServiceGetItemsForAgentRun:
    """Tests for fetching items by agent run."""

    @pytest.mark.asyncio
    async def test_get_items_for_agent_run(self):
        """Test that get_items_for_agent_run queries correctly."""
        from services.sidekick_service import SidekickService

        mock_dc = AsyncMock()
        mock_dc.execute_query.return_value = {
            "sidekickItems": [
                {"id": "item-1", "type": "asking"},
                {"id": "item-2", "type": "working"},
            ]
        }

        service = SidekickService(mock_dc, "workspace-123")

        result = await service.get_items_for_agent_run("run-789")

        mock_dc.execute_query.assert_called_once_with(
            "GetSidekickItemsByAgentRun",
            {"agentRunId": "run-789"},
        )
        assert len(result) == 2
