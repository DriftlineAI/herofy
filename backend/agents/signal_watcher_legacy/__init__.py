"""
SignalWatcher Chain Agent (LEGACY - DEPRECATED)

DEPRECATED: This is the old RawSignal-based approach.
DO NOT USE in production. Use signal_watcher_unified/event_processor.py instead.

This agent fetches signals directly from sources using the RawSignal model,
but has been replaced by the unified ingestion pipeline (ChangeEvent model).
"""

from .agent import run_signal_watcher_chain, SignalWatcherChainResult

__all__ = [
    "run_signal_watcher_chain",
    "SignalWatcherChainResult",
]
