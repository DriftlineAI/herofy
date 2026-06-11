"""
Event Emitters for Unified Ingestion Pipeline

Each emitter polls a source and produces ChangeEvent objects.
The orchestrator collects these and feeds them to SignalWatcher.
"""

from .base import EventEmitterBase
from .notion_emitter import NotionEventEmitter
from .gmail_emitter import GmailEventEmitter
from .slack_emitter import SlackEventEmitter

__all__ = [
    "EventEmitterBase",
    "NotionEventEmitter",
    "GmailEventEmitter",
    "SlackEventEmitter",
]
