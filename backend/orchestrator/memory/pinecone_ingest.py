"""
Pinecone vector store — write (ingest) and read (semantic recall) paths.

Embeds account memory using Gemini text-embedding-004 (768-dim, cosine) and
upserts/queries a Pinecone free-tier index.  Both clients are lazy-initialized
on first use so the module is safe to import when PINECONE_API_KEY is unset.

Tenant isolation: every vector carries workspace_id + customer_id metadata so
queries are always scoped to a single account.

Index requirements (create once in the Pinecone console or CLI):
    dimension : 768
    metric    : cosine
    name      : value of PINECONE_INDEX_NAME (default: "herofy-memory")
"""

import hashlib
from typing import Any

from config import settings
from core.logging import get_logger

logger = get_logger("PineconeStore")

# Module-level singletons — created at most once per process.
_genai_client = None
_pinecone_index = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        _genai_client = genai.Client(api_key=settings.gemini_api_key)
    return _genai_client


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=settings.pinecone_api_key)
        _pinecone_index = pc.Index(settings.pinecone_index_name)
    return _pinecone_index


async def _embed(text: str) -> list[float]:
    """Embed text with gemini-embedding-2 at 768 dimensions (matches Pinecone index)."""
    from google.genai import types as genai_types
    client = _get_genai_client()
    response = await client.aio.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=genai_types.EmbedContentConfig(output_dimensionality=768),
    )
    return response.embeddings[0].values


def _vector_id(customer_id: str, source: str, slot: int | str = 0) -> str:
    """Deterministic ID so repeated ingest upserts (not duplicates) into the same slot.

    Pass an entity ID string (e.g. brief_id, interaction_id) for entity-keyed vectors
    so re-ingest upserts rather than creates duplicates.
    """
    raw = f"{customer_id}:{source}:{slot}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------

async def ingest_account_memory(
    workspace_id: str,
    customer_id: str,
    strategy_body: str = "",
    event_summary: str = "",
    signals: list[dict[str, Any]] | None = None,
    handoff_briefs: list[dict[str, Any]] | None = None,
    interactions: list[dict[str, Any]] | None = None,
    risk_briefs: list[dict[str, Any]] | None = None,
) -> None:
    """Embed and upsert account memory into Pinecone.

    Content types embedded:
      strategy_body  — reconciled CustomerStrategy memo (highest signal density)
      event_summary  — triggering event from consolidation context
      signals        — recent signals (kind + sentence fields from DataConnect)
      handoff_briefs — HandoffBrief body + salesCommitments + technicalContext
      interactions   — Interaction summaryAi + subject (body is encrypted; skip if null)
      risk_briefs    — RiskBrief whatChanged + evidenceText + play

    Silently no-ops when PINECONE_API_KEY is not set.
    Called best-effort from consolidate_account_memory() — never raises.
    """
    if not settings.pinecone_api_key:
        return

    try:
        index = _get_pinecone_index()
        vectors = []
        base_meta = {"workspace_id": workspace_id, "customer_id": customer_id}

        # Strategy memo — primary artifact; highest signal density.
        body = (strategy_body or "").strip()
        if body and body != "(none yet)":
            embedding = await _embed(body[:3000])
            vectors.append({
                "id": _vector_id(customer_id, "strategy"),
                "values": embedding,
                "metadata": {**base_meta, "source": "strategy", "text": body[:500]},
            })

        # Triggering event summary (from consolidation context).
        summary = (event_summary or "").strip()
        if summary:
            embedding = await _embed(summary[:2000])
            vectors.append({
                "id": _vector_id(customer_id, "event"),
                "values": embedding,
                "metadata": {**base_meta, "source": "event", "text": summary[:500]},
            })

        # Recent signals (kind + sentence from DataConnect).
        for i, sig in enumerate((signals or [])[:10]):
            sig_text = f"{sig.get('kind', '')} — {sig.get('sentence', sig.get('body', sig.get('summary', '')))}".strip(" —")
            if not sig_text:
                continue
            embedding = await _embed(sig_text[:2000])
            vectors.append({
                "id": _vector_id(customer_id, "signal", i),
                "values": embedding,
                "metadata": {**base_meta, "source": "signal", "text": sig_text[:500]},
            })

        # HandoffBriefs — origin story of the relationship.
        for brief in (handoff_briefs or []):
            hb_text = " ".join(filter(None, [
                brief.get("body", ""),
                brief.get("salesCommitments", ""),
                brief.get("technicalContext", ""),
            ])).strip()
            if not hb_text:
                continue
            embedding = await _embed(hb_text[:3000])
            vectors.append({
                "id": _vector_id(customer_id, "handoff", brief.get("id", "0")),
                "values": embedding,
                "metadata": {**base_meta, "source": "handoff", "text": hb_text[:500]},
            })

        # Interactions — AI summaries of recent comms (body is encrypted; use summaryAi).
        for ia in (interactions or []):
            ai_summary = (ia.get("summaryAi") or "").strip()
            if not ai_summary:
                continue
            ia_text = f"{ia.get('subject', '')} — {ai_summary}".strip(" —")
            embedding = await _embed(ia_text[:2000])
            vectors.append({
                "id": _vector_id(customer_id, "interaction", ia.get("id", "0")),
                "values": embedding,
                "metadata": {**base_meta, "source": "interaction", "text": ia_text[:500]},
            })

        # RiskBriefs — past risk assessments and save plays.
        for rb in (risk_briefs or []):
            rb_text = " ".join(filter(None, [
                rb.get("whatChanged", ""),
                rb.get("evidenceText", ""),
                rb.get("play", ""),
            ])).strip()
            if not rb_text:
                continue
            embedding = await _embed(rb_text[:3000])
            vectors.append({
                "id": _vector_id(customer_id, "risk_brief", rb.get("id", "0")),
                "values": embedding,
                "metadata": {**base_meta, "source": "risk_brief", "text": rb_text[:500]},
            })

        if vectors:
            index.upsert(vectors=vectors)
            logger.info("pinecone_ingest_ok", customer_id=customer_id, vectors=len(vectors))

    except Exception as e:
        logger.warning("pinecone_ingest_failed", customer_id=customer_id, error=str(e))


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------

async def vector_recall_semantic(
    query: str,
    workspace_id: str,
    customer_id: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Query Pinecone for semantically similar memory chunks.

    Returns [] immediately when PINECONE_API_KEY is unset (graceful no-op).
    Never raises — errors are logged and swallowed.
    """
    if not settings.pinecone_api_key:
        return []

    try:
        query_vector = await _embed(query[:2000])

        metadata_filter: dict[str, Any] = {"workspace_id": workspace_id}
        if customer_id:
            metadata_filter["customer_id"] = customer_id

        index = _get_pinecone_index()
        response = index.query(
            vector=query_vector,
            top_k=top_k,
            filter=metadata_filter,
            include_metadata=True,
        )

        return [
            {
                "text": (match.metadata or {}).get("text", ""),
                "score": round(match.score or 0.0, 3),
                "source": (match.metadata or {}).get("source", "unknown"),
                "customer_id": (match.metadata or {}).get("customer_id"),
            }
            for match in (response.matches or [])
        ]

    except Exception as e:
        logger.warning("vector_recall_failed", query=query[:80], error=str(e))
        return []
