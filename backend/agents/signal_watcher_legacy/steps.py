"""
SignalWatcher Chain Steps
Individual step implementations for the sequential agent

Steps:
1. FetchSignalsStep - Get new signals from all sources
2. ClassifySignalsStep - Classify each signal (need_type, sentiment, urgency)
3. MatchThreadsStep - Match signals to existing threads
4. MatchNeedsStep - Match to existing needs or create new
5. ExtractProfilesStep - Update stakeholder profiles
6. CreateInteractionsStep - Create interaction records
7. UpdateWatermarksStep - Update watermarks for all sources

Features:
- Signal deduplication via fingerprinting (prevents reprocessing)
- Body encryption for interaction storage
- Hybrid classification (regex + LLM fallback)
- OpenTelemetry tracing for observability
- Real API sources when integrations configured, mock fallback for dev
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from core.errors import StepFailedError, IntegrationNotConfiguredError
from core.logging import get_logger
from core.encryption import encrypt_field
from core.metrics import trace_step
from core.types import IntegrationType
from db.client import get_db_client
from db.dataconnect_client import get_dataconnect_client
from services.integration_service import IntegrationService
from services.sidekick_service import SidekickService
from tools.database_tool import insert_need, get_handbook_version

from agents.signal_watcher.models import (
    RawSignal,
    ClassifiedSignal,
    ProcessedSignal,
    ThreadMatch,
    NeedMatch,
    SignalBatch,
    MatchType,
    Sentiment,
    EngagementLevel,
)
from agents.signal_watcher.sources import (
    SignalSourceBase,
    MockGmailSource,
    MockSlackSource,
    MockNotionSource,
    GmailSignalSource,
    SlackSignalSource,
)
from agents.signal_watcher.classifiers import RegexClassifier, HybridClassifier
from agents.signal_watcher.matching import SignalMatcher
from agents.signal_watcher.profiles import StakeholderAnalyzer
from agents.signal_watcher.deduplication import (
    compute_signal_fingerprint,
    is_duplicate_signal,
    mark_signal_processed,
)

from .context import SignalWatcherContext

logger = get_logger("SignalWatcherSteps")


# =============================================================================
# Step 1: Fetch Signals
# =============================================================================


async def _is_integration_configured(
    integration_service: IntegrationService,
    integration_type: IntegrationType,
) -> bool:
    """
    Check if an integration is configured and active.

    Args:
        integration_service: Integration service instance
        integration_type: Type of integration to check

    Returns:
        True if integration is configured and active
    """
    try:
        integration = await integration_service.get_integration(integration_type)
        return integration is not None and integration.get("status") == "active"
    except Exception:
        return False


async def _build_signal_sources(
    workspace_id: str,
    db,
    integration_service: IntegrationService,
) -> list[SignalSourceBase]:
    """
    Build list of signal sources based on configured integrations.

    Uses real API sources when integrations are configured.
    Mock sources are ONLY used when explicitly opted-in via USE_MOCK_* env vars.
    This prevents silent fallback to mocks when testing real integrations.

    Args:
        workspace_id: Workspace ID
        db: Database client
        integration_service: Integration service for OAuth

    Returns:
        List of configured signal sources
    """
    from config import settings

    sources: list[SignalSourceBase] = []

    # Check Gmail integration
    if await _is_integration_configured(integration_service, IntegrationType.GMAIL):
        sources.append(GmailSignalSource(workspace_id, db, integration_service))
        logger.info("source_enabled", source="gmail", mode="real")
    elif settings.use_mock_gmail:
        # Explicit opt-in to mock - not automatic
        sources.append(MockGmailSource(workspace_id, db))
        logger.info("source_enabled", source="gmail", mode="mock")
    else:
        logger.info("source_skipped", source="gmail", reason="not_configured_and_mocks_disabled")

    # Check Slack integration
    if await _is_integration_configured(integration_service, IntegrationType.SLACK):
        sources.append(SlackSignalSource(workspace_id, db, integration_service))
        logger.info("source_enabled", source="slack", mode="real")
    elif settings.use_mock_slack:
        # Explicit opt-in to mock - not automatic
        sources.append(MockSlackSource(workspace_id, db))
        logger.info("source_enabled", source="slack", mode="mock")
    else:
        logger.info("source_skipped", source="slack", reason="not_configured_and_mocks_disabled")

    # Notion signal source not yet implemented - mock only if explicitly opted in
    if settings.use_mock_notion:
        sources.append(MockNotionSource(workspace_id, db))
        logger.info("source_enabled", source="notion", mode="mock")

    return sources


async def _surface_integration_setup_need(ctx: SignalWatcherContext) -> None:
    """
    Surface a Today queue item prompting integration setup.

    Called when no integrations are configured for a workspace.
    """
    try:
        await insert_need(
            workspace_id=ctx.workspace_id,
            customer_id=None,  # System-level need
            need_type="uncategorized",  # No specific type for setup prompts
            headline="Connect your tools to get started",
            lede="Herofy needs access to Gmail, Slack, or Notion to monitor customer signals",
            agent_reasoning="No integrations configured. Connect at least one communication tool to enable signal monitoring.",
            handbook_version_id=ctx.handbook_version_id,
            priority_rank=5,
        )
    except Exception as e:
        # Don't fail the whole step if we can't surface the need
        logger.warning("failed_to_surface_setup_need", error=str(e))


async def fetch_signals_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 1: Fetch new signals from all sources.

    Sources: Gmail, Slack, Notion
    - Uses real API clients when integrations are configured
    - Falls back to mock sources in development mode only
    - Gracefully skips sources that aren't configured
    """
    logger.info(
        "step_started",
        step="FetchSignalsStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()
        integration_service = IntegrationService(db, ctx.workspace_id)
        batches: list[SignalBatch] = []
        all_signals: list[RawSignal] = []

        # Build sources based on configured integrations
        sources = await _build_signal_sources(
            ctx.workspace_id, db, integration_service
        )

        # Surface setup prompt if no sources available
        if not sources:
            logger.info(
                "no_sources_configured",
                workspace_id=ctx.workspace_id,
            )
            await _surface_integration_setup_need(ctx)
            return ctx.with_raw_signals([], [])

        # Fetch from each source
        for source in sources:
            source_type = source._get_source_type()
            watermark_before = await source.get_watermark()

            try:
                signals = await source.fetch_new_signals()

                # Only set watermark_after if we actually got signals
                # This prevents skipping signals that arrive between fetch and watermark update
                if signals:
                    # Use the latest signal timestamp as the watermark, not current time
                    watermark_after = max(s.occurred_at for s in signals)
                else:
                    watermark_after = None

                batch = SignalBatch(
                    source=source_type,
                    signals=signals,
                    watermark_before=watermark_before,
                    watermark_after=watermark_after,
                )
                batches.append(batch)
                all_signals.extend(signals)

                logger.info(
                    "source_fetched",
                    source=source_type.value,
                    signal_count=len(signals),
                )

            except Exception as e:
                logger.warning(
                    "source_fetch_failed",
                    source=source_type.value,
                    error=str(e),
                )
                # Continue with other sources

        # Phase 1: In-memory deduplication across sources (same signal in email + Slack)
        seen_external_ids: set[str] = set()
        memory_deduplicated: list[RawSignal] = []
        memory_duplicate_count = 0

        for signal in all_signals:
            unique_key = f"{signal.source.value}:{signal.external_id}"
            if unique_key not in seen_external_ids:
                seen_external_ids.add(unique_key)
                memory_deduplicated.append(signal)
            else:
                memory_duplicate_count += 1

        if memory_duplicate_count > 0:
            logger.debug(
                "memory_dedup_complete",
                duplicates_removed=memory_duplicate_count,
            )

        # Phase 2: Database-backed deduplication (prevents reprocessing across runs)
        deduplicated_signals: list[RawSignal] = []
        db_duplicate_count = 0

        for signal in memory_deduplicated:
            fingerprint = compute_signal_fingerprint(signal)

            # Check if already processed in previous runs
            if await is_duplicate_signal(ctx.workspace_id, fingerprint, db):
                db_duplicate_count += 1
                logger.debug(
                    "signal_already_processed",
                    fingerprint=fingerprint[:16],
                    external_id=signal.external_id,
                )
                continue

            # Mark as processed immediately to prevent race conditions
            await mark_signal_processed(
                ctx.workspace_id,
                fingerprint,
                signal.id,
                db,
            )

            deduplicated_signals.append(signal)

        if db_duplicate_count > 0:
            logger.info(
                "db_dedup_complete",
                duplicates_removed=db_duplicate_count,
                remaining_signals=len(deduplicated_signals),
            )

        logger.info(
            "step_completed",
            step="FetchSignalsStep",
            run_id=ctx.run_id,
            total_signals=len(deduplicated_signals),
            memory_duplicates=memory_duplicate_count,
            db_duplicates=db_duplicate_count,
        )

        return ctx.with_raw_signals(batches, deduplicated_signals)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="FetchSignalsStep", error=str(e))
        raise StepFailedError(str(e), step_name="FetchSignalsStep")


