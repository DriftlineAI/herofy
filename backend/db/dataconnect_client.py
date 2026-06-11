"""
Firebase Data Connect GraphQL Client

HTTP client for Firebase Data Connect that:
- Auto-detects emulator (dev) vs production endpoints
- Reuses GraphQL operations from dataconnect/example/*.gql files
- Provides helper methods for common operations

Usage:
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()
    customer = await dc.execute_query("GetCustomer", {"id": customer_id})

────────────────────────────────────────────────────────────────────────────
SECURITY / @auth NOTE (see docs/plans/SECURITY_RBAC_HARDENING.md)

This client calls the `services/{service}:executeGraphql` **admin/management surface**
(not the `connectors/{connector}:executeMutation` *client* surface) and authenticates
with a Google service-account ADC token (`cloud-platform` scope). Per Firebase, the admin
surface runs with elevated privileges and **bypasses `@auth` directives entirely, including
`@auth(level: NO_ACCESS)`**. The client connector surface — used by the frontend SDK with a
Firebase Auth ID token — is the one that enforces `@auth`.

Consequence for RBAC hardening: backend-only operations may (and should) be declared
`@auth(level: NO_ACCESS)` to make them un-callable from any browser client; this backend keeps
working because it runs on the admin surface. The local DataConnect emulator ignores `@auth`
altogether, so `@auth`-level changes only take effect against the deployed service. RBAC for
the *frontend* therefore lives in the operation `@auth` levels + in-operation `@check`
membership lookups (USER-tier ops) and in the Python `/api/*` routes that wrap privileged calls.

Prereq: the production service account must hold the Data Connect admin IAM permission
(`firebasedataconnect.services.executeGraphql`).
────────────────────────────────────────────────────────────────────────────
"""

import re
import contextvars
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
import google.auth
from google.auth.transport.requests import Request

from config import get_settings
from core.errors import DatabaseError, DatabaseNotConnectedError
from core.logging import get_logger

logger = get_logger("DataConnectClient")

# Global client instance
_client: "DataConnectClient | None" = None

# When set (via DataConnectClient.impersonate), admin-surface calls run AS this end-user uid: the
# request carries `extensions.impersonate.authClaims.sub`, so `auth.uid` resolves and any
# @auth/@check CEL referencing it evaluates — instead of throwing ("the admin request does not
# impersonate an end user") on the un-impersonated admin request. Per-async-context (a ContextVar),
# so concurrent requests don't collide.
_impersonate_uid: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "dc_impersonate_uid", default=None
)


def set_context_impersonation(uid: str | None) -> None:
    """Set the impersonation uid for the CURRENT async context (e.g. a request task) without a
    reset — each request runs in its own context copy. The auth dependency calls this so every
    admin-surface @check(auth.uid) op in a request runs as the authenticated user. Background tasks
    have no request user and use DataConnectClient.impersonate_workspace_owner instead."""
    _impersonate_uid.set(uid)


