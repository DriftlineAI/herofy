"""Deterministic IDs for the demo seed.

Every entity id is uuid5(NAMESPACE, f"{workspace_id}:{kind}:{key...}"). Two properties
fall out of this:
  - **Per-workspace uniqueness:** the same fixture seeded into two workspaces produces
    disjoint id sets (so per-visitor demo workspaces never collide).
  - **Stable within a workspace:** re-deriving an id for the same (kind, key) always
    matches, so cross-tier references (a milestone's goalId, a need's threadId) are
    computed locally without ever re-querying the DB — sidestepping the DataConnect
    in-process query-cache caveat that bites the TS seeds.

All ids are returned as plain `str` (DataConnect expects string UUIDs in variables).
"""

import uuid

# Fixed namespace for all Herofy demo ids (random, never changes — changing it would
# orphan every previously-seeded row).
_NS = uuid.UUID("6f1d2c3a-9b47-5e8f-a012-d34e56789abc")


def _id(workspace_id: str, kind: str, *key: str | int) -> str:
    parts = ":".join(str(k) for k in key)
    return str(uuid.uuid5(_NS, f"{workspace_id}:{kind}:{parts}"))


def customer_id(ws: str, slug: str) -> str:
    return _id(ws, "customer", slug)


def stakeholder_id(ws: str, customer_slug: str, email: str) -> str:
    return _id(ws, "stakeholder", customer_slug, email)


def goal_id(ws: str, customer_slug: str, index: int) -> str:
    return _id(ws, "goal", customer_slug, index)


def milestone_id(ws: str, customer_slug: str, index: int) -> str:
    return _id(ws, "milestone", customer_slug, index)


def thread_id(ws: str, customer_slug: str, key: str) -> str:
    return _id(ws, "thread", customer_slug, key)


def interaction_id(ws: str, customer_slug: str, thread_key: str, index: int) -> str:
    return _id(ws, "interaction", customer_slug, thread_key, index)


def meeting_id(ws: str, customer_slug: str, key: str) -> str:
    return _id(ws, "meeting", customer_slug, key)


def need_id(ws: str, customer_slug: str, key: str) -> str:
    return _id(ws, "need", customer_slug, key)


def playbook_id(ws: str, slug: str) -> str:
    return _id(ws, "playbook", slug)


def playbook_milestone_id(ws: str, playbook_slug: str, index: int) -> str:
    return _id(ws, "playbook_milestone", playbook_slug, index)


def handbook_doc_id(ws: str, slug: str) -> str:
    return _id(ws, "handbook_doc", slug)


def handbook_version_id(ws: str, slug: str) -> str:
    return _id(ws, "handbook_version", slug)


# Source-event marker for demo-seeded threads/interactions/needs/meetings. Uses the same
# `demo:{slug}:...` namespace as routes/orchestrator.demo_event_id, but the keys here
# (thread keys, "need:<k>", "meeting:<k>", "handoff") are INTENTIONALLY distinct from the
# per-event `demo:{slug}:{ALL_KINDS}` ids that the route's _reset_demo deletes. That keeps
# fixture rows OUT of _reset_demo's scope, so running /demo-agent on a fixture customer
# layers a live event on top of the lived-in workspace without wiping it. Only the
# workspace-scoped reset_workspace() clears fixture rows.
def source_event(customer_slug: str, key: str) -> str:
    return f"demo:{customer_slug}:{key}"
