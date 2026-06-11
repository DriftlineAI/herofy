"""
AI Routes
FastAPI endpoints for AI-powered features (draft generation, plan regeneration)
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from middleware.auth import FirebaseUser, require_workspace_access
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

router = APIRouter(prefix="/workspaces", tags=["ai"])
logger = get_logger("ai_routes")


# =============================================================================
# Request/Response Models
# =============================================================================


class GenerateDraftRequest(BaseModel):
    """Request to generate an AI draft response."""
    instructions: Optional[str] = None


class GenerateDraftResponse(BaseModel):
    """Response from draft generation."""
    success: bool
    draft_id: Optional[str] = None
    draft_body: Optional[str] = None
    message: Optional[str] = None


class RegeneratePlanResponse(BaseModel):
    """Response from plan regeneration."""
    success: bool
    plan_id: Optional[str] = None
    message: Optional[str] = None


# =============================================================================
# Draft Generation
# =============================================================================


@router.post("/{workspace_id}/threads/{thread_id}/draft/generate")
async def generate_draft(
    workspace_id: str,
    thread_id: str,
    request: GenerateDraftRequest,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> GenerateDraftResponse:
    """
    Generate an AI draft response for a thread.

    The AI analyzes the thread context and generates a suggested response.
    The draft is stored in the database for user review/editing.
    """
    logger.info(
        "draft_generation_requested",
        workspace_id=workspace_id,
        thread_id=thread_id,
        has_instructions=bool(request.instructions),
    )

    try:
        dc = get_dataconnect_client()

        # Verify thread exists and belongs to workspace
        result = await dc.execute_query("GetThread", {"id": thread_id})
        thread = result.get("thread")

        if not thread or thread.get("workspace", {}).get("id") != workspace_id:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Thread not found"},
            )

        # Generate synchronously: the client awaits this POST (showing a "drafting…" state) and
        # refetches the draft on completion. A background task returns before the draft is saved,
        # so the client's refetch would miss it — the draft would only appear on a manual refresh.
        result = await _generate_draft_background(
            workspace_id,
            thread_id,
            request.instructions,
        )
        completed = (result or {}).get("status") == "completed"
        return GenerateDraftResponse(
            success=completed,
            draft_id=(result or {}).get("draft_id"),
            draft_body=(result or {}).get("draft_body"),
            message="Draft generated" if completed else "Draft generation failed",
        )

    except Exception as e:
        logger.exception("draft_generation_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)},
        )


async def _generate_draft_background(
    workspace_id: str,
    thread_id: str,
    instructions: Optional[str],
) -> dict:
    """Generate + save an AI draft. Returns the service result so the (now synchronous) caller can
    report status/draft_id to the client."""
    try:
        from services.draft_generation_service import DraftGenerationService

        service = DraftGenerationService(workspace_id)
        result = await service.generate_and_save_draft(
            thread_id=thread_id,
            instructions=instructions,
        )

        logger.info(
            "draft_generated",
            thread_id=thread_id,
            model=result.get("model"),
            status=result.get("status"),
        )
        return result or {}

    except Exception as e:
        logger.exception("draft_generation_background_error", error=str(e))
        return {"status": "failed", "error": str(e)}


class SendDraftRequest(BaseModel):
    edited_body: Optional[str] = None


@router.post("/{workspace_id}/threads/{thread_id}/draft/send")
async def send_draft(
    workspace_id: str,
    thread_id: str,
    request: SendDraftRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> dict:
    """Send a reviewed draft on a thread. SIMULATES the send (no real email — not wired to
    Gmail/SMTP yet): posts the draft as an outbound interaction, marks it sent, moves the Need to
    awaiting_customer, and auto-completes the matching save-play step. The single send action also
    used by the HITL 'approve' resume. Runs under the caller's request-scoped impersonation."""
    from orchestrator.artifacts import send_draft_response
    logger.info("draft_send_requested", workspace_id=workspace_id, thread_id=thread_id)
    result = await send_draft_response(thread_id, edited_body=request.edited_body)
    if result is None:
        return {"status": "no_draft"}
    return {"status": "sent", **result}


# =============================================================================
# Plan Regeneration
# =============================================================================


@router.post("/{workspace_id}/plans/{plan_id}/regenerate")
async def regenerate_plan(
    workspace_id: str,
    plan_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> RegeneratePlanResponse:
    """
    Regenerate an AI onboarding plan.

    Creates a new plan based on the handoff brief and playbook templates.
    The old plan is archived and a new one is created.
    """
    logger.info(
        "plan_regeneration_requested",
        workspace_id=workspace_id,
        plan_id=plan_id,
    )

    try:
        dc = get_dataconnect_client()

        # Verify plan exists and belongs to workspace
        result = await dc.execute_query("GetPlan", {"id": plan_id})
        plan = result.get("aiPlan")

        # Check workspace via brief
        brief = plan.get("brief") if plan else None
        if not plan or not brief:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Plan not found"},
            )

        # Queue plan regeneration in background
        background_tasks.add_task(
            _regenerate_plan_background,
            workspace_id,
            plan_id,
            brief.get("id"),
        )

        return RegeneratePlanResponse(
            success=True,
            message="Plan regeneration started",
        )

    except Exception as e:
        logger.exception("plan_regeneration_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)},
        )


