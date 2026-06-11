"""
Signal deduplication via content fingerprinting.

Prevents duplicate signal processing across agent runs by computing
and storing fingerprints of processed signals.

Example:
    from agents.signal_watcher.deduplication import (
        compute_signal_fingerprint,
        is_duplicate_signal,
        mark_signal_processed,
    )

    fingerprint = compute_signal_fingerprint(signal)
    if not await is_duplicate_signal(workspace_id, fingerprint):
        # Process signal
        await mark_signal_processed(workspace_id, fingerprint, signal.id)
"""

import hashlib
from datetime import datetime, timedelta, timezone

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger

logger = get_logger("SignalDeduplication")


def compute_signal_fingerprint(signal) -> str:
    """
    Generate a deterministic fingerprint from signal content.

    Fingerprint components:
    - source (gmail, slack, notion)
    - external_id (message ID from source)
    - occurred_at (ISO timestamp, truncated to minute)
    - body_snippet (first 500 chars, normalized)

    Args:
        signal: RawSignal or ClassifiedSignal instance

    Returns:
        SHA256 hash (64 hex chars)
    """
    # Get source value (handle both enum and string)
    source_value = signal.source.value if hasattr(signal.source, "value") else str(signal.source)

    # Normalize body: lowercase, strip whitespace, take first 500 chars
    body_snippet = ""
    if signal.body:
        body_snippet = signal.body.lower().strip()[:500]

    # Truncate timestamp to minute for slight tolerance
    occurred_str = ""
    if signal.occurred_at:
        if isinstance(signal.occurred_at, datetime):
            occurred_str = signal.occurred_at.replace(second=0, microsecond=0).isoformat()
        else:
            occurred_str = str(signal.occurred_at)[:16]  # YYYY-MM-DDTHH:MM

    # Build deterministic string
    fingerprint_source = f"{source_value}|{signal.external_id}|{occurred_str}|{body_snippet}"

    # SHA256 hash
    return hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()


async def is_duplicate_signal(
    workspace_id: str,
    fingerprint: str,
) -> bool:
    """
    Check if signal fingerprint already exists.

    Args:
        workspace_id: Workspace UUID
        fingerprint: SHA256 fingerprint

    Returns:
        True if duplicate (already processed)
    """
    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "GetSignalFingerprint",
        {
            "workspaceId": workspace_id,
            "fingerprint": fingerprint,
        },
    )

    if result.get("signalFingerprint"):
        logger.debug(
            "duplicate_signal_detected",
            fingerprint=fingerprint[:16],
        )
        return True

    return False


async def mark_signal_processed(
    workspace_id: str,
    fingerprint: str,
    signal_id: str | None,
) -> bool:
    """
    Mark signal as processed by inserting fingerprint.

    Handles conflicts gracefully (best-effort deduplication).

    Args:
        workspace_id: Workspace UUID
        fingerprint: SHA256 fingerprint
        signal_id: Optional signal UUID for reference

    Returns:
        True if inserted, False if already existed or on error
    """
    try:
        dc = get_dataconnect_client()

        # Check if already exists first (DataConnect doesn't have ON CONFLICT)
        if await is_duplicate_signal(workspace_id, fingerprint):
            return False

        await dc.execute_mutation(
            "CreateSignalFingerprint",
            {
                "workspaceId": workspace_id,
                "fingerprint": fingerprint,
                "signalId": signal_id,
            },
        )

        logger.debug(
            "signal_fingerprint_recorded",
            fingerprint=fingerprint[:16],
        )

        return True

    except Exception as e:
        logger.error(
            "fingerprint_insert_failed",
            fingerprint=fingerprint[:16],
            error=str(e),
        )
        # Don't raise - deduplication is best-effort
        return False


async def check_and_mark_duplicate(
    workspace_id: str,
    signal,
) -> bool:
    """
    Convenience function: check if duplicate and mark as processed if not.

    Args:
        workspace_id: Workspace UUID
        signal: RawSignal instance

    Returns:
        True if signal is a duplicate (should skip processing)
        False if signal is new (has been marked for processing)
    """
    fingerprint = compute_signal_fingerprint(signal)

    if await is_duplicate_signal(workspace_id, fingerprint):
        return True

    # Mark as processed (race condition handled by check-then-insert)
    await mark_signal_processed(workspace_id, fingerprint, signal.id)
    return False


async def cleanup_old_fingerprints(
    workspace_id: str,
    days_to_keep: int = 90,
) -> int:
    """
    Clean up fingerprints older than N days.

    Should be called periodically (e.g., daily) to prevent unbounded growth.

    Args:
        workspace_id: Workspace UUID
        days_to_keep: Retention period in days (default: 90)

    Returns:
        Number of deleted records (always 0 for DataConnect - no count returned)
    """
    dc = get_dataconnect_client()

    # Calculate cutoff date
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    try:
        await dc.execute_mutation(
            "DeleteOldSignalFingerprints",
            {
                "workspaceId": workspace_id,
                "beforeDate": cutoff_date.isoformat(),
            },
        )

        logger.info(
            "fingerprints_cleaned_up",
            workspace_id=workspace_id,
            retention_days=days_to_keep,
            cutoff_date=cutoff_date.isoformat(),
        )

        # DataConnect doesn't return deletion count
        return 0

    except Exception as e:
        logger.error(
            "fingerprint_cleanup_failed",
            workspace_id=workspace_id,
            error=str(e),
        )
        return 0
