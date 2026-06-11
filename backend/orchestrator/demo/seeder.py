"""Demo seed engine — turns the fixture into real DB rows in a target workspace.

Tiers run defaults first, then every customer as an independent pipeline (bounded
concurrency). Within a customer, steps are sequential because of FK order and because
two entities (Goal, Stakeholder) have no client-settable id — their server-generated
ids are captured from the insert response and threaded into dependent rows. Every other
id is deterministic (orchestrator.demo.ids), so cross-row links never re-query the DB.

Seeds CONTENT into an existing workspace (resolved by the route). It does not create
the Workspace/User/Member rows — that is the logged-in workspace today and the
per-visitor provisioner's job later (see DEMO_BUILD_PLAN.md).
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from core.logging import get_logger
from db.dataconnect_client import DataConnectClient, get_dataconnect_client
from orchestrator.demo import fixture as fx
from orchestrator.demo import ids

logger = get_logger("DemoSeeder")

_SEED_ACTOR = "demo-seed"
_CUSTOMER_CONCURRENCY = 6


@dataclass
class SeedResult:
    workspace_id: str
    profile: str
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ── time helpers (offsets → DataConnect strings) ──────────────────────────────


def _ts(delta_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


def _target_date(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _bump(counts: dict[str, int], key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


# Health → a believable 30-day sentiment trajectory (state per backdated day), used
# when a customer carries no explicit `sentiment` so every account still shows a
# sparkline. at_risk ends at `risk` so the sweep's SentimentTrendDetector dedups
# against the seeded signal instead of firing a fresh frustrated-signal need.
_SENTIMENT_BY_HEALTH: dict[str, tuple[tuple[int, str], ...]] = {
    "healthy": ((28, "ok"), (20, "warn"), (12, "ok"), (5, "ok")),
    "stable": ((28, "warn"), (20, "ok"), (12, "warn"), (5, "ok")),
    "at_risk": ((28, "ok"), (20, "warn"), (12, "warn"), (5, "risk")),
}


def _sentiment_series(c: fx.Customer) -> list[fx.SentimentPoint]:
    pts = _SENTIMENT_BY_HEALTH.get(c.health or "stable", _SENTIMENT_BY_HEALTH["stable"])
    return [fx.SentimentPoint(days_ago=d, state=s) for d, s in pts]


# ── public entry point ────────────────────────────────────────────────────────


async def seed_workspace(workspace_id: str, *, profile: str = "full") -> SeedResult:
    """Seed the Northcrest fixture (or a lane subset) into `workspace_id`."""
    dc = get_dataconnect_client()
    customers = fx.select(profile)
    result = SeedResult(workspace_id=workspace_id, profile=profile)

    await _seed_defaults(dc, workspace_id, result)

    sem = asyncio.Semaphore(_CUSTOMER_CONCURRENCY)

    async def _guarded(c: fx.Customer) -> None:
        async with sem:
            try:
                await _seed_customer(dc, workspace_id, c, result)
            except Exception as e:  # one bad customer must not abort the whole seed
                logger.exception("demo_seed_customer_failed", slug=c.slug, error=str(e))
                result.errors.append(f"{c.slug}: {e}")

    await asyncio.gather(*[_guarded(c) for c in customers])

    logger.info("demo_seed_complete", workspace_id=workspace_id, profile=profile,
                counts=result.counts, errors=len(result.errors))
    return result


# ── tier A: workspace defaults ────────────────────────────────────────────────


async def _seed_defaults(dc: DataConnectClient, ws: str, result: SeedResult) -> None:
    for pb in fx.PLAYBOOKS:
        try:
            pid = ids.playbook_id(ws, pb.slug)
            await dc.execute_mutation("CreatePlaybookWithId", {
                "id": pid, "workspaceId": ws, "name": pb.name,
                "archetype": pb.archetype, "fitNote": pb.fit_note, "scenario": pb.scenario,
            })
            _bump(result.counts, "playbooks")
            for m in pb.milestones:
                await dc.execute_mutation("CreatePlaybookMilestoneWithId", {
                    "id": ids.playbook_milestone_id(ws, pb.slug, m.sort_order),
                    "playbookId": pid, "title": m.title, "ownerSide": m.owner_side,
                    "durationDays": m.duration_days, "description": m.description,
                    "sortOrder": m.sort_order,
                })
                _bump(result.counts, "playbook_milestones")
        except Exception as e:
            logger.exception("demo_seed_playbook_failed", slug=pb.slug, error=str(e))
            result.errors.append(f"playbook {pb.slug}: {e}")

    for doc in (*fx.HANDBOOK_DOCS, *fx.VOICE_DOCS):
        try:
            doc_id = ids.handbook_doc_id(ws, doc.slug)
            await dc.execute_mutation("CreateHandbookDocWithId", {
                "id": doc_id, "workspaceId": ws, "slug": doc.slug, "title": doc.title,
                "description": None, "body": doc.body, "blastRadius": doc.blast_radius,
                "kind": doc.kind, "inheritsFromId": None, "triggerExpr": None,
                "affectsSurfaces": json.dumps(doc.affects_surfaces) if doc.affects_surfaces else None,
                "pinned": doc.pinned, "chapterNum": doc.chapter_num,
            })
            await dc.execute_mutation("CreateHandbookVersionWithId", {
                "id": ids.handbook_version_id(ws, doc.slug), "docId": doc_id, "body": doc.body,
            })
            _bump(result.counts, "handbook_docs")
        except Exception as e:
            logger.exception("demo_seed_handbook_failed", slug=doc.slug, error=str(e))
            result.errors.append(f"handbook {doc.slug}: {e}")


# ── tier B: one customer = one sequential pipeline ────────────────────────────


async def _seed_customer(dc: DataConnectClient, ws: str, c: fx.Customer, result: SeedResult) -> None:
    cid = ids.customer_id(ws, c.slug)

    # 1. customer row
    await dc.execute_mutation("CreateCustomerWithId", {
        "id": cid, "workspaceId": ws, "name": c.name, "slug": c.slug, "domain": c.domain,
        "oneLiner": c.one_liner, "tier": c.tier, "arrCents": c.arr_cents,
        "lifecycle": c.lifecycle, "daysToRenewal": c.days_to_renewal,
        "onboardingDayCurrent": c.onboarding_day_current,
        "onboardingDayTotal": c.onboarding_day_total, "renewalReadiness": c.renewal_readiness,
    })
    _bump(result.counts, "customers")

    # 2. relationship health (separate mutation — not on CreateCustomerWithId)
    if c.health:
        await dc.execute_mutation("UpdateCustomerHealth", {
            "customerId": cid, "relationshipHealth": c.health,
            "relationshipHealthScore": c.health_score or 70,
            "relationshipHealthReason": c.health_reason,
            "relationshipHealthUpdatedBy": _SEED_ACTOR,
        })

    # 3. stakeholders (capture id; set champion/renewal flags via follow-up)
    for sh in c.stakeholders:
        res = await dc.execute_mutation("CreateStakeholderPublic", {
            "workspaceId": ws, "customerId": cid, "name": sh.name,
            "email": sh.email, "role": sh.role,
        })
        sid = (res.get("stakeholder_insert") or {}).get("id")
        _bump(result.counts, "stakeholders")
        if sid and (sh.is_champion or sh.renewal_health or sh.status != "active"):
            await dc.execute_mutation("UpdateStakeholderRenewal", {
                "id": sid, "isChampion": sh.is_champion,
                "renewalHealth": sh.renewal_health, "status": sh.status,
            })

    # 4. goals (no client id — capture server ids in fixture order for milestone links).
    # One entry per goal preserves index alignment; an entry is None only if the insert
    # returned no id, in which case the dependent milestone simply gets no goal link.
    goal_ids: list[str | None] = []
    for i, g in enumerate(c.goals):
        res = await dc.execute_mutation("CreateGoalPublic", {
            "workspaceId": ws, "customerId": cid, "text": g.text,
            "status": g.status, "sortOrder": i + 1, "isPrimary": g.is_primary,
        })
        goal_ids.append((res.get("goal_insert") or {}).get("id"))
        _bump(result.counts, "goals")

    # 5. milestones (link goalId by index when present)
    for i, m in enumerate(c.milestones):
        goal_ref = goal_ids[m.goal_index] if m.goal_index is not None and m.goal_index < len(goal_ids) else None
        await dc.execute_mutation("CreateMilestonePublic", {
            "workspaceId": ws, "customerId": cid, "title": m.title,
            "ownerSide": m.owner_side,
            "targetDate": _target_date(m.target_days) if m.target_days is not None else None,
            "status": m.status, "sortOrder": i + 1,
            "goalId": goal_ref, "goalRationale": m.goal_rationale,
        })
        _bump(result.counts, "milestones")

    # 6. threads + backdated interactions
    for t in c.threads:
        tid = ids.thread_id(ws, c.slug, t.key)
        eid = ids.source_event(c.slug, t.key)
        await dc.execute_mutation("CreateThreadWithId", {
            "id": tid, "workspaceId": ws, "customerId": cid, "needId": None,
            "subject": t.subject, "channel": t.channel, "threadType": t.thread_type,
            "status": t.status, "externalThreadId": eid,
        })
        _bump(result.counts, "threads")
        for j, it in enumerate(t.interactions):
            await dc.execute_mutation("CreateInteractionFromEvent", {
                "id": ids.interaction_id(ws, c.slug, t.key, j),
                "workspaceId": ws, "customerId": cid, "threadId": tid,
                "channel": it.channel, "direction": it.direction,
                "senderName": it.sender_name, "stakeholderId": None,
                "subject": it.subject, "body": it.body,
                "sourceEventId": eid, "occurredAt": _ts(-it.days_ago),
                "interactionSource": "demo_seed",
            })
            _bump(result.counts, "interactions")

    # 7. meetings (past = completed, future = scheduled)
    for mt in c.meetings:
        await dc.execute_mutation("CreateMeetingFromCalendarEvent", {
            "id": ids.meeting_id(ws, c.slug, mt.key), "workspaceId": ws, "customerId": cid,
            "title": mt.title, "scheduledAt": _ts(mt.days_from_now),
            "durationMinutes": mt.duration_minutes,
            "attendeesOurs": json.dumps(mt.attendees_ours),
            "attendeesTheirs": json.dumps(mt.attendees_theirs),
            "status": mt.status, "externalEventId": ids.source_event(c.slug, f"meeting:{mt.key}"),
            "recurringEventId": None, "linkStatus": "linked",
        })
        _bump(result.counts, "meetings")

    # 8. pre-baked handoff brief + plan (lane1). Point handbookVersionId at the
    # real core-voice version seeded in tier A (which completes before this runs).
    if c.handoff:
        h = c.handoff
        core_version = ids.handbook_version_id(ws, "core-voice")
        res = await dc.execute_mutation("CreateHandoffBrief", {
            "workspaceId": ws, "customerId": cid, "body": h.body,
            "dayCurrent": h.day_current, "dayTotal": h.day_total,
            "salesCommitments": json.dumps(h.sales_commitments),
            "technicalContext": json.dumps(h.technical_context),
            "realityCheckConfidence": h.confidence, "realityCheckRisks": h.risks,
            "status": "draft", "notionDealId": c.notion_page_id, "notionDealUrl": None,
            "handbookVersionId": core_version, "model": "demo-seed", "promptVersion": "handoff-fixture-v1",
        })
        brief_id = (res.get("handoffBrief_insert") or {}).get("id")
        await dc.execute_mutation("CreateAiPlan", {
            "workspaceId": ws, "customerId": cid, "briefId": brief_id,
            "archetypeName": "Standard SaaS Onboarding", "milestoneCount": len(h.plan_milestones),
            "durationLabel": h.plan_duration_label, "rationale": h.plan_rationale,
            "headline": h.plan_headline, "milestones": json.dumps(h.plan_milestones),
            "model": "demo-seed", "promptVersion": "plan-fixture-v1",
            "inputsHash": ids.source_event(c.slug, "handoff"), "handbookVersionId": core_version,
        })
        _bump(result.counts, "handoff_briefs")

    # 9. current open needs (link thread both ways so Today + Conversations agree).
    # Deliberately does NOT call artifacts.surface_need: ids are deterministic (pre-computed,
    # not surface_need's internal uuid4) and the batch seed fires no Firestore notify — the
    # caller refreshes the UI after /seed-workspace returns rather than per-need pings.
    for n in c.needs:
        nid = ids.need_id(ws, c.slug, n.key)
        tref = ids.thread_id(ws, c.slug, n.thread_key) if n.thread_key else None
        await dc.execute_mutation("CreateNeedWithId", {
            "id": nid, "workspaceId": ws, "customerId": cid, "type": n.type,
            "headline": n.headline, "lede": n.lede, "priorityRank": n.priority_rank,
            "agentReasoning": n.reasoning, "handbookVersionId": None, "agentRunId": None,
            "sourceEventId": ids.source_event(c.slug, f"need:{n.key}"), "threadId": tref,
        })
        if tref and dc.has_operation("LinkThreadToNeed"):
            await dc.execute_mutation("LinkThreadToNeed", {"threadId": tref, "needId": nid})
        _bump(result.counts, "needs")

    # 10. sentiment trajectory → backdated kind=sentiment Signal rows so the customer
    # detail / RightRail sparkline has a real line to plot (state ok|warn|risk maps to
    # 1.0|0.5|0.0 in SentimentTrendService). Explicit per-account series win; otherwise a
    # health-derived default keeps every customer from showing an empty sparkline.
    for i, sp in enumerate(c.sentiment or _sentiment_series(c)):
        note = sp.note or f"{c.name}: sentiment reading ({sp.state})."
        await dc.execute_mutation("CreateDemoSignal", {
            "workspaceId": ws, "customerId": cid,
            "kind": "sentiment", "state": sp.state,
            "sentence": note, "evidenceText": note, "nextAction": None,
            "inputsHash": ids.source_event(c.slug, f"sentiment:{i}"),
            "generatedAt": _ts(-sp.days_ago),
        })
        _bump(result.counts, "signals")