async def _regenerate_plan_background(
    workspace_id: str,
    old_plan_id: str,
    brief_id: str,
):
    """Background task to regenerate a plan."""
    try:
        from db.dataconnect_client import get_dataconnect_client
        import json

        dc = get_dataconnect_client()

        # Get the handoff brief
        result = await dc.execute_query("GetHandoff", {"id": brief_id})
        brief = result.get("handoffBrief")

        if not brief:
            logger.error("brief_not_found", brief_id=brief_id)
            return

        # Archive the old plan
        await dc.execute_mutation("ArchivePlan", {"id": old_plan_id})

        # TODO: Call Gemini to generate new plan
        # For now, create a placeholder plan
        new_milestones = [
            {
                "title": "Kickoff Call",
                "owner_side": "joint",
                "duration_days": 3,
                "description": "Initial kickoff meeting with stakeholders",
            },
            {
                "title": "Technical Setup",
                "owner_side": "customer",
                "duration_days": 7,
                "description": "Customer completes technical integration",
            },
            {
                "title": "Training Session",
                "owner_side": "ours",
                "duration_days": 5,
                "description": "Conduct training for end users",
            },
            {
                "title": "Go Live",
                "owner_side": "joint",
                "duration_days": 3,
                "description": "Launch and initial support",
            },
        ]

        # Get regeneration count from old plan
        old_plan_result = await dc.execute_query("GetPlan", {"id": old_plan_id})
        old_plan = old_plan_result.get("aiPlan")
        regen_count = (old_plan.get("regenerationCount") or 0) + 1 if old_plan else 1

        # Extract customer from brief
        customer = brief.get("customer")
        customer_id = customer.get("id") if customer else None

        # Create new plan
        await dc.execute_mutation(
            "CreateAiPlan",
            {
                "workspaceId": workspace_id,
                "customerId": customer_id,
                "briefId": brief_id,
                "milestones": json.dumps(new_milestones),
                "milestoneCount": len(new_milestones),
                "durationLabel": f"{sum(m['duration_days'] for m in new_milestones)} days",
                "headline": "Regenerated Onboarding Plan",
                "rationale": "Plan regenerated based on updated requirements",
                "model": "gemini-2.5-flash",  # Audit trail only - TODO: Use get_model() when LLM call added
                "promptVersion": "v1",
                "inputsHash": "",
                "handbookVersionId": None,
            },
        )

        logger.info(
            "plan_regenerated",
            old_plan_id=old_plan_id,
            new_plan_id=new_plan_id,
            regeneration_count=regen_count,
        )

    except Exception as e:
        logger.exception("plan_regeneration_background_error", error=str(e))


# =============================================================================
# Plan Approval with Milestone Activation
# =============================================================================


class ApproveAndActivateResponse(BaseModel):
    """Response from plan approval and activation."""
    success: bool
    plan_id: Optional[str] = None
    milestones_created: int = 0
    message: Optional[str] = None


