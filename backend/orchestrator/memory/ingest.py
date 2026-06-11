"""
Memory consolidation write path — makes account memory compound after each event.

After a meaningful event (a completed play — NOT per message), `consolidate_account_memory`:
  1. EXTRACT  — gathers the event + the account's prior strategy memo & progress vectors.
  2. RECONCILE — a Flash `Consolidator` LlmAgent merges the event into existing memory
                 (reconciled memo + state updates for vectors the event actually moved).
  3. WRITE    — UPSERT the CustomerStrategy memo + UPDATE the affected ProgressVectors
                (also refreshes stale vector states). SQL is the source of truth.

Best-effort: wrapped by the caller so it never fails the task. Vector updates are guarded
to the account's real vector ids (LLM can't move a vector that wasn't provided). The vector
*index* (semantic recall) is deferred — this is the structured, SQL-truth half.
"""

import json
from typing import Any

from google.genai import types

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services import metric_snapshots

from ..runtime.runner import APP_NAME, build_runner, default_run_config
from ..runtime.services import get_session_service
from ..specialists.consolidator import build_consolidator, CONSOLIDATION_KEY

logger = get_logger("OrchestratorConsolidate")

STRATEGY_AUTHOR = "agent:orchestrator_consolidator"


def _parse(state_val: Any) -> dict | None:
    if state_val is None:
        return None
    if isinstance(state_val, str):
        try:
            return json.loads(state_val)
        except json.JSONDecodeError:
            return None
    if isinstance(state_val, dict):
        return state_val
    if hasattr(state_val, "model_dump"):
        return state_val.model_dump()
    return None


def _format_vectors(vectors: list[dict]) -> str:
    if not vectors:
        return "(none)"
    lines = []
    for v in vectors:
        goal = (v.get("goal") or {}).get("text", "")
        lines.append(
            f"- {v['id']} · {v.get('category')} · {v.get('currentState')} · "
            f"{(v.get('assessmentReason') or '').strip()[:80]}" + (f" (goal: {goal})" if goal else "")
        )
    return "\n".join(lines)


async def consolidate_account_memory(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    event_summary: str,
) -> dict:
    """Run the extract→reconcile→write loop for one account. Returns a small result dict.
    Safe to call best-effort; raises only if the caller wants to handle it."""
    dc = get_dataconnect_client()

    # 1. EXTRACT — prior memory.
    strat = (await dc.execute_query("GetCustomerStrategy", {"customerId": customer_id})).get("customerStrategies", [])
    prior_strategy = (strat[0]["body"] if strat else "") or "(none yet)"
    vectors = (await dc.execute_query("GetCustomerProgressVectors", {"customerId": customer_id})).get("progressVectors", [])
    known_vector_ids = {v["id"] for v in vectors}

    # 2. RECONCILE — run the Consolidator agent.
    agent = build_consolidator()
    session_service = get_session_service()
    session = await session_service.create_session(
        app_name=APP_NAME, user_id=workspace_id,
        state={
            "customer_name": customer_name,
            "event_summary": event_summary,
            "prior_strategy": prior_strategy,
            "current_vectors": _format_vectors(vectors),
        },
    )
    runner = build_runner(agent)
    msg = types.Content(role="user", parts=[types.Part(text=f"Consolidate memory for {customer_name}.")])
    async for _e in runner.run_async(user_id=workspace_id, session_id=session.id,
                                     new_message=msg, run_config=default_run_config()):
        pass
    final = await session_service.get_session(app_name=APP_NAME, user_id=workspace_id, session_id=session.id)
    out = _parse((final.state if final else session.state).get(CONSOLIDATION_KEY))
    if not out:
        logger.warning("consolidation_no_output", customer_id=customer_id)
        return {"updated": False}

    # 3. WRITE — strategy memo + the vectors that actually moved (guarded to real ids).
    # Check-then-write: UpdateCustomerStrategy if one exists, else insert with a new id.
    # (DataConnect upsert requires the key, so it can't create a fresh row.)
    body = (out.get("strategy_body") or "").strip()
    if body:
        if strat:
            await dc.execute_mutation("UpdateCustomerStrategy", {
                "id": strat[0]["id"], "body": body, "lastUpdatedBy": STRATEGY_AUTHOR,
            })
        else:
            import uuid
            await dc.execute_mutation("CreateCustomerStrategyWithId", {
                "id": str(uuid.uuid4()), "workspaceId": workspace_id, "customerId": customer_id,
                "body": body, "lastUpdatedBy": STRATEGY_AUTHOR,
            })
    # prior state per vector id, captured before the updates so the snapshot
    # rows can record where each vector moved FROM.
    vector_by_id = {v["id"]: v for v in vectors}
    updated_vectors = 0
    for upd in (out.get("vector_updates") or []):
        vid = upd.get("vector_id")
        if vid not in known_vector_ids:
            logger.info("consolidation_skip_unknown_vector", vector_id=vid)  # LLM hallucination guard
            continue
        new_state = upd.get("new_state")
        await dc.execute_mutation("UpdateProgressVector", {
            "id": vid,
            "currentState": new_state,
            "assessmentReason": upd.get("reason"),
            "lastAssessedBy": STRATEGY_AUTHOR,
        })

        # Append-on-change: persist the vector's state trajectory (best-effort;
        # never raises, no-op when the metric-snapshots flag is off).
        prior = vector_by_id.get(vid, {})
        category = prior.get("category") or "unknown"  # `or` guards a null category column
        await metric_snapshots.append_snapshot(
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric=f"vector_{category}",
            state=new_state,
            trigger="assessment",
            inputs={
                "vector_id": vid,
                "prior_state": prior.get("currentState"),
                "category": category,
                "assessment_reason": upd.get("reason"),
                "assessed_by": STRATEGY_AUTHOR,
            },
        )
        updated_vectors += 1

    logger.info("consolidation_written", customer_id=customer_id,
                strategy_written=bool(body), vectors_updated=updated_vectors,
                digest=(out.get("digest") or "")[:120])

    # Pinecone — embed updated account memory for semantic recall.
    # Best-effort: SQL is already committed above; we never re-raise here.
    if body:
        try:
            from .pinecone_ingest import ingest_account_memory
            hb = (await dc.execute_query(
                "GetLatestHandoffBriefForCustomer", {"customerId": customer_id}
            )).get("handoffBriefs", [])
            ia_raw = (await dc.execute_query(
                "GetCustomerInteractions",
                {"workspaceId": workspace_id, "customerId": customer_id, "limit": 10},
            )).get("interactions", [])
            ia = [i for i in ia_raw if i.get("summaryAi")]
            rb = (await dc.execute_query(
                "GetRiskBriefsForCustomer",
                {"workspaceId": workspace_id, "customerId": customer_id},
            )).get("riskBriefs", [])
            await ingest_account_memory(
                workspace_id=workspace_id,
                customer_id=customer_id,
                strategy_body=body,
                event_summary=event_summary,
                handoff_briefs=hb,
                interactions=ia,
                risk_briefs=rb,
            )
        except Exception as e:
            logger.warning("pinecone_ingest_error", customer_id=customer_id, error=str(e))

    return {"updated": True, "strategy_written": bool(body), "vectors_updated": updated_vectors}
