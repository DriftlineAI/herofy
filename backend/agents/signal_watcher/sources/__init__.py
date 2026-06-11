"""
Signal Sources
Abstract interface and implementations for fetching signals from external systems
"""

from .base import SignalSourceBase
from .mock_source import MockGmailSource, MockSlackSource, MockNotionSource
from .gmail_source import GmailSignalSource
from .slack_source import SlackSignalSource

__all__ = [
    "SignalSourceBase",
    # Mock sources (for development)
    "MockGmailSource",
    "MockSlackSource",
    "MockNotionSource",
    # Real API sources
    "GmailSignalSource",
    "SlackSignalSource",
]
