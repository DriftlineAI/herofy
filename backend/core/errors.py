"""
Herofy Error Hierarchy
Structured exceptions matching Express API error patterns
"""

from typing import Any


class HerofyError(Exception):
    """Base exception for all Herofy errors."""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict matching Express error format."""
        return {
            "error": {
                "message": self.message,
                "code": self.code,
                "details": self.details,
            }
        }


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(HerofyError):
    """Database operation failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "DATABASE_ERROR", details)


class DatabaseNotConnectedError(DatabaseError):
    """Database pool not initialized."""

    def __init__(self, message: str = "Database not connected"):
        super().__init__(message)
        self.code = "DATABASE_NOT_CONNECTED"


class WorkspaceScopeError(DatabaseError):
    """Operation violates workspace isolation."""

    def __init__(self, message: str = "Cross-workspace operation not allowed"):
        super().__init__(message)
        self.code = "WORKSPACE_SCOPE_ERROR"


# =============================================================================
# Agent Errors
# =============================================================================


class AgentError(HerofyError):
    """Agent execution failed."""

    def __init__(
        self,
        message: str,
        code: str = "AGENT_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, code, details)


class StepFailedError(AgentError):
    """Agent step failed but may be recoverable."""

    def __init__(
        self,
        message: str,
        step_name: str,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["step"] = step_name
        super().__init__(message, "STEP_FAILED", error_details)
        self.step_name = step_name


class AgentTimeoutError(AgentError):
    """Agent exceeded execution time limit."""

    def __init__(self, message: str, timeout_seconds: float = 0):
        super().__init__(
            message, "AGENT_TIMEOUT", {"timeout_seconds": timeout_seconds}
        )


# =============================================================================
# Tool Errors
# =============================================================================


class ToolError(HerofyError):
    """Tool invocation failed."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["tool"] = tool_name
        super().__init__(message, "TOOL_ERROR", error_details)
        self.tool_name = tool_name


class NotionToolError(ToolError):
    """Notion API error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "notion", details)
        self.code = "NOTION_TOOL_ERROR"


# =============================================================================
# AI Service Errors
# =============================================================================


class AIServiceError(HerofyError):
    """AI/LLM service operation failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "AI_SERVICE_ERROR", details)


# =============================================================================
# Validation Errors
# =============================================================================


class ValidationError(HerofyError):
    """Input validation failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "VALIDATION_ERROR", details)


# =============================================================================
# Autonomous Agent Control Flow
# =============================================================================


class PauseForInputSignal(AgentError):
    """
    Special signal to pause agent execution and wait for human input.
    This is NOT an error - it's expected control flow for confidence-aware agents.
    """

    def __init__(
        self,
        need_id: str | None,  # May be None if no customer exists yet
        questions: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ):
        self.need_id = need_id
        self.questions = questions
        self.context = context or {}
        self.run_id = run_id
        message = f"Agent paused for input: {len(questions)} question(s)"
        super().__init__(message, "PAUSE_FOR_INPUT", {
            "need_id": need_id,
            "question_count": len(questions),
        })


class AgentResumeError(AgentError):
    """Failed to resume a paused agent run."""

    def __init__(self, message: str, run_id: str, details: dict[str, Any] | None = None):
        error_details = details or {}
        error_details["run_id"] = run_id
        super().__init__(message, "AGENT_RESUME_ERROR", error_details)
        self.run_id = run_id


class AgentNotPausedError(AgentError):
    """Attempted to resume an agent that is not paused."""

    def __init__(self, run_id: str, current_status: str):
        super().__init__(
            f"Agent run {run_id} is not paused (status: {current_status})",
            "AGENT_NOT_PAUSED",
            {"run_id": run_id, "current_status": current_status}
        )


class AgentAlreadyRunningError(AgentError):
    """Attempted to start an agent that is already running."""

    def __init__(self, workspace_id: str, agent_name: str):
        super().__init__(
            f"Agent {agent_name} already running for workspace",
            "AGENT_ALREADY_RUNNING",
            {"workspace_id": workspace_id, "agent_name": agent_name}
        )


# =============================================================================
# Integration Errors
# =============================================================================


class IntegrationError(HerofyError):
    """Integration operation failed."""

    def __init__(
        self,
        message: str,
        integration_type: str,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        error_details["integration_type"] = integration_type
        super().__init__(message, "INTEGRATION_ERROR", error_details)
        self.integration_type = integration_type


class IntegrationNotConfiguredError(IntegrationError):
    """Integration not set up for this workspace."""

    def __init__(self, workspace_id: str, integration_type: str):
        super().__init__(
            f"{integration_type} integration not configured",
            integration_type,
            {"workspace_id": workspace_id}
        )
        self.code = "INTEGRATION_NOT_CONFIGURED"


class IntegrationTokenExpiredError(IntegrationError):
    """OAuth token has expired and refresh failed."""

    def __init__(self, workspace_id: str, integration_type: str):
        super().__init__(
            f"{integration_type} token expired",
            integration_type,
            {"workspace_id": workspace_id}
        )
        self.code = "INTEGRATION_TOKEN_EXPIRED"


class IntegrationAuthError(IntegrationError):
    """
    Normalized auth failure across providers.

    Maps provider-specific auth errors (Slack 200 OK with error payload,
    Notion 401, Gmail 401) to a consistent exception type.
    """

    def __init__(
        self,
        message: str,
        provider: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, details)
        self.code = "INTEGRATION_AUTH_ERROR"
        self.provider = provider