@router.post("/{workspace_id}/plans/{plan_id}/approve-and-activate")
async def approve_and_activate_plan(
    workspace_id: str,
    plan_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ApproveAndActivateResponse:
    """
    Approve a plan AND create Milestone records for the customer.

    This endpoint handles the full plan approval flow:
    1. Updates AiPlan status to 'approved'
    2. Parses AiPlan.milestones JSON
    3. Creates Milestone records linked to customer
    4. Resolves the associated plan_approval_required Need (if any)

    This is the critical integration that makes milestones actionable
    after plan approval.
    """
    import json
    from datetime import date, timedelta

    logger.info(
        "plan_approval_activation_requested",
        workspace_id=workspace_id,
        plan_id=plan_id,
        user_id=user.uid,
    )

    try:
        dc = get_dataconnect_client()

        # 1. Get the plan
        result = await dc.execute_query("GetPlanPublic", {"id": plan_id})
        plan = result.get("aiPlan")

        if not plan:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Plan not found"},
            )

        # Verify workspace matches
        customer = plan.get("customer", {})
        plan_workspace = customer.get("workspace", {}).get("id")
        if plan_workspace and plan_workspace != workspace_id:
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Plan does not belong to this workspace"},
            )

        customer_id = customer.get("id")
        if not customer_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Plan has no customer"},
            )

        # Check if already approved
        if plan.get("status") == "approved":
            return ApproveAndActivateResponse(
                success=True,
                plan_id=plan_id,
                milestones_created=0,
                message="Plan was already approved",
            )

        # 2. Approve the plan
        await dc.execute_mutation("ApprovePlan", {"id": plan_id})
        logger.info("plan_approved", plan_id=plan_id)

        # 3. Parse milestones and create Milestone records
        milestones_json = plan.get("milestones", "[]")
        try:
            milestones = json.loads(milestones_json) if isinstance(milestones_json, str) else milestones_json
            if not isinstance(milestones, list):
                milestones = []
        except json.JSONDecodeError:
            logger.warning("plan_milestones_parse_error", plan_id=plan_id)
            milestones = []

        start_date = date.today()
        created_count = 0
        cumulative_days = 0

        for idx, m in enumerate(milestones):
            # Calculate target date from duration
            # Support both target_days (absolute) and duration_days (relative)
            duration = m.get("duration_days") or m.get("durationDays") or m.get("target_days") or m.get("target_day") or 7
            cumulative_days += duration
            target_date = start_date + timedelta(days=cumulative_days)

            # Determine owner side
            owner_side_raw = m.get("owner_side") or m.get("ownerSide") or "joint"
            # Normalize to expected enum value
            owner_side = owner_side_raw.lower()
            if owner_side not in ["us", "customer", "joint"]:
                owner_side = "joint"

            # Preserve goal linkage from the plan onto the live, actionable milestone.
            # Supports both snake_case (agent JSON) and camelCase (edited via SDK).
            goal_id = m.get("goal_id") or m.get("goalId")
            goal_rationale = m.get("goal_rationale") or m.get("goalRationale")

            try:
                await dc.execute_mutation(
                    "CreateMilestonePublic",
                    {
                        "workspaceId": workspace_id,
                        "customerId": customer_id,
                        "title": m.get("title", f"Milestone {idx + 1}"),
                        "ownerSide": owner_side,
                        "targetDate": target_date.isoformat(),
                        "status": "not_started",
                        "sortOrder": idx,
                        "goalId": goal_id,
                        "goalRationale": goal_rationale,
                    },
                )
                created_count += 1
            except Exception as e:
                logger.warning(
                    "milestone_creation_failed",
                    plan_id=plan_id,
                    milestone_idx=idx,
                    error=str(e),
                )

        logger.info(
            "milestones_created_from_plan",
            plan_id=plan_id,
            customer_id=customer_id,
            count=created_count,
        )

        # 4. Resolve the associated plan_approval_required Need (if any)
        # Find the need by type and customer
        try:
            needs_result = await dc.execute_query(
                "GetTodayQueue",
                {"workspaceId": workspace_id},
            )
            needs = needs_result.get("needs", [])

            for need in needs:
                if (
                    need.get("type") == "plan_approval_required"
                    and need.get("customer", {}).get("id") == customer_id
                    and not need.get("resolvedAt")
                ):
                    await dc.execute_mutation("ResolveNeed", {"id": need.get("id")})
                    logger.info(
                        "plan_approval_need_resolved",
                        need_id=need.get("id"),
                        customer_id=customer_id,
                    )
                    break
        except Exception as e:
            logger.warning(
                "need_resolution_failed",
                plan_id=plan_id,
                error=str(e),
            )

        return ApproveAndActivateResponse(
            success=True,
            plan_id=plan_id,
            milestones_created=created_count,
            message=f"Plan approved and {created_count} milestones created",
        )

    except Exception as e:
        logger.exception("plan_approval_activation_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)},
        )


# =============================================================================
# Manual plan creation (instantiate a playbook as a customer's plan)
# =============================================================================


class PlanFromPlaybookRequest(BaseModel):
    """Instantiate one of the workspace's playbook templates as a live plan."""
    playbook_id: str


class PlanFromPlaybookResponse(BaseModel):
    success: bool
    plan_id: Optional[str] = None  # the Goal id that anchors the new plan
    milestones_created: int = 0
    message: str


