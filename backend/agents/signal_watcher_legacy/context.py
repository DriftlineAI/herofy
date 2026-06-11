"""
SignalWatcher Chain Context
Shared state passed between agent steps
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from agents.signal_watcher.models import (
    RawSignal,
    ClassifiedSignal,
    ProcessedSignal,
    ThreadMatch,
    NeedMatch,
    StakeholderProfile,
    SignalBatch,
)


@dataclass
class SignalWatcherContext:
    """
    Context object passed between SignalWatcher chain steps.
    Accumulates data as each step executes.
    """

    # Input parameters
    workspace_id: str

    # Run metadata
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.utcnow)
    handbook_version_id: str | None = None

    # Step 1: Fetch Signals
    signal_batches: list[SignalBatch] = field(default_factory=list)
    raw_signals: list[RawSignal] = field(default_factory=list)

    # Step 2: Classify Signals
    classified_signals: list[ClassifiedSignal] = field(default_factory=list)

    # Step 3: Match Threads
    thread_matches: dict[str, ThreadMatch | None] = field(default_factory=dict)  # signal_id -> match

    # Step 4: Match/Create Needs
    need_matches: dict[str, NeedMatch | None] = field(default_factory=dict)  # signal_id -> match
    created_needs: list[dict[str, Any]] = field(default_factory=list)

    # Step 5: Extract Profiles
    stakeholder_profiles: dict[str, StakeholderProfile] = field(default_factory=dict)  # email -> profile

    # Step 6: Create Interactions
    created_interactions: list[dict[str, Any]] = field(default_factory=list)
    created_threads: list[dict[str, Any]] = field(default_factory=list)

    # Step 7: Watermarks (updated on success)
    watermarks_updated: dict[str, datetime] = field(default_factory=dict)

    # Tracking
    processed_signals: list[ProcessedSignal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    failed_step: str | None = None

    # Customer resolution cache
    customer_cache: dict[str, str | None] = field(default_factory=dict)  # email_domain -> customer_id

    def with_raw_signals(
        self,
        batches: list[SignalBatch],
        signals: list[RawSignal],
    ) -> "SignalWatcherContext":
        """Return new context with fetched signals."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=batches,
            raw_signals=signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_classified_signals(
        self,
        classified: list[ClassifiedSignal],
    ) -> "SignalWatcherContext":
        """Return new context with classified signals."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=classified,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_thread_matches(
        self,
        matches: dict[str, ThreadMatch | None],
    ) -> "SignalWatcherContext":
        """Return new context with thread matches."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_need_matches(
        self,
        matches: dict[str, NeedMatch | None],
        created: list[dict[str, Any]],
    ) -> "SignalWatcherContext":
        """Return new context with need matches and created needs."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=matches,
            created_needs=created,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_stakeholder_profiles(
        self,
        profiles: dict[str, StakeholderProfile],
    ) -> "SignalWatcherContext":
        """Return new context with stakeholder profiles."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_interactions(
        self,
        interactions: list[dict[str, Any]],
        threads: list[dict[str, Any]],
        processed: list[ProcessedSignal],
    ) -> "SignalWatcherContext":
        """Return new context with created interactions."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=interactions,
            created_threads=threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=processed,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_watermarks(
        self,
        watermarks: dict[str, datetime],
    ) -> "SignalWatcherContext":
        """Return new context with updated watermarks."""
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=watermarks,
            processed_signals=self.processed_signals,
            errors=self.errors,
            customer_cache=self.customer_cache,
        )

    def with_error(self, step_name: str, error: str) -> "SignalWatcherContext":
        """Return new context with error recorded."""
        new_errors = self.errors.copy()
        new_errors.append(f"{step_name}: {error}")
        return SignalWatcherContext(
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            started_at=self.started_at,
            handbook_version_id=self.handbook_version_id,
            signal_batches=self.signal_batches,
            raw_signals=self.raw_signals,
            classified_signals=self.classified_signals,
            thread_matches=self.thread_matches,
            need_matches=self.need_matches,
            created_needs=self.created_needs,
            stakeholder_profiles=self.stakeholder_profiles,
            created_interactions=self.created_interactions,
            created_threads=self.created_threads,
            watermarks_updated=self.watermarks_updated,
            processed_signals=self.processed_signals,
            errors=new_errors,
            failed_step=step_name,
            customer_cache=self.customer_cache,
        )

    @property
    def is_failed(self) -> bool:
        """Check if any step has failed."""
        return self.failed_step is not None

    @property
    def signal_count(self) -> int:
        """Total number of raw signals."""
        return len(self.raw_signals)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary for storage."""
        return {
            "workspace_id": self.workspace_id,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "handbook_version_id": self.handbook_version_id,
            "signal_count": self.signal_count,
            "classified_count": len(self.classified_signals),
            "thread_match_count": len([m for m in self.thread_matches.values() if m]),
            "need_match_count": len([m for m in self.need_matches.values() if m]),
            "created_need_count": len(self.created_needs),
            "created_interaction_count": len(self.created_interactions),
            "errors": self.errors,
            "failed_step": self.failed_step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalWatcherContext":
        """Deserialize context from dictionary."""
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elif started_at is None:
            started_at = datetime.utcnow()

        return cls(
            workspace_id=data["workspace_id"],
            run_id=data.get("run_id", str(uuid4())),
            started_at=started_at,
            handbook_version_id=data.get("handbook_version_id"),
            errors=data.get("errors", []),
            failed_step=data.get("failed_step"),
        )