# =============================================================================
# Step 2: Classify Signals
# =============================================================================


@trace_step("ClassifySignalsStep")
async def classify_signals_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 2: Classify each signal to determine need_type, sentiment, urgency.

    Uses HybridClassifier which:
    - Tries regex classification first (fast)
    - Falls back to LLM if confidence is below threshold
    - Mode controlled by SIGNAL_CLASSIFICATION_MODE env var:
      - "threshold" (default): LLM fallback when confidence < threshold
      - "always_llm": Always use LLM for classification
    """
    logger.info(
        "step_started",
        step="ClassifySignalsStep",
        run_id=ctx.run_id,
        signal_count=len(ctx.raw_signals),
    )

    try:
        # HybridClassifier handles mode switching internally based on config
        classifier = HybridClassifier(use_fuzzy=True)
        classified: list[ClassifiedSignal] = []
        llm_fallback_count = 0

        for signal in ctx.raw_signals:
            # Use async classify for LLM fallback support
            classification = await classifier.classify_async(signal)

            # Track LLM fallback usage
            if classification.confidence > 0.8 and "LLM" in classification.reasoning:
                llm_fallback_count += 1

            # Create classified signal
            classified_signal = ClassifiedSignal(
                id=signal.id,
                source=signal.source,
                external_id=signal.external_id,
                sender_email=signal.sender_email,
                sender_name=signal.sender_name,
                sender_domain=signal.sender_domain,
                subject=signal.subject,
                body=signal.body,
                channel=signal.channel,
                reply_to_id=signal.reply_to_id,
                thread_id=signal.thread_id,
                occurred_at=signal.occurred_at,
                raw_metadata=signal.raw_metadata,
                classification=classification,
            )

            classified.append(classified_signal)

        logger.info(
            "step_completed",
            step="ClassifySignalsStep",
            run_id=ctx.run_id,
            classified_count=len(classified),
            llm_fallback_count=llm_fallback_count,
        )

        return ctx.with_classified_signals(classified)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="ClassifySignalsStep", error=str(e))
        raise StepFailedError(str(e), step_name="ClassifySignalsStep")


# =============================================================================
# Step 3: Match Threads
# =============================================================================


async def match_threads_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 3: Match each signal to an existing thread.

    First resolves customer by email domain, then attempts thread matching.
    """
    logger.info(
        "step_started",
        step="MatchThreadsStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()
        matcher = SignalMatcher(ctx.workspace_id, db)

        thread_matches: dict[str, ThreadMatch | None] = {}
        updated_signals: list[ClassifiedSignal] = []

        for signal in ctx.classified_signals:
            # Resolve customer from email domain
            customer_id = await _resolve_customer(
                signal,
                matcher,
                ctx.customer_cache,
            )

            if not customer_id:
                logger.debug(
                    "customer_not_found",
                    signal_id=signal.id,
                    email=signal.sender_email,
                )
                thread_matches[signal.id] = None
                updated_signals.append(signal)
                continue

            # Update signal with customer_id
            signal.customer_id = customer_id

            # Try to match thread
            match = await matcher.match_signal_to_thread(signal, customer_id)
            thread_matches[signal.id] = match

            updated_signals.append(signal)

        # Update context with resolved customer IDs
        ctx = ctx.with_classified_signals(updated_signals)

        logger.info(
            "step_completed",
            step="MatchThreadsStep",
            run_id=ctx.run_id,
            matched_count=len([m for m in thread_matches.values() if m]),
        )

        return ctx.with_thread_matches(thread_matches)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="MatchThreadsStep", error=str(e))
        raise StepFailedError(str(e), step_name="MatchThreadsStep")