@router.post("/{workspace_id}/customers/{customer_id}/plans/from-playbook")
async def create_plan_from_playbook(
    workspace_id: str,
    customer_id: str,
    request: PlanFromPlaybookRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> PlanFromPlaybookResponse:
    """Manually instantiate a workspace playbook as a plan for a customer.

    A "plan" here is a Goal that anchors a set of Milestones. This mirrors the AI
    approve-and-activate path deterministically: it creates a Goal named after the
    playbook, then materializes each PlaybookMilestone as a real Milestone with a
    target date computed from cumulative durationDays. No LLM — pure templating, so
    the CSM can spin up a standard plan in one click and edit from there.
    """
    from datetime import date, timedelta

    logger.info(
        "plan_from_playbook_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        playbook_id=request.playbook_id,
        user_id=user.uid,
    )

    try:
        dc = get_dataconnect_client()

        # 1. Resolve the playbook (with its templated milestones) within this workspace.
        playbooks = (await dc.execute_query(
            "GetPlaybooksPublic", {"workspaceId": workspace_id}
        )).get("playbooks", [])
        playbook = next((p for p in playbooks if p.get("id") == request.playbook_id), None)
        if not playbook:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Playbook not found in this workspace"},
            )

        steps = playbook.get("playbookMilestones_on_playbook") or []

        # 2. Create the Goal that anchors the plan (non-primary so we never collide with
        #    an existing Mission Objective; the CSM can promote it later).
        goal_res = await dc.execute_mutation("CreateGoalPublic", {
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "text": playbook.get("name") or "New plan",
            "status": "active",
            "sortOrder": 0,
            "isPrimary": False,
        })
        goal_id = (goal_res.get("goal_insert") or {}).get("id")
        if not goal_id:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Could not create the plan (no goal id returned)"},
            )

        # 3. Materialize each templated step as a live, goal-linked Milestone.
        start_date = date.today()
        cumulative_days = 0
        created = 0
        for idx, s in enumerate(steps):
            duration = s.get("durationDays") or 7
            cumulative_days += duration
            target_date = start_date + timedelta(days=cumulative_days)
            owner_side = (s.get("ownerSide") or "joint").lower()
            if owner_side not in ("us", "customer", "joint"):
                owner_side = "joint"
            try:
                await dc.execute_mutation("CreateMilestonePublic", {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "title": s.get("title", f"Step {idx + 1}"),
                    "ownerSide": owner_side,
                    "targetDate": target_date.isoformat(),
                    "status": "not_started",
                    "sortOrder": idx,
                    "goalId": goal_id,
                    "goalRationale": s.get("description"),
                })
                created += 1
            except Exception as e:
                logger.warning("plan_from_playbook_milestone_failed", idx=idx, error=str(e))

        logger.info(
            "plan_from_playbook_created",
            workspace_id=workspace_id,
            customer_id=customer_id,
            goal_id=goal_id,
            milestones=created,
        )
        return PlanFromPlaybookResponse(
            success=True,
            plan_id=goal_id,
            milestones_created=created,
            message=f"Created plan from '{playbook.get('name')}' with {created} milestones",
        )

    except Exception as e:
        logger.exception("plan_from_playbook_error", error=str(e))
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


# =============================================================================
# Customer Classification
# =============================================================================


class ClassifyCustomersRequest(BaseModel):
    """Request to classify customers during setup."""
    customer_ids: Optional[list[str]] = None  # If None, classify all imported customers


class CustomerClassificationResult(BaseModel):
    """Classification result for a single customer."""
    customer_id: str
    group: str  # not_yet_customer, new_customer, pointer_needed, ready_to_confirm
    confidence: int
    reasoning: str
    what_i_know: list[str]
    what_im_uncertain_about: list[str]
    suggested_playbook: Optional[str] = None
    playbook_code: Optional[str] = None
    current_state: Optional[str] = None
    next_milestone: Optional[str] = None


class ClassifyCustomersResponse(BaseModel):
    """Response from customer classification."""
    success: bool
    classifications: list[CustomerClassificationResult]
    message: Optional[str] = None


