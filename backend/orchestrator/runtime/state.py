"""
Session-state contract for the orchestrator.

ADK session `state` is the short-term / working memory for a single task. We use
scope prefixes from day 1 so workspace- and account-scoped context stays clean and
so a future swap to a durable SessionService / MemoryService is seamless:

  app:    application/workspace-wide (e.g. workspace handbook digest)
  user:   per-CSM (preferences, working style)
  temp:   run-scoped scratch, never persisted to long-term memory
  (no prefix) = session-scoped (this task only)

These are plain string helpers — no ADK import — so they're cheap to reuse anywhere.
"""

# Scope prefixes (ADK-native semantics).
APP_SCOPE = "app:"
USER_SCOPE = "user:"
TEMP_SCOPE = "temp:"

# Well-known session-state keys the worker/plays/callbacks agree on.
KEY_RUN_ID = "run_id"            # AgentRun UUID (progress streaming + DB linkage)
KEY_TASK_ID = "task_id"          # AgentTask UUID being processed
KEY_WORKSPACE_ID = "workspace_id"
KEY_CUSTOMER_ID = "customer_id"  # present only when the task is about a customer
KEY_CUSTOMER_NAME = "customer_name"
KEY_TRIGGER_TYPE = "trigger_type"
KEY_PAYLOAD = "payload"          # the task payload (dict)

# Memory profile keys assembled by the context-load callback (memory/ module).
KEY_USER_PROFILE = USER_SCOPE + "profile"
KEY_WORKSPACE_PROFILE = APP_SCOPE + "profile"
KEY_CUSTOMER_PROFILE = "customer_profile"  # session-scoped (only when customer in scope)


def app_key(name: str) -> str:
    """Workspace/app-scoped state key."""
    return APP_SCOPE + name


def user_key(name: str) -> str:
    """CSM/user-scoped state key."""
    return USER_SCOPE + name


def temp_key(name: str) -> str:
    """Run-scoped scratch key (never consolidated to long-term memory)."""
    return TEMP_SCOPE + name


def initial_state(
    *,
    run_id: str,
    task_id: str,
    workspace_id: str,
    customer_id: str | None,
    customer_name: str | None,
    trigger_type: str,
    payload: dict | None = None,
) -> dict:
    """Build the session state dict for a worker/play invocation."""
    state: dict = {
        KEY_RUN_ID: run_id,
        KEY_TASK_ID: task_id,
        KEY_WORKSPACE_ID: workspace_id,
        KEY_TRIGGER_TYPE: trigger_type,
        KEY_PAYLOAD: payload or {},
    }
    if customer_id:
        state[KEY_CUSTOMER_ID] = customer_id
    if customer_name:
        state[KEY_CUSTOMER_NAME] = customer_name
    return state