class DataConnectClient:
    """
    GraphQL client for Firebase Data Connect.

    Connects to either the local emulator (development) or
    Firebase Data Connect production service (production).
    """

    def __init__(self):
        self.settings = get_settings()
        self._http_client: httpx.AsyncClient | None = None
        self._operations: dict[str, str] = {}
        self._base_url: str = ""
        self._is_emulator: bool = False
        self._credentials: google.auth.credentials.Credentials | None = None

    async def connect(self) -> None:
        """Initialize HTTP client and load operations."""
        if self._http_client is not None:
            return

        # Determine endpoint based on emulator flag
        if self.settings.use_dataconnect_emulator:
            self._is_emulator = True
            host = self.settings.dataconnect_emulator_host
            port = self.settings.dataconnect_emulator_port
            project = self.settings.firebase_project_id
            location = self.settings.dataconnect_location
            service = self.settings.dataconnect_service

            # Emulator GraphQL endpoint
            self._base_url = (
                f"http://{host}:{port}/v1beta/"
                f"projects/{project}/locations/{location}/services/{service}"
            )
            logger.info(
                "dataconnect_emulator_mode",
                url=self._base_url,
            )
        else:
            self._is_emulator = False
            project = self.settings.firebase_project_id
            location = self.settings.dataconnect_location
            service = self.settings.dataconnect_service

            # Production Firebase Data Connect endpoint
            self._base_url = (
                f"https://firebasedataconnect.googleapis.com/v1beta/"
                f"projects/{project}/locations/{location}/services/{service}"
            )

            # Get Application Default Credentials for production
            try:
                self._credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                logger.info("dataconnect_credentials_loaded", type=type(self._credentials).__name__)
            except google.auth.exceptions.DefaultCredentialsError as e:
                logger.error("dataconnect_credentials_error", error=str(e))
                raise DatabaseError(
                    "Failed to load Google credentials. Run: gcloud auth application-default login"
                )

            logger.info(
                "dataconnect_production_mode",
                url=self._base_url,
            )

        # Create HTTP client with connection pooling
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        # Load GraphQL operations from .gql files
        self._operations = self._load_operations()
        logger.info(
            "dataconnect_operations_loaded",
            count=len(self._operations),
        )

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("dataconnect_disconnected")

    def _load_operations(self) -> dict[str, str]:
        """
        Load GraphQL operations from .gql files.

        Returns dict mapping operation name to full GraphQL text.
        """
        operations: dict[str, str] = {}

        # Find the dataconnect directory. Two layouts are supported:
        #   - Local dev: repo/backend/db/... and repo/dataconnect/example/...
        #   - Container: /app/db/... and /app/dataconnect/example/... (Dockerfile bundles it)
        backend_dir = Path(__file__).parent.parent
        candidate_dirs = [
            backend_dir / "dataconnect" / "example",
            backend_dir.parent / "dataconnect" / "example",
        ]
        gql_dir = next((p for p in candidate_dirs if p.exists()), None)

        if gql_dir is None:
            logger.warning(
                "dataconnect_gql_dir_not_found",
                searched=[str(p) for p in candidate_dirs],
            )
            return operations

        # Parse queries.gql and mutations.gql
        for filename in ["queries.gql", "mutations.gql"]:
            filepath = gql_dir / filename
            if filepath.exists():
                file_ops = self._parse_gql_file(filepath)
                operations.update(file_ops)
                logger.debug(
                    "dataconnect_file_parsed",
                    file=filename,
                    operations=len(file_ops),
                )

        return operations

    def _parse_gql_file(self, filepath: Path) -> dict[str, str]:
        """
        Parse a .gql file and extract named operations.

        Returns dict mapping operation name to GraphQL text.
        """
        content = filepath.read_text()
        operations: dict[str, str] = {}

        # Pattern to match query/mutation blocks with their full body
        # This handles nested braces by counting brace depth
        pattern = r'(query|mutation)\s+(\w+)'

        for match in re.finditer(pattern, content):
            op_type = match.group(1)
            op_name = match.group(2)
            start_pos = match.start()

            # Find the opening brace
            brace_pos = content.find("{", start_pos)
            if brace_pos == -1:
                continue

            # Count braces to find matching closing brace
            depth = 0
            end_pos = brace_pos
            for i, char in enumerate(content[brace_pos:], start=brace_pos):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break

            # Extract full operation text
            op_text = content[start_pos:end_pos].strip()
            operations[op_name] = op_text

        return operations

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for requests."""
        headers = {
            "Content-Type": "application/json",
        }

        # In production, add OAuth access token from ADC
        if not self._is_emulator and self._credentials:
            # Refresh credentials if expired
            if not self._credentials.valid:
                self._credentials.refresh(Request())

            # Add access token to Authorization header
            headers["Authorization"] = f"Bearer {self._credentials.token}"

        return headers

    @contextmanager
    def impersonate(self, uid: str | None):
        """Run enclosed admin-surface operations AS end-user `uid`.

        The admin executeGraphql surface has no `auth.uid`, so any @auth/@check CEL that reads it
        throws. Wrapping calls in `with dc.impersonate(member_uid):` attaches
        `extensions.impersonate.authClaims.sub`, so membership @check gates on seed/write ops
        evaluate against a real member. Pass a uid that is actually a member of the target
        workspace, otherwise the @check correctly fails.
        """
        token = _impersonate_uid.set(uid)
        try:
            yield
        finally:
            _impersonate_uid.reset(token)

    @asynccontextmanager
    async def impersonate_workspace_owner(self, workspace_id: str):
        """Impersonate a member (owner) of `workspace_id` for enclosed admin-surface calls — for
        backend code with no request user (queue drains, sweeps, webhooks, agents). Resolves a
        member via GetWorkspaceMembers (USER-level, no auth.uid → runs on pure admin) so the
        @check(auth.uid) ops in plays/sweeps pass. Falls back to pure admin if no member is found
        (gated ops then fail loudly rather than mis-writing)."""
        uid = await self._resolve_workspace_owner(workspace_id)
        if uid is None:
            logger.warning("impersonation_owner_unresolved", workspace_id=workspace_id)
        with self.impersonate(uid):
            yield uid

    async def _resolve_workspace_owner(self, workspace_id: str) -> str | None:
        try:
            data = await self.execute_query("GetWorkspaceMembers", {"workspaceId": workspace_id})
        except Exception as e:  # noqa: BLE001 - best-effort resolution
            logger.warning("resolve_workspace_owner_failed", workspace_id=workspace_id, error=str(e))
            return None
        members = data.get("workspaceMembers") or []
        if not members:
            return None
        owner = next((m for m in members if m.get("role") == "owner"), members[0])
        return (owner.get("user") or {}).get("id")

    async def execute_query(
        self,
        operation_name: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL query operation.

        Args:
            operation_name: Name of the query (e.g., "GetCustomer")
            variables: Variables to pass to the query

        Returns:
            Query result data

        Raises:
            DatabaseError: If query fails
        """
        if not self._http_client:
            raise DatabaseNotConnectedError("DataConnect client not initialized")

        query = self._get_operation(operation_name)

        payload = {
            "query": query,
            "variables": variables or {},
            "operationName": operation_name,
        }
        # Impersonate ONLY ops whose CEL references auth.uid (the @check-gated ones). NO_ACCESS ops
        # carry no auth.uid and must stay PURE admin — impersonating them makes the service reject
        # the call as a non-admin request. (Strip comments so a stray "auth.uid" mention can't
        # mis-trigger.) Short-circuits on _imp, so normal app traffic skips the regex.
        _imp = _impersonate_uid.get()
        if _imp and "auth.uid" in re.sub(r"#.*", "", query):
            payload["extensions"] = {"impersonate": {"authClaims": {"sub": _imp}}}

        try:
            response = await self._http_client.post(
                f"{self._base_url}:executeGraphql",
                json=payload,
                headers=self._get_headers(),
            )

            if response.status_code != 200:
                logger.error(
                    "dataconnect_query_http_error",
                    operation=operation_name,
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise DatabaseError(
                    f"DataConnect query failed: HTTP {response.status_code}"
                )

            result = response.json()

            if "errors" in result and result["errors"]:
                errors = result["errors"]
                logger.error(
                    "dataconnect_query_graphql_error",
                    operation=operation_name,
                    errors=errors,
                )
                raise DatabaseError(
                    f"GraphQL query error: {errors[0].get('message', 'Unknown error')}"
                )

            return result.get("data", {})

        except httpx.TimeoutException as e:
            logger.error(
                "dataconnect_query_timeout",
                operation=operation_name,
                error=str(e),
            )
            raise DatabaseError(f"DataConnect query timeout: {operation_name}")
        except httpx.RequestError as e:
            logger.error(
                "dataconnect_query_request_error",
                operation=operation_name,
                error=str(e),
            )
            raise DatabaseError(f"DataConnect request error: {e}")

    async def execute_mutation(
        self,
        operation_name: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL mutation operation.

        Args:
            operation_name: Name of the mutation (e.g., "CreateCustomer")
            variables: Variables to pass to the mutation

        Returns:
            Mutation result data

        Raises:
            DatabaseError: If mutation fails
        """
        if not self._http_client:
            raise DatabaseNotConnectedError("DataConnect client not initialized")

        mutation = self._get_operation(operation_name)

        payload = {
            "query": mutation,
            "variables": variables or {},
            "operationName": operation_name,
        }
        # Impersonate ONLY ops whose CEL references auth.uid (the @check-gated ones). NO_ACCESS ops
        # carry no auth.uid and must stay PURE admin — impersonating them makes the service reject
        # the call as a non-admin request. (Strip comments so a stray "auth.uid" mention can't
        # mis-trigger.) Short-circuits on _imp, so normal app traffic skips the regex.
        _imp = _impersonate_uid.get()
        if _imp and "auth.uid" in re.sub(r"#.*", "", mutation):
            payload["extensions"] = {"impersonate": {"authClaims": {"sub": _imp}}}

        try:
            response = await self._http_client.post(
                f"{self._base_url}:executeGraphql",
                json=payload,
                headers=self._get_headers(),
            )

            if response.status_code != 200:
                logger.error(
                    "dataconnect_mutation_http_error",
                    operation=operation_name,
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise DatabaseError(
                    f"DataConnect mutation failed: HTTP {response.status_code}"
                )

            result = response.json()

            if "errors" in result and result["errors"]:
                errors = result["errors"]
                logger.error(
                    "dataconnect_mutation_graphql_error",
                    operation=operation_name,
                    errors=errors,
                )
                raise DatabaseError(
                    f"GraphQL mutation error: {errors[0].get('message', 'Unknown error')}"
                )

            return result.get("data", {})

        except httpx.TimeoutException as e:
            logger.error(
                "dataconnect_mutation_timeout",
                operation=operation_name,
                error=str(e),
            )
            raise DatabaseError(f"DataConnect mutation timeout: {operation_name}")
        except httpx.RequestError as e:
            logger.error(
                "dataconnect_mutation_request_error",
                operation=operation_name,
                error=str(e),
            )
            raise DatabaseError(f"DataConnect request error: {e}")

    def _get_operation(self, name: str) -> str:
        """Get GraphQL operation by name."""
        if name not in self._operations:
            raise DatabaseError(f"GraphQL operation not found: {name}")
        return self._operations[name]

    def has_operation(self, name: str) -> bool:
        """Check if an operation exists."""
        return name in self._operations

    def list_operations(self) -> list[str]:
        """List all available operation names."""
        return list(self._operations.keys())

    # =========================================================================
    # Convenience Methods for Common Operations
    # =========================================================================

    async def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Get a customer by ID."""
        result = await self.execute_query("GetCustomerPublic", {"id": customer_id})
        return result.get("customer")

    async def get_customers(self, workspace_id: str) -> list[dict[str, Any]]:
        """Get all customers for a workspace."""
        result = await self.execute_query(
            "GetCustomersPublic",
            {"workspaceId": workspace_id},
        )
        return result.get("customers", [])

    async def create_customer(
        self,
        workspace_id: str,
        name: str,
        slug: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new customer."""
        variables = {
            "workspaceId": workspace_id,
            "name": name,
            "slug": slug,
            **kwargs,
        }
        result = await self.execute_mutation("CreateCustomer", variables)
        return result.get("customer_insert", {})

    async def update_customer(
        self,
        customer_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a customer."""
        variables = {"id": customer_id, **kwargs}
        result = await self.execute_mutation("UpdateCustomer", variables)
        return result.get("customer_update", {})

    async def get_workspace_integrations(
        self,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        """Get all integrations for a workspace."""
        # Note: Need to add GetWorkspaceIntegrations query to queries.gql
        result = await self.execute_query(
            "GetWorkspaceIntegrations",
            {"workspaceId": workspace_id},
        )
        return result.get("workspaceIntegrations", [])

    async def get_playbooks(self, workspace_id: str) -> list[dict[str, Any]]:
        """Get all playbooks for a workspace."""
        result = await self.execute_query("GetPlaybooks", {"workspaceId": workspace_id})
        return result.get("playbooks", [])

    async def get_handbook(self, workspace_id: str) -> list[dict[str, Any]]:
        """Get handbook docs for a workspace."""
        result = await self.execute_query("GetHandbook", {"workspaceId": workspace_id})
        return result.get("handbookDocs", [])

    # =========================================================================
    # Agent Run Operations
    # =========================================================================

    async def create_agent_run(
        self,
        workspace_id: str,
        agent_name: str,
        trigger_type: str | None = None,
        triggered_by: str | None = None,
        input_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new agent run."""
        import json
        result = await self.execute_mutation(
            "CreateAgentRun",
            {
                "workspaceId": workspace_id,
                "agentName": agent_name,
                "triggerType": trigger_type,
                "triggeredBy": triggered_by,
                "inputParams": json.dumps(input_params) if input_params else "{}",
            },
        )
        return result.get("agentRun_insert", {})

    async def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        """Get an agent run by ID."""
        result = await self.execute_query("GetAgentRunPublic", {"id": run_id})
        return result.get("agentRun")

    async def start_agent_run(self, run_id: str) -> dict[str, Any]:
        """Start an agent run (transition to running)."""
        result = await self.execute_mutation("StartAgentRun", {"id": run_id})
        return result.get("agentRun_update", {})

    async def update_agent_run_step(
        self,
        run_id: str,
        step_name: str,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the current step of an agent run."""
        import json
        result = await self.execute_mutation(
            "UpdateAgentRunStep",
            {
                "id": run_id,
                "currentStep": step_name,
                "contextSnapshot": json.dumps(context_snapshot) if context_snapshot else None,
            },
        )
        return result.get("agentRun_update", {})

    async def pause_agent_run(
        self,
        run_id: str,
        pause_reason: str,
        confidence_level: str | None = None,
        confidence_score: float | None = None,
        confidence_reasons: list[str] | None = None,
        clarifying_questions: list[dict[str, Any]] | None = None,
        blocking_need_id: str | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pause an agent run for human input."""
        import json
        result = await self.execute_mutation(
            "PauseAgentRun",
            {
                "id": run_id,
                "pauseReason": pause_reason,
                "confidenceLevel": confidence_level,
                "confidenceScore": confidence_score,
                "confidenceReasons": json.dumps(confidence_reasons) if confidence_reasons else None,
                "clarifyingQuestions": json.dumps(clarifying_questions) if clarifying_questions else None,
                "blockingNeedId": blocking_need_id,
                "contextSnapshot": json.dumps(context_snapshot) if context_snapshot else None,
            },
        )
        return result.get("agentRun_update", {})

    async def resume_agent_run(self, run_id: str, answers: dict[str, Any]) -> dict[str, Any]:
        """Resume an agent run with answers."""
        import json
        result = await self.execute_mutation(
            "ResumeAgentRun",
            {
                "id": run_id,
                "resumeAnswers": json.dumps(answers),
            },
        )
        return result.get("agentRun_update", {})

    async def mark_agent_run_running(self, run_id: str) -> dict[str, Any]:
        """Transition agent run back to running after resume."""
        result = await self.execute_mutation("MarkAgentRunRunning", {"id": run_id})
        return result.get("agentRun_update", {})

    async def complete_agent_run(
        self,
        run_id: str,
        result_data: dict[str, Any] | None = None,
        customer_id: str | None = None,
        brief_id: str | None = None,
        plan_id: str | None = None,
        used_fallback: bool = False,
        fallback_reason: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        """Complete an agent run successfully."""
        import json
        result = await self.execute_mutation(
            "CompleteAgentRun",
            {
                "id": run_id,
                "result": json.dumps(result_data) if result_data else None,
                "customerId": customer_id,
                "briefId": brief_id,
                "planId": plan_id,
                "usedFallback": used_fallback,
                "fallbackReason": fallback_reason,
                "durationMs": duration_ms,
            },
        )
        return result.get("agentRun_update", {})

    async def fail_agent_run(
        self,
        run_id: str,
        error_message: str,
        context_snapshot: dict[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        """Mark an agent run as failed."""
        import json
        result = await self.execute_mutation(
            "FailAgentRun",
            {
                "id": run_id,
                "errorMessage": error_message,
                "contextSnapshot": json.dumps(context_snapshot) if context_snapshot else None,
                "durationMs": duration_ms,
            },
        )
        return result.get("agentRun_update", {})

    async def get_active_agent_run(
        self,
        workspace_id: str,
        agent_name: str,
    ) -> dict[str, Any] | None:
        """Get the active (non-terminal) run for an agent."""
        result = await self.execute_query(
            "GetActiveAgentRun",
            {"workspaceId": workspace_id, "agentName": agent_name},
        )
        runs = result.get("agentRuns", [])
        return runs[0] if runs else None

    async def get_waiting_runs(
        self,
        workspace_id: str,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get agent runs waiting for input."""
        result = await self.execute_query(
            "GetWaitingRunsPublic",
            {"workspaceId": workspace_id, "agentName": agent_name},
        )
        return result.get("agentRuns", [])

    # =========================================================================
    # Today Queue Operations
    # =========================================================================

    async def get_today_queue(self, workspace_id: str) -> list[dict[str, Any]]:
        """Get the Today queue items for a workspace (unresolved, unsnoozed needs)."""
        result = await self.execute_query(
            "GetTodayQueue",
            {"workspaceId": workspace_id},
        )
        return result.get("needs", [])


# =========================================================================
# Global Client Access (matches DatabaseClient pattern)
# =========================================================================


async def init_dataconnect_client() -> DataConnectClient:
    """Initialize the global DataConnect client."""
    global _client
    _client = DataConnectClient()
    await _client.connect()
    return _client


async def close_dataconnect_client() -> None:
    """Close the global DataConnect client."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None


def get_dataconnect_client() -> DataConnectClient:
    """Get the global DataConnect client instance."""
    if not _client:
        raise DatabaseNotConnectedError("DataConnect client not initialized")
    return _client
