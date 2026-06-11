"""
Researcher specialist — read-only context gathering (reused by every play).

An `LlmAgent` with the reused read tools (customer info + hybrid memory_recall),
bound to a specific account via closures. Its summary lands in session state under
`research_summary` for downstream stages to template into their prompts.

Grounding stack (ordered by signal density):
  1. get_customer_info  — structured DB snapshot (lifecycle, goals, signals, renewal)
  2. recall             — hybrid memory: structured past plans + Pinecone semantic RAG
  3. google_search      — live Google Search grounding (ADK GoogleSearchTool with
                          bypass_multi_tools_limit so it composes with the function tools)
  4. Notion MCP         — customer-linked docs/notes via mcp.notion.com (notion_mcp OAuth) or the
                          @notionhq/notion-mcp-server stdio dev fallback; graceful no-op otherwise
"""

import asyncio
import json

from google.adk.agents import LlmAgent
from google.adk.tools.google_search_agent_tool import (
    GoogleSearchAgentTool,
    create_google_search_agent,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

from config import settings
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase

# Reused read-only callables (import, never modify handoff_auto).
from agents.handoff_auto.tools.context import get_customer_info as _get_customer_info

from ..memory.recall import memory_recall as _memory_recall
from ..runtime.callbacks import langfuse_model_cb, stream_tool_output

logger = get_logger("Researcher")

RESEARCH_KEY = "research_summary"

NOTION_MCP_URL = "https://mcp.notion.com/mcp"   # StreamableHTTP (recommended transport)
NOTION_MCP_SSE_URL = "https://mcp.notion.com/sse"  # SSE fallback per Notion's MCP-client guide


def _is_real_cancel() -> bool:
    """True only when OUR task was genuinely asked to cancel (vs. a CancelledError
    leaking out of the MCP client's internal anyio cancel scope on a failed session)."""
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


class _SafeMcpToolset(McpToolset):
    """An McpToolset that (a) optionally falls back to a secondary transport and
    (b) degrades to NO tools if the MCP session can't be established — e.g. an
    expired/revoked OAuth token (401), a network error, or a startup timeout. An
    optional enrichment tool must never crash the agent run; on failure the
    researcher simply proceeds without it.

    `fallback_params`: a second connection (e.g. SSE) tried once if the primary
    transport (e.g. StreamableHTTP) fails — honoring Notion's "try Streamable HTTP
    first, fall back to SSE" guidance. `auth_failed` is left set as a breadcrumb for
    a future HITL "re-authorize" pause (see project-hitl-reauth memory)."""

    def __init__(self, *args, fallback_params=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fallback_params = fallback_params
        self.auth_failed = False

    async def get_tools(self, readonly_context=None):
        try:
            return await super().get_tools(readonly_context)
        except BaseException as e:  # noqa: BLE001 — a sub-agent tool must never crash the run
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            # The MCP streamable-http client leaks a CancelledError out of its internal
            # anyio cancel scope when session init fails. Re-raise only a genuine cancel.
            if isinstance(e, asyncio.CancelledError) and _is_real_cancel():
                raise
            # Primary transport failed — try the fallback (SSE) once before degrading.
            if self._fallback_params is not None:
                try:
                    fb = McpToolset(connection_params=self._fallback_params)
                    return await fb.get_tools(readonly_context)
                except BaseException as e2:  # noqa: BLE001
                    if isinstance(e2, (KeyboardInterrupt, SystemExit)):
                        raise
                    if isinstance(e2, asyncio.CancelledError) and _is_real_cancel():
                        raise
            self.auth_failed = True
            logger.warning("notion_mcp_unavailable", error=repr(e)[:200])
            return []


class _SafeGoogleSearchAgentTool(GoogleSearchAgentTool):
    """ADK's GoogleSearchAgentTool.run_async joins `last_content.parts` without guarding
    `parts is None` (google_search_agent_tool.py:128). When google_search finds nothing for a
    query, Gemini returns a candidate with finish_reason=STOP but `content.parts = None` (empty
    answer) — common here because the seeded demo customers (e.g. "Bevelpoint Logistics") are
    fictional names with no web presence. That raises 'NoneType' object is not iterable and kills
    the run. We degrade to empty text instead — a parts-less response has no text to extract anyway.
    TODO(ADK b/448114567): drop once upstream guards it."""

    async def run_async(self, *, args, tool_context):
        try:
            return await super().run_async(args=args, tool_context=tool_context)
        except BaseException as e:  # noqa: BLE001 — optional web grounding must never crash the run
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(e, asyncio.CancelledError) and _is_real_cancel():
                raise
            logger.warning("google_search_empty_or_failed", error=repr(e)[:160])
            return ""

_INSTRUCTION = (
    "You are the Researcher. Investigate this customer's current situation "
    "using your tools.\n\n"
    "1. get_customer_info — call first for lifecycle, goals, signals, "
    "commitments, stakeholders, and renewal data.\n"
    "2. recall(query) — call for relevant account history and past patterns. "
    "Use a query that captures the current risk or change you're investigating.\n"
    "3. google_search — search for recent public news about the company "
    "(funding rounds, leadership changes, layoffs, product launches) that "
    "could explain engagement drops or risk signals.\n"
    "4. Notion tools (if available) — search for customer-related docs, "
    "meeting notes, or project pages linked to this account. Use read-only "
    "operations only.\n\n"
    "Then write a TIGHT briefing (<=150 words) covering: the customer's "
    "goal/north star, what has changed recently (engagement, sentiment, "
    "stakeholders, usage), how close is renewal, and the 2-3 hardest risks. "
    "Be concrete and quote evidence. This briefing is the only context "
    "downstream stages get — make it count."
)


def _build_notion_toolset(notion_token: str | None) -> McpToolset | None:
    """Return a Notion MCP toolset, or None if Notion is not configured.

    Primary path — StreamableHTTP with the workspace's hosted-MCP OAuth token:
        Uses mcp.notion.com (Notion's hosted MCP server). `notion_token` MUST be a
        token from the MCP-specific OAuth flow (IntegrationType `notion_mcp`) — the
        REST API token is rejected here with 401. Falls back to SSE transport on a
        transport failure (auth failures degrade gracefully — see _SafeMcpToolset).

    Dev fallback — stdio with an internal integration token:
        If no per-workspace OAuth token is available but NOTION_API_KEY is set
        in settings, falls back to the @notionhq/notion-mcp-server npm package
        (pre-installed in the Docker image) as a stdio subprocess. This uses
        Notion's deprecated v1 JSON APIs; acceptable for local dev only.
    """
    if notion_token:
        bearer = {"Authorization": f"Bearer {notion_token}"}
        return _SafeMcpToolset(
            connection_params=StreamableHTTPConnectionParams(url=NOTION_MCP_URL, headers=bearer),
            fallback_params=SseConnectionParams(url=NOTION_MCP_SSE_URL, headers=bearer),
        )
    if settings.notion_api_key:
        # Dev fallback: internal integration token via stdio subprocess.
        return _SafeMcpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["@notionhq/notion-mcp-server"],
                    env={"NOTION_API_KEY": settings.notion_api_key},
                ),
                timeout=30.0,
            ),
        )
    return None


