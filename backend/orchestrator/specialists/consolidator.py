"""
Consolidator specialist — the extract→reconcile brain of the memory write path.

An `LlmAgent` with `output_schema=ConsolidationOutput`. Given what just happened plus
the account's PRIOR strategy memo and current progress vectors, it produces a
*reconciled* strategy memo (merge, don't overwrite) and state updates for the vectors
the event actually moved. No tools — the deterministic writer (memory/ingest.py)
persists the result. This is how the system's understanding of an account compounds.
"""

from google.adk.agents import LlmAgent

from core.model_config import get_model, ModelUseCase

from .schemas import ConsolidationOutput
from ..runtime.callbacks import langfuse_model_cb

CONSOLIDATION_KEY = "consolidation"


def build_consolidator() -> LlmAgent:
    return LlmAgent(
        name="memory_consolidator",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You maintain the long-term memory for a Customer Success account. An event just "
            "occurred; update the account's memory to reflect it.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "WHAT JUST HAPPENED:\n{event_summary}\n\n"
            "PRIOR STRATEGY MEMO (may be '(none yet)'):\n{prior_strategy}\n\n"
            "CURRENT PROGRESS VECTORS (id · category · state · reason):\n{current_vectors}\n\n"
            "Produce:\n"
            "1) strategy_body — the updated living memo (markdown). RECONCILE with the prior memo: "
            "keep what's still true, fold in what changed, remove what's now wrong. Don't restate "
            "the whole history; it's a working memo, not a log. If prior is '(none yet)', write a "
            "concise fresh one.\n"
            "2) vector_updates — ONLY for vectors whose state this event actually changes, and ONLY "
            "using vector ids from the list above (never invent ids). Empty list if nothing moved.\n"
            "3) digest — one line on what we now understand.\n"
            "Be specific and grounded in the event; do not speculate beyond it."
        ),
        output_schema=ConsolidationOutput,
        output_key=CONSOLIDATION_KEY,
        after_model_callback=langfuse_model_cb,
    )
