"""
MetricSnapshot retention / downsampling.

Append-on-change is chatty for active accounts. Rows are small, but we keep RAW
high-frequency rows only for a recent window (default 90 days) and roll older
history down to ONE row per (customer, metric, day) — the last of that day.
Nothing is silently dropped: the job logs exactly what it collapsed (SIGNAL_AGGREGATION.md).

Single bounded pass per call (no internal re-query loop), so it always terminates
and is idempotent: once old rows are already daily, a re-run deletes nothing.
DataConnect has no GROUP BY, so the grouping is done in Python and surplus rows are
deleted by id. Schedule periodically (Cloud Scheduler); large backlogs drain over
several runs.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config import get_settings
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("MetricRetention")


def plan_downsample_deletions(rows: list[dict]) -> tuple[list[str], int]:
    """Pure: from old snapshot rows, return (ids_to_delete, kept_daily_count).

    Keeps the LATEST row per (customer, stakeholder, metric, day) and marks the rest
    for deletion. Idempotent — already-daily input yields no deletions. Stakeholder is
    in the key so per-stakeholder metrics keep one row per stakeholder per day.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        cust = (r.get("customer") or {}).get("id")
        stake = (r.get("stakeholder") or {}).get("id")
        day = str(r.get("capturedAt", ""))[:10]
        groups[(cust, stake, r.get("metric"), day)].append(r)

    to_delete: list[str] = []
    for members in groups.values():
        if len(members) > 1:
            members.sort(key=lambda r: r.get("capturedAt", ""))  # ASC; last = latest
            to_delete.extend(m["id"] for m in members[:-1])
    return to_delete, len(groups)


@dataclass
class RetentionSummary:
    workspace_id: str
    keep_days: int
    scanned: int = 0
    deleted: int = 0
    kept_daily: int = 0
    capped: bool = False  # True when the row cap was hit and more remain for next run


async def downsample_metric_snapshots(
    workspace_id: str,
    *,
    keep_days: int = 90,
    max_rows: int = 2000,
) -> RetentionSummary:
    """Downsample raw snapshots older than `keep_days` to one row per
    (customer, metric, day). No-op when the flag is off. Never raises."""
    summary = RetentionSummary(workspace_id=workspace_id, keep_days=keep_days)
    if not get_settings().metric_snapshots_enabled:
        return summary

    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetMetricSnapshotsBefore",
            {"workspaceId": workspace_id, "before": cutoff, "limit": max_rows},
        )
        rows = result.get("metricSnapshots", []) or []
    except Exception as e:
        logger.error("retention_fetch_failed", workspace_id=workspace_id, error=str(e))
        return summary

    summary.scanned = len(rows)
    summary.capped = len(rows) >= max_rows

    to_delete, summary.kept_daily = plan_downsample_deletions(rows)

    for snap_id in to_delete:
        try:
            await dc.execute_mutation("DeleteMetricSnapshot", {"id": snap_id})
            summary.deleted += 1
        except Exception as e:
            logger.warning("retention_delete_failed", snapshot_id=snap_id, error=str(e))

    logger.info(
        "retention_downsampled",
        workspace_id=workspace_id,
        scanned=summary.scanned,
        deleted=summary.deleted,
        kept_daily=summary.kept_daily,
        capped=summary.capped,
    )
    return summary
