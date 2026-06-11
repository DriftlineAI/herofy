"""
Runner + RunConfig factory for the orchestrator.

A single place that wires an ADK agent to the shared Session/Memory/Artifact
services and applies the runaway guardrail (`max_llm_calls`). Used by the queue
consumer to invoke the worker, and reusable for invoking plays directly in tests.
"""

from google.adk.agents import BaseAgent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner

from .services import get_session_service, get_memory_service, get_artifact_service

# App name namespaces orchestrator sessions/artifacts away from "handoff_auto".
APP_NAME = "orchestrator"

# Runaway guardrail — caps total LLM calls per invocation (worker reasoning +
# all dispatched plays). Bounds cost and stops infinite tool loops.
MAX_LLM_CALLS = 60


def default_run_config(max_llm_calls: int = MAX_LLM_CALLS) -> RunConfig:
    """RunConfig with the runaway guardrail applied."""
    return RunConfig(max_llm_calls=max_llm_calls)


def build_runner(agent: BaseAgent) -> Runner:
    """Build a Runner for `agent` wired to the shared orchestrator services."""
    return Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=get_session_service(),
        memory_service=get_memory_service(),
        artifact_service=get_artifact_service(),
    )
