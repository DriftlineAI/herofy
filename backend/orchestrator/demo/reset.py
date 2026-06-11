"""Demo workspace teardown — wipes everything the seed creates, FK-safe.

Workspace-scoped (not per-customer like routes/orchestrator._reset_demo), because the
seed owns the whole workspace's contents. Intended for throwaway demo workspaces:
re-running the seed calls this first so deterministic ids never collide.

⚠️ This deletes ALL customers, threads, needs, meetings, goals, etc. in the target
workspace. The route guards it; never point it at a real workspace.

The delete order is children-before-parents. The Thread↔Need cycle is broken by
deleting threads before needs (matching routes/orchestrator._reset_demo, which relies
on the same delete-time FK behavior).

Note: the *ByWorkspace mutations are loaded from mutations.gql at client connect(), so
a backend restart is required after adding them before this will find them. Each delete
is best-effort: a missing op or empty table is logged and skipped, never fatal.
"""

from core.logging import get_logger
from db.dataconnect_client import DataConnectClient, get_dataconnect_client

logger = get_logger("DemoReset")

# Children → parents. Each entry is a mutation taking a single $workspaceId.
_DELETE_ORDER: list[str] = [
    "DeleteDraftResponsesByWorkspace",     # → Need, Thread
    "DeleteRiskPlayStepsByWorkspace",      # → RiskBrief
    "DeleteRiskBriefsByWorkspace",
    "DeleteSidekickObservationsByWorkspace",
    "DeleteAgentTasksByWorkspace",
    "DeleteMeetingBriefsByWorkspace",      # → Meeting
    "DeleteInteractionsByWorkspace",       # → Thread
    "DeleteMeetingsByWorkspace",
    "DeleteThreadsByWorkspace",            # → Need (delete threads first; see module note)
    "DeleteNeedsByWorkspace",
    "DeleteAiPlansByWorkspace",            # → HandoffBrief
    "DeleteHandoffBriefsByWorkspace",
    "DeleteMilestonesByWorkspace",         # → Goal
    "DeleteGoalsByWorkspace",
    "DeleteStakeholdersByWorkspace",
    "DeleteSignalsByWorkspace",
    "DeleteAllCustomersForWorkspacePublic",
    # workspace defaults last (their children first)
    "DeletePlaybookMilestonesByWorkspace",
    "DeletePlaybooksByWorkspace",
    "DeleteHandbookVersionsByWorkspace",
    "DeleteHandbookDocsByWorkspace",
]


async def reset_workspace(workspace_id: str) -> dict[str, int]:
    """Delete all seedable rows in `workspace_id`. Returns per-step error counts."""
    dc: DataConnectClient = get_dataconnect_client()
    errors = 0
    for op in _DELETE_ORDER:
        if not dc.has_operation(op):
            logger.warning("demo_reset_op_missing", op=op,
                           hint="restart backend after editing mutations.gql")
            errors += 1
            continue
        try:
            await dc.execute_mutation(op, {"workspaceId": workspace_id})
        except Exception as e:
            logger.warning("demo_reset_step_failed", op=op, error=str(e))
            errors += 1
    logger.info("demo_reset_complete", workspace_id=workspace_id, errors=errors)
    return {"steps": len(_DELETE_ORDER), "errors": errors}
