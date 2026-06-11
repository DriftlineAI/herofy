#!/usr/bin/env python3
"""One-shot Pinecone seed script for the Herofy demo workspace.

Fetches customer strategy memos and recent signals from DataConnect and embeds
them into the Pinecone index so semantic recall is populated before recording
the demo video.

Prerequisites:
    1. Create a Pinecone index named PINECONE_INDEX_NAME (default: herofy-memory)
       with dimension=768 and metric=cosine.
    2. Set PINECONE_API_KEY (and optionally PINECONE_INDEX_NAME) in backend/.env.
    3. Firebase Data Connect emulator must be running (or USE_DATACONNECT_EMULATOR=false
       and ADC credentials configured for production Cloud SQL).

Usage:
    cd backend
    python scripts/seed_pinecone.py                          # seeds default workspace
    python scripts/seed_pinecone.py --workspace-id <uuid>   # target workspace
    python scripts/seed_pinecone.py --dry-run                # list customers, no embed
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend root to sys.path so relative imports work as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must come after sys.path insert)


# ---------------------------------------------------------------------------
# DataConnect bootstrap for standalone use
# ---------------------------------------------------------------------------

async def _init_dc():
    """Initialize the DataConnect singleton outside the FastAPI lifecycle."""
    from db.dataconnect_client import _client as _existing, DataConnectClient
    import db.dataconnect_client as dc_module

    if _existing is not None:
        return  # already initialised

    client = DataConnectClient()
    await client.connect()
    dc_module._client = client


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

DEMO_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
SIGNALS_SINCE_DAYS = 90  # embed signals from the last 90 days


async def seed_workspace(workspace_id: str, dry_run: bool = False) -> None:
    from db.dataconnect_client import get_dataconnect_client
    from orchestrator.memory.pinecone_ingest import ingest_account_memory

    await _init_dc()
    dc = get_dataconnect_client()

    # --- customers -----------------------------------------------------------
    result = await dc.execute_query("GetCustomersPublic", {"workspaceId": workspace_id})
    customers = result.get("customers", [])
    if not customers:
        print(f"No customers found in workspace {workspace_id}. "
              "Make sure the emulator is running and seed data is loaded.")
        return

    print(f"Found {len(customers)} customer(s) in workspace {workspace_id}")

    since_ts = (datetime.now(tz=timezone.utc) - timedelta(days=SIGNALS_SINCE_DAYS)).isoformat()
    seeded = 0

    for customer in customers:
        customer_id = customer["id"]
        customer_name = customer.get("name", customer_id)

        # Strategy memo
        strat_result = await dc.execute_query(
            "GetCustomerStrategy", {"customerId": customer_id}
        )
        strat_rows = strat_result.get("customerStrategies", [])
        strategy_body = (strat_rows[0].get("body", "") if strat_rows else "") or ""

        # Recent signals
        sig_result = await dc.execute_query(
            "GetRecentSignalsForCustomer",
            {"workspaceId": workspace_id, "customerId": customer_id, "since": since_ts},
        )
        signals = sig_result.get("signals", [])

        # HandoffBrief — origin story of the customer relationship
        hb_result = await dc.execute_query(
            "GetLatestHandoffBriefForCustomer", {"customerId": customer_id}
        )
        handoff_briefs = hb_result.get("handoffBriefs", [])

        # Interactions — AI summaries of recent comms (body is encrypted)
        ia_result = await dc.execute_query(
            "GetCustomerInteractions",
            {"workspaceId": workspace_id, "customerId": customer_id, "limit": 20},
        )
        interactions = [i for i in ia_result.get("interactions", []) if i.get("summaryAi")]

        # RiskBriefs — past risk assessments
        rb_result = await dc.execute_query(
            "GetRiskBriefsForCustomer",
            {"workspaceId": workspace_id, "customerId": customer_id},
        )
        risk_briefs = rb_result.get("riskBriefs", [])

        has_content = any([strategy_body.strip(), signals, handoff_briefs, interactions, risk_briefs])
        if not has_content:
            print(f"  skip  {customer_name} — no embeddable content")
            continue

        if dry_run:
            print(f"  [dry] {customer_name}: "
                  f"strategy={'yes' if strategy_body else 'no'}, "
                  f"signals={len(signals)}, "
                  f"handoffs={len(handoff_briefs)}, "
                  f"interactions={len(interactions)}, "
                  f"risk_briefs={len(risk_briefs)}")
            continue

        await ingest_account_memory(
            workspace_id=workspace_id,
            customer_id=customer_id,
            strategy_body=strategy_body,
            signals=signals,
            handoff_briefs=handoff_briefs,
            interactions=interactions,
            risk_briefs=risk_briefs,
        )
        print(f"  ok    {customer_name}: "
              f"strategy={'yes' if strategy_body else 'no'}, "
              f"signals={len(signals)}, "
              f"handoffs={len(handoff_briefs)}, "
              f"interactions={len(interactions)}, "
              f"risk_briefs={len(risk_briefs)}")
        seeded += 1

    if not dry_run:
        print(f"\nDone — seeded {seeded}/{len(customers)} customer(s) into "
              f"index '{settings.pinecone_index_name}'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Pinecone index with Herofy demo workspace memory."
    )
    parser.add_argument(
        "--workspace-id",
        default=DEMO_WORKSPACE_ID,
        help=f"Workspace UUID to seed (default: {DEMO_WORKSPACE_ID})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List customers and content counts without embedding.",
    )
    args = parser.parse_args()

    if not settings.pinecone_api_key:
        print("ERROR: PINECONE_API_KEY is not set. Add it to backend/.env and retry.")
        sys.exit(1)

    if not settings.gemini_api_key:
        print("ERROR: GEMINI_API_KEY is not set. Embeddings require the Gemini API.")
        sys.exit(1)

    print(f"Pinecone index : {settings.pinecone_index_name}")
    print(f"Workspace      : {args.workspace_id}")
    print(f"Dry run        : {args.dry_run}\n")

    asyncio.run(seed_workspace(args.workspace_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
