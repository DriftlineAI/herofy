"""
`memory_recall` — agent-managed retrieval: the agent decides WHEN to look
something up, so we never pre-load everything.

Hybrid: two complementary recall paths merged into one JSON response.
  1. Structured — targeted DataConnect lookups via the reused `AgentMemory` seam
     (past plans, similar customers, success/HITL patterns).
  2. Semantic   — Pinecone top-k vector search (text-embedding-004, 768-dim).
                  Activated when PINECONE_API_KEY is set; returns [] otherwise.
  → Merge → return JSON for the agent.

Tenant isolation: scope is always bounded to `workspace_id` (and `customer_id` when
the customer scope is requested). Never crosses the workspace boundary.
"""

import json
from typing import Any

from core.logging import get_logger

# Reused swappable memory seam from the working agent (read-only; never modified).
from agents.handoff_auto.memory import AgentMemory
from .pinecone_ingest import vector_recall_semantic

logger = get_logger("OrchestratorRecall")

_VALID_SCOPES = {"customer", "workspace"}


async def memory_recall(
    query: str,
    scope: str = "customer",
    *,
    workspace_id: str,
    customer_id: str | None = None,
) -> str:
    """Recall relevant memory as a JSON string.

    Args:
        query: what the agent is looking for (recorded; drives semantic search once wired).
        scope: "customer" (account history) or "workspace" (playbook/patterns).
        workspace_id: tenant boundary (required).
        customer_id: required when scope == "customer".
    """
    if scope not in _VALID_SCOPES:
        return json.dumps({"error": f"unknown scope '{scope}'", "valid": sorted(_VALID_SCOPES)})

    memory = AgentMemory(workspace_id)
    result: dict[str, Any] = {
        "query": query,
        "scope": scope,
        "semantic": await vector_recall_semantic(
            query, workspace_id, customer_id if scope == "customer" else None
        ),
        "structured": {},
    }

    try:
        if scope == "customer":
            if not customer_id:
                return json.dumps({"error": "customer scope requires customer_id"})
            result["structured"] = {
                "past_plans": await memory.recall_past_plans(customer_id=customer_id, limit=5),
                "similar_customers": await memory.recall_similar_customers(limit=3),
            }
        else:  # workspace
            result["structured"] = {
                "success_patterns": await memory.recall_success_patterns(),
                "hitl_patterns": await memory.recall_hitl_patterns(limit=10),
            }
    except Exception as e:
        logger.warning("memory_recall_failed", scope=scope, error=str(e))
        result["error"] = str(e)

    logger.info("memory_recall", scope=scope, customer_id=customer_id, query=query[:80])
    return json.dumps(result, default=str)