async def _resolve_customer(
    signal: ClassifiedSignal,
    matcher: SignalMatcher,
    cache: dict[str, str | None],
) -> str | None:
    """Resolve customer ID from signal, using cache."""
    domain = signal.sender_domain
    if not domain and signal.sender_email and "@" in signal.sender_email:
        domain = signal.sender_email.split("@")[1].lower()

    if not domain:
        return None

    # Check cache
    if domain in cache:
        return cache[domain]

    # Look up customer
    customer = await matcher.find_customer_by_email(signal.sender_email)
    customer_id = str(customer["id"]) if customer else None

    # Cache result
    cache[domain] = customer_id

    return customer_id


# =============================================================================
# Step 4: Match/Create Needs
# =============================================================================


async def match_needs_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 4: Match signals to existing needs or create new ones.
    """
    logger.info(
        "step_started",
        step="MatchNeedsStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()
        matcher = SignalMatcher(ctx.workspace_id, db)

        need_matches: dict[str, NeedMatch | None] = {}
        created_needs: list[dict[str, Any]] = []

        for signal in ctx.classified_signals:
            if not signal.customer_id:
                need_matches[signal.id] = None
                continue

            # Get thread match for this signal
            thread_match = ctx.thread_matches.get(signal.id)
            thread_id = thread_match.thread_id if thread_match else None

            # Try to match need
            need_match = await matcher.match_signal_to_need(
                signal,
                signal.customer_id,
                thread_id,
            )

            if need_match:
                need_matches[signal.id] = need_match
            else:
                # Create new need
                need = await _create_need_for_signal(
                    signal,
                    ctx.workspace_id,
                    ctx.handbook_version_id,
                )
                if need:
                    created_needs.append(need)
                    need_matches[signal.id] = NeedMatch(
                        need_id=str(need["id"]),
                        need_type=need["type"],
                        confidence=1.0,
                        reason="Created new need for signal",
                        need_headline=need.get("headline"),
                    )

        logger.info(
            "step_completed",
            step="MatchNeedsStep",
            run_id=ctx.run_id,
            matched_count=len([m for m in need_matches.values() if m]),
            created_count=len(created_needs),
        )

        return ctx.with_need_matches(need_matches, created_needs)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="MatchNeedsStep", error=str(e))
        raise StepFailedError(str(e), step_name="MatchNeedsStep")


async def _create_need_for_signal(
    signal: ClassifiedSignal,
    workspace_id: str,
    handbook_version_id: str | None,
) -> dict[str, Any] | None:
    """Create a need for a signal that didn't match existing needs."""
    if not signal.customer_id or not signal.classification:
        return None

    if not handbook_version_id:
        logger.warning("cannot_create_need", reason="no_handbook_version")
        return None

    classification = signal.classification
    need_type = classification.need_type

    # Build headline
    headline = _build_need_headline(signal, classification)

    # Build reasoning
    reasoning = _build_need_reasoning(signal, classification)

    try:
        need = await insert_need(
            workspace_id=workspace_id,
            customer_id=signal.customer_id,
            need_type=need_type,
            headline=headline,
            lede=f"From {signal.sender_name} via {signal.source.value}",
            agent_reasoning=reasoning,
            handbook_version_id=handbook_version_id,
            priority_rank=_get_priority_rank(classification),
        )
        return need
    except Exception as e:
        logger.error("need_creation_failed", error=str(e), signal_id=signal.id)
        return None


