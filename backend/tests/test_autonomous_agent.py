"""
Autonomous Handoff Agent Tests
Tests for the true autonomous agent with FunctionTools
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAutonomousAgentTools:
    """Tests for the autonomous agent's tool functions."""

    @pytest.mark.asyncio
    async def test_tool_get_customer_info_returns_customer_data(self):
        """Test that get_customer_info returns comprehensive customer details."""
        from agents.handoff_auto.autonomous_agent import tool_get_customer_info

        mock_customer = {
            "id": "cust-123",
            "name": "Acme Corp",
            "slug": "acme-corp",
            "tier": "Enterprise",
            "arrCents": 50000000,
            "lifecycle": "onboarding",
            "oneLiner": "B2B SaaS company",
            "daysToRenewal": 180,
            "onboardingDayCurrent": 15,
            "onboardingDayTotal": 45,
            "renewalReadiness": "not_started",
            "valueRealizationText": "50% time savings",
            "enrichmentStatus": "complete",
            "rawNotes": "Key enterprise deal",
            "stakeholders_on_customer": [
                {"name": "Jane Doe", "email": "jane@acme.com", "role": "VP Eng", "status": "active", "sentimentNote": "positive"}
            ],
            "goals_on_customer": [
                {"text": "Reduce deployment time", "status": "active"}
            ],
            "signals_on_customer": [
                {"kind": "engagement", "state": "ok", "sentence": "Active", "evidenceText": "12 logins", "nextAction": None}
            ],
            "milestones_on_customer": [
                {"title": "Kickoff", "status": "done", "ownerSide": "us", "targetDate": "2024-01-15", "blockedReason": None}
            ],
            "commitments_on_customer": [
                {"side": "us", "text": "Send docs", "dueLabel": "Tomorrow", "status": "in_progress"}
            ],
        }

        with patch("agents.handoff_auto.autonomous_agent.get_dataconnect_client") as mock_dc:
            mock_client = MagicMock()
            mock_client.get_customer = AsyncMock(return_value=mock_customer)
            mock_dc.return_value = mock_client

            result = await tool_get_customer_info("cust-123", "workspace-456")

            # Core fields
            assert result["id"] == "cust-123"
            assert result["name"] == "Acme Corp"
            assert result["tier"] == "Enterprise"
            assert result["arr_cents"] == 50000000
            # Onboarding progress
            assert result["onboarding_day_current"] == 15
            assert result["onboarding_day_total"] == 45
            # Stakeholders
            assert len(result["stakeholders"]) == 1
            assert result["stakeholders"][0]["name"] == "Jane Doe"
            assert result["stakeholders"][0]["role"] == "VP Eng"
            # Goals
            assert len(result["goals"]) == 1
            assert result["goals"][0]["text"] == "Reduce deployment time"
            # Signals
            assert len(result["signals"]) == 1
            assert result["signals"][0]["state"] == "ok"
            # Milestones
            assert len(result["milestones"]) == 1
            assert result["milestones"][0]["title"] == "Kickoff"
            # Commitments
            assert len(result["commitments"]) == 1
            assert result["commitments"][0]["side"] == "us"

            mock_client.get_customer.assert_called_once_with("cust-123")

    @pytest.mark.asyncio
    async def test_tool_get_customer_info_handles_not_found(self):
        """Test that get_customer_info handles missing customer."""
        from agents.handoff_auto.autonomous_agent import tool_get_customer_info

        with patch("agents.handoff_auto.autonomous_agent.get_dataconnect_client") as mock_dc:
            mock_client = MagicMock()
            mock_client.get_customer = AsyncMock(return_value=None)
            mock_dc.return_value = mock_client

            result = await tool_get_customer_info("nonexistent", "workspace-456")

            assert "error" in result
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_get_playbook_returns_playbook_with_milestones(self):
        """Test that get_playbook_for_workspace returns playbook and milestones."""
        from agents.handoff_auto.autonomous_agent import tool_get_playbook_for_workspace

        mock_playbook = {
            "id": "playbook-123",
            "name": "Standard Onboarding",
            "archetype": "Mid-Market",
        }

        mock_milestones = [
            {"id": "m1", "title": "Kickoff", "duration_days": 7},
            {"id": "m2", "title": "Setup", "duration_days": 14},
        ]

        with patch("agents.handoff_auto.autonomous_agent.get_playbook") as mock_get_pb:
            with patch("agents.handoff_auto.autonomous_agent.get_playbook_milestones") as mock_get_ms:
                mock_get_pb.return_value = mock_playbook
                mock_get_ms.return_value = mock_milestones

                result = await tool_get_playbook_for_workspace("workspace-456")

                assert result["name"] == "Standard Onboarding"
                assert len(result["milestones"]) == 2
                mock_get_pb.assert_called_once_with("workspace-456", None)
                mock_get_ms.assert_called_once_with("playbook-123", "workspace-456")

    @pytest.mark.asyncio
    async def test_tool_generate_plan_creates_plan(self):
        """Test that generate_onboarding_plan creates a plan."""
        from agents.handoff_auto.autonomous_agent import tool_generate_onboarding_plan

        mock_plan = {
            "id": "plan-123",
            "milestone_count": 5,
            "duration_label": "45 days",
        }

        mock_adapted_milestones = [
            {"title": "M1", "target_days": 7},
        ]

        with patch("agents.handoff_auto.autonomous_agent.get_db_client") as mock_db:
            with patch("agents.handoff_auto.autonomous_agent.PlanService") as mock_service_cls:
                mock_service = MagicMock()
                mock_service.adapt_milestones = AsyncMock(return_value=mock_adapted_milestones)
                mock_service.create_plan = AsyncMock(return_value=mock_plan)
                mock_service_cls.return_value = mock_service

                result = await tool_generate_onboarding_plan(
                    workspace_id="workspace-456",
                    customer_id="cust-123",
                    customer_name="Acme Corp",
                    playbook={"name": "Standard", "archetype": "Mid-Market"},
                    milestones=[{"title": "Kickoff", "duration_days": 7}],
                )

                assert result["id"] == "plan-123"
                mock_service.create_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_surface_need_creates_need(self):
        """Test that surface_need_for_review creates a need."""
        from agents.handoff_auto.autonomous_agent import tool_surface_need_for_review

        mock_need = {
            "id": "need-123",
            "type": "plan_approval_required",
            "headline": "Review plan",
        }

        with patch("agents.handoff_auto.autonomous_agent.insert_need") as mock_insert:
            mock_insert.return_value = mock_need

            result = await tool_surface_need_for_review(
                workspace_id="workspace-456",
                customer_id="cust-123",
                customer_name="Acme Corp",
                plan_id="plan-789",
                milestone_count=5,
                playbook_name="Standard Onboarding",
            )

            assert result["id"] == "need-123"
            mock_insert.assert_called_once()
            call_kwargs = mock_insert.call_args[1]
            assert call_kwargs["need_type"] == "plan_approval_required"
            assert "Acme Corp" in call_kwargs["headline"]


