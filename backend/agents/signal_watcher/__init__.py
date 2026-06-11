"""
SignalWatcher Agent System
Autonomous agent that monitors Gmail/Slack/Notion for signals

This package contains:
- models: Data models for signals, classifications, matches, profiles
- sources: Signal source adapters (Gmail, Slack, Notion - mocked for now)
- classifiers: Signal classification logic (regex/fuzzy + future LLM hybrid)
- matching: Thread and need matching algorithms
- profiles: Stakeholder profile extraction
"""

from .models import (
    SignalSource,
    Sentiment,
    Urgency,
    MatchType,
    CommunicationStyle,
    EngagementLevel,
    ResponsePattern,
    RawSignal,
    Classification,
    ClassifiedSignal,
    ThreadMatch,
    NeedMatch,
    StakeholderProfile,
    ProcessedSignal,
    SignalBatch,
)

__all__ = [
    # Enums
    "SignalSource",
    "Sentiment",
    "Urgency",
    "MatchType",
    "CommunicationStyle",
    "EngagementLevel",
    "ResponsePattern",
    # Data models
    "RawSignal",
    "Classification",
    "ClassifiedSignal",
    "ThreadMatch",
    "NeedMatch",
    "StakeholderProfile",
    "ProcessedSignal",
    "SignalBatch",
]
