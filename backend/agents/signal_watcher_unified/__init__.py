"""
SignalWatcher Unified Ingestion Pipeline
Deterministic event processing for all customer interactions (Gmail, Slack, Calendar, Notion)

IMPORTANT: Despite the historical "auto" name, this is the PRODUCTION pipeline.
It is deterministic, sequential, and does NOT use autonomous agents.
"""

from .agent import (
    run_signal_watcher_auto,
    resume_signal_watcher_auto,
    SignalWatcherAutoResult,
)
from .loop_controller import SignalWatcherLoopController
from .confidence import (
    assess_signal_confidence,
    assess_batch_confidence,
    should_pause_for_signal,
)
from .event_processor import SignalWatcherEventProcessor

__all__ = [
    "run_signal_watcher_auto",
    "resume_signal_watcher_auto",
    "SignalWatcherAutoResult",
    "SignalWatcherLoopController",
    "assess_signal_confidence",
    "assess_batch_confidence",
    "should_pause_for_signal",
    "SignalWatcherEventProcessor",
]
