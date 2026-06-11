"""
HandoffChain Agent Tests
"""

import pytest
from unittest.mock import AsyncMock, patch

from agents.handoff_chain.context import HandoffContext
from agents.handoff_chain.steps import (
    read_deal_step,
    read_playbook_step,
)


@pytest.mark.asyncio
async def test_handoff_context_initialization(workspace_id, notion_deal_id):
    """Test HandoffContext creates with correct initial state."""
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
    )

    assert ctx.workspace_id == workspace_id
    assert ctx.notion_deal_id == notion_deal_id
    assert ctx.customer_id is None
    assert ctx.run_id is not None
    assert len(ctx.errors) == 0
    assert not ctx.is_failed


@pytest.mark.asyncio
async def test_handoff_context_with_deal_data(workspace_id, notion_deal_id, mock_deal_data):
    """Test HandoffContext.with_deal_data returns new context."""
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
    )

    new_ctx = ctx.with_deal_data(mock_deal_data)

    assert new_ctx.deal_data == mock_deal_data
    assert new_ctx.company_name == "TestCorp"
    assert new_ctx.run_id == ctx.run_id  # Same run


@pytest.mark.asyncio
async def test_handoff_context_error_tracking(workspace_id, notion_deal_id):
    """Test HandoffContext tracks errors correctly."""
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
    )

    error_ctx = ctx.with_error("TestStep", "Something went wrong")

    assert error_ctx.is_failed
    assert error_ctx.failed_step == "TestStep"
    assert "TestStep: Something went wrong" in error_ctx.errors


@pytest.mark.asyncio
async def test_read_deal_step_with_mock(workspace_id, notion_deal_id, mock_deal_data):
    """Test ReadDealStep with mocked Notion tool."""
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
    )

    with patch("agents.handoff_chain.steps.read_notion_deal") as mock_notion:
        mock_notion.return_value = mock_deal_data

        result = await read_deal_step(ctx)

        assert result.deal_data is not None
        assert result.deal_data["company_name"] == "TestCorp"
        mock_notion.assert_called_once_with(
            deal_id=notion_deal_id,
            workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_read_playbook_step_with_mock(
    workspace_id, notion_deal_id, mock_deal_data, mock_playbook, mock_milestones
):
    """Test ReadPlaybookStep with mocked database."""
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
    ).with_deal_data(mock_deal_data)

    with patch("agents.handoff_chain.steps.get_playbook") as mock_get_playbook:
        with patch("agents.handoff_chain.steps.get_playbook_milestones") as mock_get_milestones:
            mock_get_playbook.return_value = mock_playbook
            mock_get_milestones.return_value = mock_milestones

            result = await read_playbook_step(ctx)

            assert result.playbook is not None
            assert result.playbook["name"] == "Standard SaaS Onboarding"
            assert len(result.playbook_milestones) == 3


@pytest.mark.asyncio
async def test_handoff_chain_api_endpoint(client, workspace_id, notion_deal_id):
    """Test the /agents/handoff-chain/run endpoint."""
    # This test requires mocking the entire agent
    # In a real test, you'd use a test database with seed data

    with patch("routes.agents.run_handoff_chain") as mock_run:
        mock_run.return_value = type(
            "Result",
            (),
            {
                "run_id": "test-run-123",
                "status": "completed",
                "customer_id": "cust-123",
                "brief_id": "brief-123",
                "plan_id": "plan-123",
                "need_id": "need-123",
                "error": None,
            },
        )()

        response = await client.post(
            "/agents/handoff-chain/run",
            json={
                "workspace_id": workspace_id,
                "notion_deal_id": notion_deal_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["run_id"] == "test-run-123"
