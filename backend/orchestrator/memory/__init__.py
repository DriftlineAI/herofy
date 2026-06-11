"""
Orchestrator memory — read path (Phase 0) and write/consolidation path (Phase 2).

Read path (here): scoped context assembly + the hybrid `memory_recall` tool.
SQL is the source of truth; a vector index is a swappable accelerator added later
(DataConnect-only for the demo). Tenant isolation is a hard line — recall never
crosses the workspace boundary.
"""

from .context import assemble_context, make_context_load_callback
from .recall import memory_recall
from .ingest import consolidate_account_memory

__all__ = ["assemble_context", "make_context_load_callback", "memory_recall", "consolidate_account_memory"]