@router.post("/{workspace_id}/ai/classify-customers")
async def classify_customers(
    workspace_id: str,
    request: ClassifyCustomersRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ClassifyCustomersResponse:
    """
    Classify customers during setup using AI.

    Analyzes CRM data + linked Notion pages to determine:
    - Which grouping each customer belongs to
    - Confidence score
    - Reasoning for the Sidekick panel
    - What Sidekick knows vs is uncertain about

    This is called during the setup flow after importing customers.
    """
    logger.info(
        "customer_classification_requested",
        workspace_id=workspace_id,
        customer_ids=request.customer_ids,
    )

    try:
        from db.dataconnect_client import get_dataconnect_client
        from services.customer_classifier import CustomerClassifier, CustomerInput
        from services.firestore_service import get_firestore_service

        dc = get_dataconnect_client()
        classifier = CustomerClassifier(workspace_id)
        firestore = get_firestore_service()

        # Get customers to classify
        if request.customer_ids:
            # Specific customers
            customers_data = []
            for cid in request.customer_ids:
                customer = await dc.get_customer(customer_id=cid)
                if customer:
                    customers_data.append(customer)
        else:
            # All customers in workspace
            customers_data = await dc.get_customers(workspace_id=workspace_id)

        if not customers_data:
            return ClassifyCustomersResponse(
                success=True,
                classifications=[],
                message="No customers to classify",
            )

        # Get linked pages for each customer (if any)
        # For now, we'll check the customer's linked_pages field
        # In future, we can fetch content from Notion API
        customer_inputs = []
        for c in customers_data:
            # Parse linked_pages JSON if present
            linked_pages = []
            linked_pages_raw = c.get('linkedPages') or c.get('linked_pages')
            if linked_pages_raw:
                try:
                    import json
                    pages = json.loads(linked_pages_raw) if isinstance(linked_pages_raw, str) else linked_pages_raw
                    linked_pages = pages if isinstance(pages, list) else []
                except:
                    pass

            customer_inputs.append(CustomerInput(
                customer_id=c.get('id'),
                customer_name=c.get('name'),
                lifecycle=c.get('lifecycle'),
                tier=c.get('tier'),
                arr_cents=c.get('arrCents') or c.get('arr_cents'),
                days_as_customer=c.get('daysAsCustomer') or c.get('days_as_customer'),
                onboarding_day_current=c.get('onboardingDayCurrent') or c.get('onboarding_day_current'),
                onboarding_day_total=c.get('onboardingDayTotal') or c.get('onboarding_day_total'),
                raw_notes=c.get('rawNotes') or c.get('notes'),
                linked_pages=linked_pages,
            ))

        # Classify all customers
        results = await classifier.classify_customers(customer_inputs)

        # Save classifications to database and Firestore
        import json
        for r in results:
            try:
                await dc.execute_mutation(
                    "UpdateCustomerClassification",
                    {
                        "id": r.customer_id,
                        "group": r.group,
                        "confidence": r.confidence,
                        "reasoning": r.reasoning,
                        "whatIKnow": json.dumps(r.what_i_know) if r.what_i_know else None,
                        "uncertainties": json.dumps(r.what_im_uncertain_about) if r.what_im_uncertain_about else None,
                    },
                )

                # Also update Firestore for real-time UI updates
                await firestore.update_setup_progress(
                    workspace_id=workspace_id,
                    customer_id=r.customer_id,
                    status="classified",
                    progress={
                        "group": r.group,
                        "confidence": r.confidence,
                        "reasoning": r.reasoning,
                        "progress_pct": 100,
                        "step": "Classified",
                    },
                )
            except Exception as e:
                logger.warning(
                    "classification_save_failed",
                    customer_id=r.customer_id,
                    error=str(e),
                )

        # Convert to response format
        classifications = [
            CustomerClassificationResult(
                customer_id=r.customer_id,
                group=r.group,
                confidence=r.confidence,
                reasoning=r.reasoning,
                what_i_know=r.what_i_know,
                what_im_uncertain_about=r.what_im_uncertain_about,
                suggested_playbook=r.suggested_playbook,
                playbook_code=r.playbook_code,
                current_state=r.current_state,
                next_milestone=r.next_milestone,
            )
            for r in results
        ]

        logger.info(
            "customer_classification_complete",
            workspace_id=workspace_id,
            total=len(classifications),
            groups={
                "not_yet_customer": sum(1 for c in classifications if c.group == "not_yet_customer"),
                "new_customer": sum(1 for c in classifications if c.group == "new_customer"),
                "pointer_needed": sum(1 for c in classifications if c.group == "pointer_needed"),
                "ready_to_confirm": sum(1 for c in classifications if c.group == "ready_to_confirm"),
            },
        )

        return ClassifyCustomersResponse(
            success=True,
            classifications=classifications,
        )

    except Exception as e:
        logger.exception("customer_classification_error", error=str(e))
        return ClassifyCustomersResponse(
            success=False,
            classifications=[],
            message=str(e),
        )


# =============================================================================
# Manual Classification Override
# =============================================================================


class UpdateClassificationRequest(BaseModel):
    """Request to manually update a customer's classification."""
    group: str  # not_yet_customer, new_customer, pointer_needed, ready_to_confirm
    confidence: int = 100
    reasoning: Optional[str] = None


class UpdateClassificationResponse(BaseModel):
    """Response from updating classification."""
    success: bool
    message: Optional[str] = None


# =============================================================================
# Streaming Customer Classification (Real-time via Firestore)
# =============================================================================


class StreamingClassifyRequest(BaseModel):
    """Request to start streaming classification."""
    customer_ids: Optional[list[str]] = None  # If None, classify all customers


class StreamingClassifyResponse(BaseModel):
    """Response from starting streaming classification."""
    success: bool
    workspace_id: str
    customer_count: int
    message: Optional[str] = None


@router.post("/{workspace_id}/ai/classify-customers-streaming")
async def classify_customers_streaming(
    workspace_id: str,
    request: StreamingClassifyRequest,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> StreamingClassifyResponse:
    """
    Start streaming customer classification with real-time updates via Firestore.

    Unlike the batch endpoint, this returns immediately and processes customers
    one-by-one in the background. Progress updates are pushed to Firestore
    at setup_progress/{workspace_id} for the frontend to subscribe to.

    Flow:
    1. Frontend calls this endpoint
    2. Endpoint returns immediately with customer count
    3. Background task processes each customer:
       - Updates Firestore status to 'reading'
       - Classifies customer
       - Updates Firestore status to 'classified' with results
       - Saves to CloudSQL
    4. Frontend receives live updates via Firestore subscription
    """
    logger.info(
        "streaming_classification_started",
        workspace_id=workspace_id,
        customer_ids=request.customer_ids,
    )

    try:
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        # Get customers to classify
        if request.customer_ids:
            customers_data = []
            for cid in request.customer_ids:
                customer = await dc.get_customer(customer_id=cid)
                if customer:
                    customers_data.append(customer)
        else:
            customers_data = await dc.get_customers(workspace_id=workspace_id)

        if not customers_data:
            return StreamingClassifyResponse(
                success=True,
                workspace_id=workspace_id,
                customer_count=0,
                message="No customers to classify",
            )

        # Queue background classification
        background_tasks.add_task(
            _classify_customers_streaming_background,
            workspace_id,
            customers_data,
        )

        return StreamingClassifyResponse(
            success=True,
            workspace_id=workspace_id,
            customer_count=len(customers_data),
            message=f"Classification started for {len(customers_data)} customers",
        )

    except Exception as e:
        logger.exception("streaming_classification_start_error", error=str(e))
        return StreamingClassifyResponse(
            success=False,
            workspace_id=workspace_id,
            customer_count=0,
            message=str(e),
        )


async def _classify_customers_streaming_background(
    workspace_id: str,
    customers_data: list[dict],
):
    """
    Background task that classifies customers and pushes updates to Firestore.

    This runs one customer at a time, updating Firestore after each step
    so the frontend can show real-time progress.
    """
    import json
    from services.firestore_service import get_firestore_service
    from services.customer_classifier import CustomerClassifier, CustomerInput
    from db.dataconnect_client import get_dataconnect_client

    try:
        firestore_service = get_firestore_service()
    except Exception as e:
        logger.error("firestore_service_unavailable", error=str(e))
        firestore_service = None

    dc = get_dataconnect_client()
    classifier = CustomerClassifier(workspace_id)

    for i, customer in enumerate(customers_data):
        customer_id = customer.get('id')
        customer_name = customer.get('name', 'Unknown')

        try:
            # Step 1: Mark as 'reading'
            if firestore_service:
                await firestore_service.update_setup_progress(
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    status='reading',
                    progress={
                        'step': 'Fetching customer data',
                        'progress_pct': 10,
                        'customer_name': customer_name,
                        'index': i,
                        'total': len(customers_data),
                    },
                )

            # Parse linked pages
            linked_pages = []
            linked_pages_raw = customer.get('linkedPages') or customer.get('linked_pages')
            if linked_pages_raw:
                try:
                    pages = json.loads(linked_pages_raw) if isinstance(linked_pages_raw, str) else linked_pages_raw
                    linked_pages = pages if isinstance(pages, list) else []
                except:
                    pass

            # Build input for classifier
            customer_input = CustomerInput(
                customer_id=customer_id,
                customer_name=customer_name,
                lifecycle=customer.get('lifecycle'),
                tier=customer.get('tier'),
                arr_cents=customer.get('arrCents') or customer.get('arr_cents'),
                days_as_customer=customer.get('daysAsCustomer') or customer.get('days_as_customer'),
                onboarding_day_current=customer.get('onboardingDayCurrent') or customer.get('onboarding_day_current'),
                onboarding_day_total=customer.get('onboardingDayTotal') or customer.get('onboarding_day_total'),
                raw_notes=customer.get('rawNotes') or customer.get('notes'),
                linked_pages=linked_pages,
            )

            # Step 2: Update to 'analyzing'
            if firestore_service:
                await firestore_service.update_setup_progress(
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    status='reading',
                    progress={
                        'step': 'Analyzing with AI',
                        'progress_pct': 50,
                        'customer_name': customer_name,
                        'index': i,
                        'total': len(customers_data),
                    },
                )

            # Classify
            result = await classifier.classify_customer(customer_input)

            # Step 3: Save to CloudSQL
            try:
                await dc.execute_mutation(
                    "UpdateCustomerClassification",
                    {
                        "id": customer_id,
                        "group": result.group,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                        "whatIKnow": json.dumps(result.what_i_know) if result.what_i_know else None,
                        "uncertainties": json.dumps(result.what_im_uncertain_about) if result.what_im_uncertain_about else None,
                    },
                )
            except Exception as e:
                logger.warning(
                    "classification_save_failed",
                    customer_id=customer_id,
                    error=str(e),
                )

            # Step 4: Update Firestore to 'classified'
            if firestore_service:
                await firestore_service.update_setup_progress(
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    status='classified',
                    progress={
                        'group': result.group,
                        'confidence': result.confidence,
                        'reasoning': result.reasoning,
                        'what_i_know': result.what_i_know,
                        'what_im_uncertain_about': result.what_im_uncertain_about,
                        'suggested_playbook': result.suggested_playbook,
                        'playbook_code': result.playbook_code,
                        'current_state': result.current_state,
                        'next_milestone': result.next_milestone,
                        'customer_name': customer_name,
                        'index': i,
                        'total': len(customers_data),
                    },
                )

            logger.info(
                "streaming_classification_customer_done",
                customer_id=customer_id,
                group=result.group,
                progress=f"{i+1}/{len(customers_data)}",
            )

        except Exception as e:
            logger.error(
                "streaming_classification_customer_error",
                customer_id=customer_id,
                error=str(e),
            )

            # Mark as error in Firestore
            if firestore_service:
                await firestore_service.update_setup_progress(
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    status='error',
                    progress={
                        'error': str(e),
                        'customer_name': customer_name,
                        'index': i,
                        'total': len(customers_data),
                    },
                )

    logger.info(
        "streaming_classification_complete",
        workspace_id=workspace_id,
        total=len(customers_data),
    )


# =============================================================================
# Manual Classification Override
# =============================================================================


@router.put("/{workspace_id}/customers/{customer_id}/classification")
async def update_customer_classification(
    workspace_id: str,
    customer_id: str,
    request: UpdateClassificationRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> UpdateClassificationResponse:
    """
    Manually update a customer's classification.

    Used when the user wants to override the AI classification,
    e.g., marking a customer as "not in onboarding" (ready_to_confirm).
    """
    import json

    logger.info(
        "manual_classification_update",
        workspace_id=workspace_id,
        customer_id=customer_id,
        group=request.group,
    )

    try:
        from db.dataconnect_client import get_dataconnect_client
        from services.firestore_service import get_firestore_service

        dc = get_dataconnect_client()
        firestore = get_firestore_service()

        # Update customer classification in database
        await dc.execute_mutation(
            "UpdateCustomerClassification",
            {
                "id": customer_id,
                "group": request.group,
                "confidence": request.confidence,
                "reasoning": request.reasoning or f"Manually set to {request.group} by user",
                "whatIKnow": json.dumps(["Manually classified by user"]),
                "uncertainties": json.dumps([]),
            },
        )

        # Also update Firestore so the UI reflects the change immediately
        await firestore.update_setup_progress(
            workspace_id=workspace_id,
            customer_id=customer_id,
            status="classified",
            progress={
                "group": request.group,
                "confidence": request.confidence,
                "reasoning": request.reasoning or f"Manually set to {request.group} by user",
                "progress_pct": 100,
                "step": "User override",
            },
        )

        logger.info(
            "manual_classification_updated",
            customer_id=customer_id,
            group=request.group,
        )

        return UpdateClassificationResponse(success=True)

    except Exception as e:
        logger.exception("manual_classification_error", error=str(e))
        return UpdateClassificationResponse(
            success=False,
            message=str(e),
        )


# =============================================================================
# Playbook Generation from Natural Language
# =============================================================================


class GeneratePlaybookRequest(BaseModel):
    """Request to generate a playbook from natural language."""
    description: str


class PlaybookMilestoneResult(BaseModel):
    """A milestone extracted from the description."""
    title: str
    owner_side: str
    duration_days: int
    description: Optional[str] = None
    phase: Optional[str] = None


class GeneratePlaybookResponse(BaseModel):
    """Response from playbook generation."""
    success: bool
    playbook_id: Optional[str] = None
    playbook_name: Optional[str] = None

    # Semantic extraction
    type: Optional[str] = None  # onboarding or action
    trigger: Optional[str] = None
    archetype: Optional[str] = None
    variables: Optional[list[str]] = None
    mandates: Optional[list[str]] = None
    guardrails: Optional[list[str]] = None

    # Milestones
    milestones: Optional[list[PlaybookMilestoneResult]] = None
    milestone_count: Optional[int] = None

    # Metadata
    sidekick_adds: Optional[str] = None
    extraction_confidence: Optional[float] = None
    message: Optional[str] = None


class ExtractPlaybookPreviewResponse(BaseModel):
    """Response from playbook extraction preview (without creation)."""
    success: bool

    # Semantic extraction
    playbook_name: Optional[str] = None
    type: Optional[str] = None
    trigger: Optional[str] = None
    archetype: Optional[str] = None
    fit_note: Optional[str] = None
    variables: Optional[list[str]] = None
    mandates: Optional[list[str]] = None
    guardrails: Optional[list[str]] = None

    # Milestones
    milestones: Optional[list[PlaybookMilestoneResult]] = None

    # Metadata
    sidekick_adds: Optional[str] = None
    extraction_confidence: Optional[float] = None
    extraction_notes: Optional[str] = None
    message: Optional[str] = None


@router.post("/{workspace_id}/playbooks/generate")
async def generate_playbook(
    workspace_id: str,
    request: GeneratePlaybookRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> GeneratePlaybookResponse:
    """
    Generate a playbook from a natural language description.

    Takes a prose description of the onboarding/action process and:
    1. Extracts semantic structure (type, trigger, variables, mandates, guardrails)
    2. Extracts milestones with timing and ownership
    3. Creates the playbook in the database

    Used in the Setup flow "Describe it to Sidekick" option.
    """
    logger.info(
        "playbook_generation_requested",
        workspace_id=workspace_id,
        description_length=len(request.description),
    )

    try:
        from services.playbook_generation import generate_and_create_playbook

        result = await generate_and_create_playbook(
            workspace_id=workspace_id,
            description=request.description,
        )

        extraction = result.get("extraction", {})

        return GeneratePlaybookResponse(
            success=True,
            playbook_id=result.get("playbook_id"),
            playbook_name=result.get("playbook_name"),
            type=extraction.get("type"),
            trigger=extraction.get("trigger"),
            archetype=extraction.get("archetype"),
            variables=extraction.get("variables"),
            mandates=extraction.get("mandates"),
            guardrails=extraction.get("guardrails"),
            milestones=[
                PlaybookMilestoneResult(
                    title=m.get("title", ""),
                    owner_side=m.get("owner_side", "joint"),
                    duration_days=m.get("duration_days", 7),
                    description=m.get("description"),
                    phase=m.get("phase"),
                )
                for m in extraction.get("milestones", [])
            ],
            milestone_count=result.get("milestone_count"),
            sidekick_adds=extraction.get("sidekick_adds"),
            extraction_confidence=extraction.get("extraction_confidence"),
            message=f"Created playbook '{result.get('playbook_name')}' with {result.get('milestone_count')} milestones",
        )

    except ValueError as e:
        logger.warning("playbook_generation_validation_error", error=str(e))
        return GeneratePlaybookResponse(
            success=False,
            message=str(e),
        )

    except Exception as e:
        logger.exception("playbook_generation_error", error=str(e))
        return GeneratePlaybookResponse(
            success=False,
            message=f"Failed to generate playbook: {str(e)}",
        )


@router.post("/{workspace_id}/playbooks/extract-preview")
async def extract_playbook_preview(
    workspace_id: str,
    request: GeneratePlaybookRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ExtractPlaybookPreviewResponse:
    """
    Extract playbook structure WITHOUT creating it.

    Used for live preview in the UI while the user is typing.
    Shows what Sidekick understood from the description without
    committing to the database.
    """
    logger.info(
        "playbook_extraction_preview_requested",
        workspace_id=workspace_id,
        description_length=len(request.description),
    )

    try:
        from services.playbook_generation import extract_playbook_preview as do_extract

        extraction = await do_extract(
            workspace_id=workspace_id,
            description=request.description,
        )

        return ExtractPlaybookPreviewResponse(
            success=True,
            playbook_name=extraction.get("playbook_name"),
            type=extraction.get("type"),
            trigger=extraction.get("trigger"),
            archetype=extraction.get("archetype"),
            fit_note=extraction.get("fit_note"),
            variables=extraction.get("variables"),
            mandates=extraction.get("mandates"),
            guardrails=extraction.get("guardrails"),
            milestones=[
                PlaybookMilestoneResult(
                    title=m.get("title", ""),
                    owner_side=m.get("owner_side", "joint"),
                    duration_days=m.get("duration_days", 7),
                    description=m.get("description"),
                    phase=m.get("phase"),
                )
                for m in extraction.get("milestones", [])
            ],
            sidekick_adds=extraction.get("sidekick_adds"),
            extraction_confidence=extraction.get("extraction_confidence"),
            extraction_notes=extraction.get("extraction_notes"),
        )

    except ValueError as e:
        logger.warning("playbook_extraction_validation_error", error=str(e))
        return ExtractPlaybookPreviewResponse(
            success=False,
            message=str(e),
        )

    except Exception as e:
        logger.exception("playbook_extraction_error", error=str(e))
        return ExtractPlaybookPreviewResponse(
            success=False,
            message=f"Failed to extract playbook: {str(e)}",
        )
