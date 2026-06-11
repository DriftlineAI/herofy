"""
Herofy Orchestrator — net-new, queue-driven autonomous worker.

Side-by-side with `agents/handoff_auto/` (never modifies it). Reuses existing
tool *callables* by import. Entire orchestrator scope lives under this package
and is mounted only when `settings.orchestration_enabled` is True (mount-only
feature flag — see config.ORCHESTRATION_ENABLED).

Layers:
  runtime/      ADK wiring (services, runner, callbacks, state) — stood up once.
  queue/        AgentTask work queue (repository + consumer/drain).
  worker/       the autonomous decision agent (Phase 1).
  plays/        deterministic SequentialAgent workflows (Phase 1).
  specialists/  small reusable sub-agents (Phase 1).
  memory/       scoped context-load + memory_recall (read path, Phase 0).
"""