class TestToolDefinitions:
    """Tests for tool schema definitions."""

    def test_tools_are_defined(self):
        """Test that TOOLS list is properly defined."""
        from agents.handoff_auto.autonomous_agent import TOOLS

        assert len(TOOLS) == 1
        tool = TOOLS[0]
        # 4 core + 1 memory + 2 planning/eval + 2 HITL = 9 tools
        assert len(tool.function_declarations) == 9

    def test_tool_implementations_match_declarations(self):
        """Test that all declared tools have implementations."""
        from agents.handoff_auto.autonomous_agent import TOOLS, TOOL_IMPLEMENTATIONS

        declared_names = {
            fd.name for fd in TOOLS[0].function_declarations
        }
        implemented_names = set(TOOL_IMPLEMENTATIONS.keys())

        assert declared_names == implemented_names, f"Mismatch: declared={declared_names}, implemented={implemented_names}"

    def test_memory_tools_exist(self):
        """Test that memory tools are available."""
        from agents.handoff_auto.autonomous_agent import TOOL_IMPLEMENTATIONS

        assert "recall_memory" in TOOL_IMPLEMENTATIONS

    def test_planning_tools_exist(self):
        """Test that planning tools are available."""
        from agents.handoff_auto.autonomous_agent import TOOL_IMPLEMENTATIONS

        assert "create_plan" in TOOL_IMPLEMENTATIONS
        assert "evaluate_generated_plan" in TOOL_IMPLEMENTATIONS


class TestMemoryTools:
    """Tests for memory tool functions."""

    @pytest.mark.asyncio
    async def test_recall_memory_past_plans(self):
        """Test recalling past plans from memory."""
        from agents.handoff_auto.autonomous_agent import tool_recall_memory

        with patch("agents.handoff_auto.autonomous_agent.AgentMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.recall_past_plans = AsyncMock(return_value=[
                {"id": "plan-1", "headline": "Test plan", "status": "approved"}
            ])
            mock_memory_cls.return_value = mock_memory

            result = await tool_recall_memory(
                workspace_id="workspace-456",
                memory_type="past_plans",
            )

            assert result["type"] == "past_plans"
            assert len(result["plans"]) == 1
            mock_memory.recall_past_plans.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_memory_success_patterns(self):
        """Test recalling success patterns from memory."""
        from agents.handoff_auto.autonomous_agent import tool_recall_memory

        with patch("agents.handoff_auto.autonomous_agent.AgentMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.recall_success_patterns = AsyncMock(return_value={
                "archetype_performance": [{"archetype": "Standard", "approval_rate": 90}],
                "tier_patterns": [],
                "insights": ["Standard archetype has highest approval rate"],
            })
            mock_memory_cls.return_value = mock_memory

            result = await tool_recall_memory(
                workspace_id="workspace-456",
                memory_type="success_patterns",
            )

            assert result["type"] == "success_patterns"
            assert "patterns" in result

    @pytest.mark.asyncio
    async def test_recall_memory_unknown_type(self):
        """Test that unknown memory type returns error."""
        from agents.handoff_auto.autonomous_agent import tool_recall_memory

        with patch("agents.handoff_auto.autonomous_agent.AgentMemory"):
            result = await tool_recall_memory(
                workspace_id="workspace-456",
                memory_type="unknown_type",
            )

            assert "error" in result


