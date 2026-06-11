"""
Sidekick Routes Unit Tests
Tests for Sidekick API endpoints
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetUnansweredCount:
    """Tests for GET /workspaces/{workspace_id}/sidekick/count endpoint."""

    @pytest.mark.asyncio
    async def test_get_count_returns_unanswered_count(self):
        """Test that count endpoint returns the unanswered question count."""
        from routes.sidekick import get_unanswered_count

        # Mock dependencies
        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_unanswered_count.return_value = 5
                mock_service_class.return_value = mock_service

                result = await get_unanswered_count(
                    workspace_id="workspace-123",
                    customer_id=None,
                    user=mock_user,
                )

                assert result.count == 5
                mock_service.get_unanswered_count.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_get_count_with_customer_filter(self):
        """Test that count endpoint filters by customer when provided."""
        from routes.sidekick import get_unanswered_count

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_unanswered_count.return_value = 2
                mock_service_class.return_value = mock_service

                result = await get_unanswered_count(
                    workspace_id="workspace-123",
                    customer_id="customer-456",
                    user=mock_user,
                )

                assert result.count == 2
                mock_service.get_unanswered_count.assert_called_once_with("customer-456")


class TestResolveItem:
    """Tests for POST /workspaces/{workspace_id}/sidekick/items/{item_id}/resolve endpoint."""

    @pytest.mark.asyncio
    async def test_resolve_item_success_without_agent(self):
        """Test resolving an item that is not linked to an agent run."""
        from routes.sidekick import resolve_item, ResolveItemRequest

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "workspace-123"},
                    "agentRun": None,
                }
                mock_service.resolve_item.return_value = {"id": "item-123"}
                mock_service_class.return_value = mock_service

                request = ResolveItemRequest(resolution="Champion is Sarah Chen")

                result = await resolve_item(
                    workspace_id="workspace-123",
                    item_id="item-123",
                    request=request,
                    user=mock_user,
                )

                assert result.success is True
                assert result.item_id == "item-123"
                assert result.agent_resumed is False
                mock_service.resolve_item.assert_called_once_with(
                    item_id="item-123",
                    resolution="Champion is Sarah Chen",
                    resolved_by_user_id="user-123",
                )

    @pytest.mark.asyncio
    async def test_resolve_item_not_found_returns_404(self):
        """Test that resolving a non-existent item returns 404."""
        from routes.sidekick import resolve_item, ResolveItemRequest
        from fastapi.responses import JSONResponse

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_item.return_value = None
                mock_service_class.return_value = mock_service

                request = ResolveItemRequest(resolution="Some answer")

                result = await resolve_item(
                    workspace_id="workspace-123",
                    item_id="nonexistent-123",
                    request=request,
                    user=mock_user,
                )

                assert isinstance(result, JSONResponse)
                assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_item_wrong_workspace_returns_404(self):
        """Test that resolving an item from wrong workspace returns 404 (security)."""
        from routes.sidekick import resolve_item, ResolveItemRequest
        from fastapi.responses import JSONResponse

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                # Item belongs to different workspace
                mock_service.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "other-workspace-999"},
                    "agentRun": None,
                }
                mock_service_class.return_value = mock_service

                request = ResolveItemRequest(resolution="Some answer")

                result = await resolve_item(
                    workspace_id="workspace-123",  # Different from item's workspace
                    item_id="item-123",
                    request=request,
                    user=mock_user,
                )

                # Should return 404 to not leak existence
                assert isinstance(result, JSONResponse)
                assert result.status_code == 404
                # Should NOT have called resolve_item
                mock_service.resolve_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_item_resumes_waiting_agent(self):
        """Test that resolving an item linked to a waiting agent resumes it."""
        from routes.sidekick import resolve_item, ResolveItemRequest

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_sidekick_class:
                mock_sidekick = AsyncMock()
                mock_sidekick.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "workspace-123"},
                    "question": "What is the ARR?",
                    "agentRun": {"id": "run-789"},
                }
                mock_sidekick.resolve_item.return_value = {"id": "item-123"}
                mock_sidekick_class.return_value = mock_sidekick

                with patch("routes.sidekick.AgentRunService") as mock_agent_class:
                    mock_agent = AsyncMock()
                    mock_agent.get_run.return_value = {
                        "id": "run-789",
                        "status": "waiting_for_input",
                    }
                    mock_agent.resume_from_input.return_value = {}
                    mock_agent_class.return_value = mock_agent

                    request = ResolveItemRequest(resolution="$50K ARR")

                    result = await resolve_item(
                        workspace_id="workspace-123",
                        item_id="item-123",
                        request=request,
                        user=mock_user,
                    )

                    assert result.success is True
                    assert result.agent_resumed is True
                    # Should use item_id as the answer key
                    mock_agent.resume_from_input.assert_called_once_with(
                        run_id="run-789",
                        answers={"item-123": "$50K ARR"},
                    )

    @pytest.mark.asyncio
    async def test_resolve_item_does_not_resume_non_waiting_agent(self):
        """Test that agent is not resumed if not in waiting_for_input status."""
        from routes.sidekick import resolve_item, ResolveItemRequest

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_sidekick_class:
                mock_sidekick = AsyncMock()
                mock_sidekick.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "workspace-123"},
                    "agentRun": {"id": "run-789"},
                }
                mock_sidekick.resolve_item.return_value = {"id": "item-123"}
                mock_sidekick_class.return_value = mock_sidekick

                with patch("routes.sidekick.AgentRunService") as mock_agent_class:
                    mock_agent = AsyncMock()
                    mock_agent.get_run.return_value = {
                        "id": "run-789",
                        "status": "completed",  # Not waiting
                    }
                    mock_agent_class.return_value = mock_agent

                    request = ResolveItemRequest(resolution="Answer")

                    result = await resolve_item(
                        workspace_id="workspace-123",
                        item_id="item-123",
                        request=request,
                        user=mock_user,
                    )

                    assert result.success is True
                    assert result.agent_resumed is False
                    mock_agent.resume_from_input.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_item_continues_on_agent_resume_failure(self):
        """Test that item is still resolved even if agent resume fails."""
        from routes.sidekick import resolve_item, ResolveItemRequest

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_sidekick_class:
                mock_sidekick = AsyncMock()
                mock_sidekick.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "workspace-123"},
                    "agentRun": {"id": "run-789"},
                }
                mock_sidekick.resolve_item.return_value = {"id": "item-123"}
                mock_sidekick_class.return_value = mock_sidekick

                with patch("routes.sidekick.AgentRunService") as mock_agent_class:
                    mock_agent = AsyncMock()
                    mock_agent.get_run.return_value = {
                        "id": "run-789",
                        "status": "waiting_for_input",
                    }
                    # Simulate agent resume failure
                    mock_agent.resume_from_input.side_effect = Exception("Agent error")
                    mock_agent_class.return_value = mock_agent

                    request = ResolveItemRequest(resolution="Answer")

                    result = await resolve_item(
                        workspace_id="workspace-123",
                        item_id="item-123",
                        request=request,
                        user=mock_user,
                    )

                    # Should still succeed, just not resume agent
                    assert result.success is True
                    assert result.agent_resumed is False
                    # Item should have been resolved
                    mock_sidekick.resolve_item.assert_called_once()


class TestWorkspaceSecurityValidation:
    """Tests specifically for workspace authorization security."""

    @pytest.mark.asyncio
    async def test_cross_workspace_access_blocked(self):
        """
        Security test: Verify that users cannot access items from other workspaces.
        This is a critical security check.
        """
        from routes.sidekick import resolve_item, ResolveItemRequest
        from fastapi.responses import JSONResponse

        mock_user = MagicMock()
        mock_user.uid = "attacker-user"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                # Attacker knows item ID from workspace B
                mock_service.get_item.return_value = {
                    "id": "victim-item-123",
                    "type": "asking",
                    "question": "Sensitive question?",
                    "workspace": {"id": "workspace-B"},  # Victim's workspace
                }
                mock_service_class.return_value = mock_service

                request = ResolveItemRequest(resolution="Malicious answer")

                # Attacker has access to workspace-A but tries to resolve
                # an item from workspace-B
                result = await resolve_item(
                    workspace_id="workspace-A",  # Attacker's workspace
                    item_id="victim-item-123",
                    request=request,
                    user=mock_user,
                )

                # Should be blocked with 404
                assert isinstance(result, JSONResponse)
                assert result.status_code == 404
                # Item should NOT have been resolved
                mock_service.resolve_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_workspace_access_allowed(self):
        """Test that users CAN access items from their own workspace."""
        from routes.sidekick import resolve_item, ResolveItemRequest

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        with patch("routes.sidekick.get_dataconnect_client") as mock_get_dc:
            mock_dc = AsyncMock()
            mock_get_dc.return_value = mock_dc

            with patch("routes.sidekick.SidekickService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_item.return_value = {
                    "id": "item-123",
                    "type": "asking",
                    "workspace": {"id": "workspace-123"},  # Same workspace
                }
                mock_service.resolve_item.return_value = {"id": "item-123"}
                mock_service_class.return_value = mock_service

                request = ResolveItemRequest(resolution="Valid answer")

                result = await resolve_item(
                    workspace_id="workspace-123",  # Same as item's workspace
                    item_id="item-123",
                    request=request,
                    user=mock_user,
                )

                # Should succeed
                assert result.success is True
                mock_service.resolve_item.assert_called_once()