def _build_need_headline(signal: ClassifiedSignal, classification) -> str:
    """Build a headline for the need."""
    need_type_display = classification.need_type.replace("_", " ").title()

    if signal.subject:
        subject_preview = signal.subject[:50] + "..." if len(signal.subject) > 50 else signal.subject
        return f"{need_type_display}: {subject_preview}"

    return f"{need_type_display} from {signal.sender_name}"


def _build_need_reasoning(signal: ClassifiedSignal, classification) -> str:
    """Build agent_reasoning for the need."""
    parts = [
        f"Signal detected via {signal.source.value}",
        f"From: {signal.sender_name} ({signal.sender_email})",
        f"Classified as: {classification.need_type}",
        f"Sentiment: {classification.sentiment.value}",
        f"Urgency: {classification.urgency.value}",
        f"Confidence: {classification.confidence:.0%}",
    ]

    if classification.keywords:
        parts.append(f"Keywords: {', '.join(classification.keywords)}")

    if classification.reasoning:
        parts.append(f"\nClassification reasoning: {classification.reasoning}")

    return "\n".join(parts)


def _get_priority_rank(classification) -> int:
    """Get priority rank based on urgency."""
    urgency = classification.urgency.value
    if urgency == "urgent":
        return 1
    elif urgency == "high":
        return 5
    elif urgency == "medium":
        return 10
    else:
        return 20