class TestPlanningTools:
    """Tests for planning tool functions."""

    @pytest.mark.asyncio
    async def test_create_plan_returns_execution_plan(self):
        """Test that create_plan generates an execution plan."""
        from agents.handoff_auto.autonomous_agent import tool_create_plan

        with patch("agents.handoff_auto.autonomous_agent.AgentMemory") as mock_memory_cls:
            with patch("agents.handoff_auto.autonomous_agent.create_execution_plan") as mock_create:
                mock_memory = MagicMock()
                mock_memory.recall_past_plans = AsyncMock(return_value=[])
                mock_memory.recall_success_patterns = AsyncMock(return_value={})
                mock_memory_cls.return_value = mock_memory

                mock_create.return_value = {
                    "plan_summary": "Generate onboarding plan",
                    "tasks": [{"id": 1, "action": "Get customer info"}],
                    "success_criteria": ["Plan created"],
                    "estimated_confidence": 0.8,
                }

                result = await tool_create_plan(
                    goal="Generate onboarding plan for new customer",
                    workspace_id="workspace-456",
                    customer_id="cust-123",
                    customer_name="Acme Corp",
                )

                assert "plan_summary" in result
                assert "tasks" in result
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_generated_plan_returns_assessment(self):
        """Test that evaluate_generated_plan returns quality assessment."""
        from agents.handoff_auto.autonomous_agent import tool_evaluate_generated_plan

        with patch("agents.handoff_auto.autonomous_agent.AgentMemory"):
            with patch("agents.handoff_auto.autonomous_agent.evaluate_plan_quality") as mock_eval:
                mock_eval.return_value = {
                    "quality_score": 0.85,
                    "confidence": 0.9,
                    "issues": [],
                    "suggestions": [],
                    "would_approve_immediately": True,
                    "reasoning": "Plan looks good",
                }

                result = await tool_evaluate_generated_plan(
                    plan={"headline": "Test plan", "milestone_count": 5},
                    customer_name="Acme Corp",
                    customer_tier="Enterprise",
                )

                assert result["quality_score"] == 0.85
                assert result["would_approve_immediately"] is True


class TestAutonomousAgentFlow:
    """Integration-style tests for the agent flow."""

    @pytest.mark.asyncio
    async def test_run_autonomous_handoff_initializes_correctly(self):
        """Test that run_autonomous_handoff starts properly."""
        # This is a smoke test - full integration would need real Gemini
        from agents.handoff_auto.autonomous_agent import run_autonomous_handoff

        # Mock everything to avoid real API calls
        with patch("agents.handoff_auto.autonomous_agent.get_dataconnect_client") as mock_dc:
            with patch("agents.handoff_auto.autonomous_agent.AgentRunService") as mock_run_svc:
                with patch("agents.handoff_auto.autonomous_agent.genai") as mock_genai:
                    with patch("agents.handoff_auto.autonomous_agent.reflect_on_execution") as mock_reflect:
                        # Setup mocks
                        mock_dc_client = MagicMock()
                        mock_dc.return_value = mock_dc_client

                        mock_service = MagicMock()
                        mock_service.create_run = AsyncMock(return_value={"id": "run-123"})
                        mock_service.start_run = AsyncMock()
                        mock_service.fail_run = AsyncMock()
                        mock_run_svc.return_value = mock_service

                        # Mock reflection
                        mock_reflect.return_value = {"patterns_learned": [], "confidence_for_next_run": 0.5}

                        # Mock Gemini to return empty response (will fail gracefully)
                        mock_client = MagicMock()
                        mock_response = MagicMock()
                        mock_response.candidates = [MagicMock()]
                        mock_response.candidates[0].content.parts = []
                        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
                        mock_genai.Client.return_value = mock_client

                        result = await run_autonomous_handoff(
                            workspace_id="workspace-456",
                            customer_id="cust-123",
                        )

                        # Should fail because of empty response, but that's expected
                        assert result["run_id"] == "run-123"
                        mock_service.create_run.assert_called_once()