def build_researcher(
    workspace_id: str,
    customer_id: str,
    notion_token: str | None = None,
    after_agent_callback=None,
) -> LlmAgent:
    """Researcher bound to one account. Investigates, then summarizes."""

    async def get_customer_info() -> str:
        """Full current picture of the customer (lifecycle, goals, signals,
        commitments, stakeholders, renewal)."""
        return json.dumps(await _get_customer_info(customer_id, workspace_id), default=str)

    async def recall(query: str) -> str:
        """Recall relevant customer history (past plans, similar accounts,
        semantically similar past events via vector search)."""
        return await _memory_recall(query, "customer", workspace_id=workspace_id, customer_id=customer_id)

    # Gemini forbids combining the BUILT-IN google_search tool with function-calling tools in one
    # request. ADK's workaround is to run google_search in its own sub-agent exposed as an
    # AgentTool (GoogleSearchAgentTool), so the researcher's request stays function-calling-only.
    # We supply our crash-hardened subclass directly (instead of GoogleSearchTool(
    # bypass_multi_tools_limit=True), whose auto-created wrapper crashes on an empty grounding
    # result — see _SafeGoogleSearchAgentTool). See https://adk.dev/tools/limitations/.
    tools: list = [
        get_customer_info,
        recall,
        _SafeGoogleSearchAgentTool(create_google_search_agent(get_model(ModelUseCase.SIGNAL_ANALYSIS))),
    ]

    notion_toolset = _build_notion_toolset(notion_token)
    if notion_toolset is not None:
        tools.append(notion_toolset)

    return LlmAgent(
        name="researcher",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=_INSTRUCTION,
        tools=tools,
        output_key=RESEARCH_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
        after_tool_callback=stream_tool_output,
    )