# =============================================================================
# Step 5: Extract Stakeholder Profiles
# =============================================================================


def _select_most_relevant_signal(signals: list[ClassifiedSignal]) -> ClassifiedSignal:
    """
    Select the most relevant signal from a list of signals from the same sender.

    Priority order:
    1. Most severe sentiment (frustrated > negative > neutral > positive)
    2. Highest urgency
    3. Most recent

    Args:
        signals: List of signals from the same sender

    Returns:
        The most relevant signal
    """
    if len(signals) == 1:
        return signals[0]

    # Sentiment severity ranking (higher = more severe, we want to capture issues)
    sentiment_rank = {
        "frustrated": 4,
        "negative": 3,
        "neutral": 2,
        "positive": 1,
    }

    # Urgency ranking
    urgency_rank = {
        "urgent": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    def signal_score(s: ClassifiedSignal) -> tuple:
        """Score a signal for sorting (higher = more relevant)."""
        sentiment = "neutral"
        urgency = "low"

        if s.classification:
            sentiment = s.classification.sentiment.value if s.classification.sentiment else "neutral"
            urgency = s.classification.urgency.value if s.classification.urgency else "low"

        return (
            sentiment_rank.get(sentiment, 2),
            urgency_rank.get(urgency, 1),
            s.occurred_at,  # Tie-breaker: most recent
        )

    return max(signals, key=signal_score)


async def extract_profiles_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 5: Extract/update stakeholder profiles from signals.

    Also creates SidekickItem tips for notable observations:
    - Frustrated sentiment detected
    - Engagement level drop (going dark)
    """
    logger.info(
        "step_started",
        step="ExtractProfilesStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()
        dc = get_dataconnect_client()
        analyzer = StakeholderAnalyzer(ctx.workspace_id, db)
        sidekick = SidekickService(dc, ctx.workspace_id)

        profiles: dict[str, Any] = {}
        tips_created = 0

        # Group signals by sender, keeping track of all signals per sender
        signals_by_sender: dict[str, list[ClassifiedSignal]] = {}
        for signal in ctx.classified_signals:
            if not signal.sender_email or not signal.customer_id:
                continue

            email = signal.sender_email.lower()
            if email not in signals_by_sender:
                signals_by_sender[email] = []
            signals_by_sender[email].append(signal)

        # Process each sender, using the most severe/recent signal
        for email, sender_signals in signals_by_sender.items():
            # Pick the signal with the most severe sentiment or most recent
            signal = _select_most_relevant_signal(sender_signals)

            # Analyze stakeholder
            profile = await analyzer.analyze_stakeholder(
                signal,
                signal.classification,
                signal.customer_id,
            )

            # Update database
            await analyzer.update_stakeholder_record(
                signal.customer_id,
                profile,
            )

            profiles[email] = profile

            # Create SidekickItem tips for notable observations
            # Tip: Frustrated sentiment detected
            if signal.classification and signal.classification.sentiment == Sentiment.FRUSTRATED:
                try:
                    sender_name = profile.name if profile.name else signal.sender_name or email
                    await sidekick.create_tip(
                        customer_id=signal.customer_id,
                        text=f"Frustrated tone detected from {sender_name}",
                    )
                    tips_created += 1
                    logger.debug(
                        "sidekick_tip_frustrated_created",
                        customer_id=signal.customer_id,
                        sender=sender_name,
                    )
                except Exception as e:
                    # Non-fatal - log and continue
                    logger.warning(
                        "sidekick_tip_creation_failed",
                        customer_id=signal.customer_id,
                        error=str(e),
                    )

            # Tip: Engagement level drop (going dark)
            if profile.engagement_level == EngagementLevel.DISENGAGED:
                try:
                    sender_name = profile.name if profile.name else signal.sender_name or email
                    await sidekick.create_observed(
                        customer_id=signal.customer_id,
                        text=f"{sender_name} engagement dropping - no response in 30+ days",
                    )
                    tips_created += 1
                    logger.debug(
                        "sidekick_observed_disengaged_created",
                        customer_id=signal.customer_id,
                        sender=sender_name,
                    )
                except Exception as e:
                    # Non-fatal - log and continue
                    logger.warning(
                        "sidekick_observed_creation_failed",
                        customer_id=signal.customer_id,
                        error=str(e),
                    )

        logger.info(
            "step_completed",
            step="ExtractProfilesStep",
            run_id=ctx.run_id,
            profile_count=len(profiles),
            tips_created=tips_created,
        )

        return ctx.with_stakeholder_profiles(profiles)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="ExtractProfilesStep", error=str(e))
        raise StepFailedError(str(e), step_name="ExtractProfilesStep")


# =============================================================================
# Step 6: Create Interactions
# =============================================================================


async def create_interactions_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 6: Create interaction records for each signal.

    Also creates threads if no existing thread was matched.
    """
    logger.info(
        "step_started",
        step="CreateInteractionsStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()

        created_interactions: list[dict[str, Any]] = []
        created_threads: list[dict[str, Any]] = []
        processed_signals: list[ProcessedSignal] = []

        for signal in ctx.classified_signals:
            if not signal.customer_id:
                continue

            thread_match = ctx.thread_matches.get(signal.id)
            need_match = ctx.need_matches.get(signal.id)

            # Determine thread_id (existing or create new)
            thread_id = None
            created_thread = None

            if thread_match:
                thread_id = thread_match.thread_id
            else:
                # Create new thread
                need_id = need_match.need_id if need_match else None
                created_thread = await _create_thread(
                    db,
                    ctx.workspace_id,
                    signal,
                    need_id,
                )
                if created_thread:
                    thread_id = str(created_thread["id"])
                    created_threads.append(created_thread)

            # Create interaction
            interaction = await _create_interaction(
                db,
                ctx.workspace_id,
                signal,
                thread_id,
            )

            if interaction:
                created_interactions.append(interaction)

            # Build processed signal
            processed = ProcessedSignal(
                raw_signal=signal,
                classification=signal.classification,
                customer_id=signal.customer_id,
                thread_match=thread_match,
                need_match=need_match,
                created_thread_id=str(created_thread["id"]) if created_thread else None,
                created_need_id=need_match.need_id if need_match else None,
                created_interaction_id=str(interaction["id"]) if interaction else None,
                is_inferred_match=(
                    thread_match is not None and
                    thread_match.match_type == MatchType.INFERRED
                ),
                needs_review=(
                    thread_match is not None and
                    thread_match.match_type == MatchType.INFERRED and
                    thread_match.confidence < 0.8
                ),
            )
            processed_signals.append(processed)

        logger.info(
            "step_completed",
            step="CreateInteractionsStep",
            run_id=ctx.run_id,
            interaction_count=len(created_interactions),
            thread_count=len(created_threads),
        )

        # Push real-time notification if any interactions were created
        if created_interactions:
            try:
                from services.firestore_service import get_firestore_service
                firestore_service = get_firestore_service()

                # Get the first thread_id for the notification
                first_thread_id = None
                if created_threads:
                    first_thread_id = str(created_threads[0].get("id"))
                elif processed_signals and processed_signals[0].created_thread_id:
                    first_thread_id = processed_signals[0].created_thread_id

                # Get channel from first signal
                channel = None
                if ctx.classified_signals:
                    channel = ctx.classified_signals[0].channel

                await firestore_service.notify_conversation_updated(
                    workspace_id=ctx.workspace_id,
                    thread_id=first_thread_id,
                    interaction_count=len(created_interactions),
                    channel=channel,
                )
            except Exception as e:
                # Don't fail the step for notification errors
                logger.warning(
                    "firestore_notification_failed",
                    step="CreateInteractionsStep",
                    error=str(e),
                )

        return ctx.with_interactions(created_interactions, created_threads, processed_signals)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="CreateInteractionsStep", error=str(e))
        raise StepFailedError(str(e), step_name="CreateInteractionsStep")


async def _create_thread(
    db,
    workspace_id: str,
    signal: ClassifiedSignal,
    need_id: str | None,
) -> dict[str, Any] | None:
    """Create a new thread for a signal."""
    try:
        # Determine thread_type based on signal source
        # 'customer' = external customer communication
        # 'internal' = internal team communication
        # 'sidekick' = AI assistant threads (not created here)
        thread_type = "customer"

        thread = await db.insert(
            "threads",
            {
                "workspace_id": workspace_id,
                "customer_id": signal.customer_id,
                "subject": signal.subject or f"Message from {signal.sender_name}",
                "status": "open",
                "channel": signal.channel,
                "thread_type": thread_type,
                "category": "uncategorized",
                "need_id": need_id,
                "origin_detail": signal.external_id,
            },
        )
        return thread
    except Exception as e:
        logger.error("thread_creation_failed", error=str(e))
        return None


async def _create_interaction(
    db,
    workspace_id: str,
    signal: ClassifiedSignal,
    thread_id: str | None,
) -> dict[str, Any] | None:
    """Create an interaction record for a signal with encrypted body."""
    try:
        # Encrypt the body content for storage
        # encrypt_field gracefully returns plaintext if encryption key not configured
        encrypted_body = encrypt_field(signal.body) if signal.body else None

        interaction = await db.insert(
            "interactions",
            {
                "workspace_id": workspace_id,
                "customer_id": signal.customer_id,
                "thread_id": thread_id,
                "channel": signal.channel,
                "origin_kind": signal.source.value,
                "direction": "customer",
                "sender_name": signal.sender_name,
                "occurred_at": signal.occurred_at,
                "subject": signal.subject,
                "body_encrypted": encrypted_body,  # Now properly encrypted
                "summary_ai": signal.classification.reasoning if signal.classification else None,
                "external_ref": {
                    "system": signal.source.value,
                    "message_id": signal.external_id,
                },
            },
        )
        return interaction
    except Exception as e:
        logger.error("interaction_creation_failed", error=str(e))
        return None


# =============================================================================
# Step 7: Update Watermarks
# =============================================================================


async def update_watermarks_step(ctx: SignalWatcherContext) -> SignalWatcherContext:
    """
    Step 7: Update watermarks for all successfully processed sources.
    """
    logger.info(
        "step_started",
        step="UpdateWatermarksStep",
        run_id=ctx.run_id,
    )

    try:
        db = get_db_client()
        watermarks: dict[str, datetime] = {}

        # Update watermark for each source batch
        for batch in ctx.signal_batches:
            if batch.watermark_after:
                source_key = f"signal_watcher:{batch.source.value}:watermark"

                await db.execute(
                    """
                    INSERT INTO agent_state (workspace_id, key, value, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (workspace_id, key)
                    DO UPDATE SET value = $3, updated_at = NOW()
                    """,
                    [ctx.workspace_id, source_key, batch.watermark_after.isoformat()],
                )

                watermarks[batch.source.value] = batch.watermark_after

                logger.info(
                    "watermark_updated",
                    source=batch.source.value,
                    timestamp=batch.watermark_after.isoformat(),
                )

        logger.info(
            "step_completed",
            step="UpdateWatermarksStep",
            run_id=ctx.run_id,
            watermark_count=len(watermarks),
        )

        return ctx.with_watermarks(watermarks)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="UpdateWatermarksStep", error=str(e))
        raise StepFailedError(str(e), step_name="UpdateWatermarksStep")
