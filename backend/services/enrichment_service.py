"""
Customer Enrichment Service

AI-powered enrichment for customer data imported from CRM systems.
Uses a single LLM call per customer to extract structured data from raw notes.

Principle: "Extract what's stated, don't infer what isn't."
- Only extract data explicitly mentioned in notes
- Don't manufacture sentiment or risk stories where none exist
- Leave fields null/empty if no evidence in source data

Usage:
    from services.enrichment_service import EnrichmentService

    service = EnrichmentService(workspace_id)
    result = await service.enrich_customer(customer_id, raw_notes)
"""

import hashlib
import json
import re
from typing import Any

from google import genai

from config import get_settings
from core.errors import AIServiceError
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase
from core.retry import retry_with_backoff
from db.dataconnect_client import get_dataconnect_client

from .enrichment_models import (
    EnrichmentOutput,
    EnrichmentInput,
    StakeholderData,
    GoalData,
    SignalData,
)

logger = get_logger("EnrichmentService")

# LLM prompt for customer enrichment
ENRICHMENT_PROMPT = """You are analyzing raw CRM notes for a customer account to extract structured data.

# Customer
Name: {customer_name}
{context_section}
{existing_goals_section}
# Raw Notes
{raw_notes}
{linked_pages_section}
# Task
Extract ONLY information that is explicitly stated or clearly implied in the notes.
DO NOT invent, assume, or infer information that isn't present.

Extract the following if present:

1. **one_liner**: A single sentence describing what this customer does or their key situation (max 120 chars). ALWAYS generate this - use the company name and any context available.

2. **stakeholders**: People mentioned by name with their roles/context. Only include if explicitly named.
   - name: Person's name
   - email: Email if mentioned
   - role: Job title or role if mentioned
   - sentiment_note: ONLY if the notes explicitly describe their sentiment (e.g., "frustrated about X", "excited about Y")

3. **goals**: Business goals or desired outcomes the customer wants to achieve.
   - text: The goal description (see quality guidelines below)
   - status: "active" (default), "achieved" (if noted as complete), "dropped" (if noted as abandoned)
   - priority: "primary" (core business objective), "secondary" (supporting goal), or "exploratory" (nice-to-have)
   - success_criteria: Brief description of how success would be measured (if mentioned or inferable)

   **Goal Quality Guidelines - CRITICAL**:
   Goals must be OUTCOME-FOCUSED, not activity-focused. The test: "Why does this matter to the business?"

   GOOD goals (outcome-focused, specific):
   - "Reduce customer support ticket volume by 30%" (measurable outcome)
   - "Enable self-service reporting for finance team" (specific capability + user)
   - "Accelerate sales cycle from 45 to 30 days" (measurable business impact)
   - "Achieve SOC 2 compliance before enterprise deals" (specific milestone)

   BAD goals (vague, activity-focused):
   - "Use the product" (not a goal, just adoption)
   - "Get value" (too vague)
   - "Improve processes" (no specificity)
   - "Better analytics" (what outcome? for whom?)

   Transform vague statements into specific goals:
   - "They want analytics" → "Enable data-driven decision making for marketing team"
   - "Need reporting" → "Provide executive visibility into pipeline health"
   - "Integration with Salesforce" → "Automate lead routing to reduce manual entry by 50%"

   **CRITICAL - Avoid Duplicates**: Check the EXISTING GOALS section above. DO NOT extract goals that:
   - Are identical or nearly identical to existing goals
   - Say the same thing with different wording
   - Are subsets or supersets of existing goals

   **Goal Inference Based on Context**:
   {goal_inference_section}

4. **signals**: Health indicators ONLY if explicitly described in the notes:
   - kind: "sentiment" (emotional state explicitly described) OR "commitments" (promises/deadlines mentioned)
   - state: "ok", "warn", or "risk" based on what's described
   - sentence: One-sentence narrative of what's stated
   - evidence_text: Quote or reference from the notes
   NOTE: Do NOT include "engagement" signals - you cannot infer engagement from static documents.

5. **risk_brief**: A 2-3 sentence summary of risks or concerns ONLY if the notes explicitly describe:
   - Escalations, complaints, or frustrations
   - At-risk situations, churn signals
   - Blockers or problems
   If no risk information is present, set to null.

# Critical Guidelines
- If information is not present, use null or empty arrays - DO NOT make things up
- Only extract sentiment signals if emotions/attitudes are explicitly described
- Only extract commitment signals if specific promises or deadlines are mentioned
- The risk_brief should only exist if there's actual risk content in the notes
- Be concise and factual
- Prefer null over generic/placeholder content

# Output Format (JSON only, no explanation)
{{
  "one_liner": "Brief description" or null,
  "stakeholders": [
    {{"name": "Jane Doe", "role": "VP Engineering", "email": "jane@example.com", "sentiment_note": "Frustrated about integration delays" or null}}
  ],
  "goals": [
    {{"text": "Reduce support ticket volume by 30% through self-service", "status": "active", "priority": "primary", "success_criteria": "Monthly ticket count drops from 500 to 350"}}
  ],
  "signals": [
    {{"kind": "sentiment", "state": "warn", "sentence": "CFO expressed concern about ROI timeline", "evidence_text": "Sarah mentioned she's under pressure from the board..."}}
  ],
  "risk_brief": "Brief risk summary" or null,
  "extraction_notes": "Brief note on what was/wasn't extractable" or null
}}
"""


class EnrichmentService:
    """
    Service for AI-powered customer enrichment.

    Handles single-customer enrichment and batch processing for imports.
    """

    def __init__(self, workspace_id: str, tier: str | None = None):
        self.workspace_id = workspace_id
        self.settings = get_settings()
        self._client: genai.Client | None = None
        self.model_name = get_model(ModelUseCase.ENRICHMENT, tier=tier)

    def _get_client(self) -> genai.Client:
        """Get or create the GenAI client instance."""
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
    async def _call_llm(self, prompt: str) -> str:
        """
        Call Gemini with retry logic for transient failures.

        Args:
            prompt: The enrichment prompt

        Returns:
            Raw response text from LLM
        """
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        return response.text.strip()

    def _build_goal_inference_section(
        self,
        lifecycle: str | None,
        tier: str | None,
        arr_cents: int | None,
        value_prop: str | None,
    ) -> str:
        """
        Build dynamic goal inference guidance based on customer context.

        Returns specific, contextual guidance for inferring goals when none are stated.
        """
        sections = []

        # Base guidance
        sections.append(
            "If no specific goals are explicitly stated AND no existing goals cover the topic, "
            "you may infer goals based on context. Inferred goals must still be OUTCOME-FOCUSED."
        )

        # Lifecycle-specific inference
        lifecycle_guidance = {
            "prospect": (
                "For PROSPECTS: Focus on evaluation goals\n"
                "  - 'Validate that [product] can solve [specific problem mentioned]'\n"
                "  - 'Compare [product] against current solution for [use case]'\n"
                "  - 'Build internal business case for [product] adoption'"
            ),
            "onboarding": (
                "For ONBOARDING customers: Focus on adoption and time-to-value\n"
                "  - 'Achieve first value milestone within [X] days of kickoff'\n"
                "  - 'Successfully onboard [team/department] as initial users'\n"
                "  - 'Complete data migration and validation before go-live'\n"
                "  - 'Train power users to enable self-service'"
            ),
            "active": (
                "For ACTIVE customers: Focus on expansion and deepening value\n"
                "  - 'Expand usage from [current team] to [additional teams]'\n"
                "  - 'Achieve measurable ROI to justify renewal/expansion'\n"
                "  - 'Reduce reliance on workarounds by adopting [feature]'"
            ),
            "renewal": (
                "For RENEWAL customers: Focus on demonstrable value\n"
                "  - 'Document ROI to support renewal decision'\n"
                "  - 'Address any adoption gaps before renewal discussion'\n"
                "  - 'Identify expansion opportunities for next contract period'"
            ),
            "at_risk": (
                "For AT-RISK customers: Focus on stabilization\n"
                "  - 'Resolve [specific blocker] preventing value realization'\n"
                "  - 'Re-engage [churned stakeholder/team]'\n"
                "  - 'Demonstrate quick win to rebuild confidence'"
            ),
        }

        if lifecycle and lifecycle.lower() in lifecycle_guidance:
            sections.append(lifecycle_guidance[lifecycle.lower()])

        # Tier-specific guidance
        if tier:
            tier_lower = tier.lower()
            if tier_lower in ("enterprise", "strategic"):
                sections.append(
                    "For ENTERPRISE tier: Goals often involve\n"
                    "  - Cross-functional rollouts ('Enable all regional teams')\n"
                    "  - Compliance/security requirements ('Achieve [certification] compliance')\n"
                    "  - Executive visibility ('Provide C-suite dashboard for [metrics]')\n"
                    "  - Integration with enterprise systems ('Connect to [Salesforce/SAP/etc]')"
                )
            elif tier_lower in ("smb", "startup", "growth"):
                sections.append(
                    "For SMB/STARTUP tier: Goals often involve\n"
                    "  - Quick time-to-value ('Get [core feature] working this week')\n"
                    "  - Cost efficiency ('Replace [manual process] to save [hours/week]')\n"
                    "  - Scaling preparation ('Set up [product] to support 10x growth')"
                )

        # ARR-based guidance
        if arr_cents:
            arr = arr_cents / 100
            if arr >= 100000:
                sections.append(
                    "For HIGH-VALUE accounts ($100K+ ARR): Inferred goals should be strategic and measurable. "
                    "These customers expect significant business impact."
                )

        # Value prop guidance
        if value_prop:
            sections.append(
                f"Based on your product's value proposition: '{value_prop[:200]}...'\n"
                "Inferred goals should connect to this value prop. "
                "Example: If value prop mentions 'reduce support tickets', "
                "a reasonable goal is 'Decrease support volume by X% through self-service'."
            )

        # Fallback
        if len(sections) == 1:
            sections.append(
                "Without specific context, infer conservative goals:\n"
                "  - 'Successfully adopt core [product] capabilities'\n"
                "  - 'Achieve measurable improvement in [area mentioned in notes]'\n"
                "  - 'Enable [team/role mentioned] to [accomplish task mentioned]'"
            )

        sections.append(
            "\nMark inferred goals with priority='secondary' unless context clearly indicates they are primary. "
            "Always prefer extracting explicit goals over inferring."
        )

        return "\n\n".join(sections)

    async def _build_prompt(self, input_data: EnrichmentInput) -> str:
        """Build the enrichment prompt from input data."""
        dc = get_dataconnect_client()

        # Build optional context section
        context_parts = []
        value_prop = None

        if input_data.existing_tier:
            context_parts.append(f"Tier: {input_data.existing_tier}")
        if input_data.existing_arr_cents:
            arr_display = f"${input_data.existing_arr_cents / 100:,.0f}"
            context_parts.append(f"ARR: {arr_display}")
        if input_data.existing_lifecycle:
            context_parts.append(f"Lifecycle: {input_data.existing_lifecycle}")

        # Fetch workspace value prop for goal inference context
        try:
            workspace_result = await dc.execute_query(
                "GetWorkspacePublic",
                {"id": self.workspace_id},
            )
            workspace = workspace_result.get("workspace")
            if workspace:
                value_prop = workspace.get("valueProp")
                if value_prop:
                    # Truncate value prop to reasonable length
                    value_prop = value_prop[:500]
                    context_parts.append(f"Company Value Prop: {value_prop}")
        except Exception as e:
            logger.warning(
                "workspace_fetch_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )

        context_section = "\n".join(context_parts) if context_parts else ""

        # Build dynamic goal inference section
        goal_inference_section = self._build_goal_inference_section(
            lifecycle=input_data.existing_lifecycle,
            tier=input_data.existing_tier,
            arr_cents=input_data.existing_arr_cents,
            value_prop=value_prop,
        )

        # Fetch existing goals to avoid duplicates
        existing_goals_section = ""
        try:
            goals_result = await dc.execute_query(
                "GetCustomerGoals",
                {
                    "customerId": input_data.customer_id,
                    "workspaceId": self.workspace_id,
                },
            )
            existing_goals = goals_result.get("goals", [])
            if existing_goals:
                goal_texts = [f"- {g.get('text', '')}" for g in existing_goals if g.get("text")]
                if goal_texts:
                    existing_goals_section = "\n# Existing Goals (DO NOT DUPLICATE)\n" + "\n".join(goal_texts) + "\n"
        except Exception as e:
            logger.warning(
                "existing_goals_fetch_failed",
                customer_id=input_data.customer_id,
                error=str(e),
            )

        # Truncate raw notes to prevent excessive token usage and prompt injection
        MAX_NOTES_LENGTH = 50000
        MAX_LINKED_CONTENT_LENGTH = 30000
        raw_notes = input_data.raw_notes or ""
        if len(raw_notes) > MAX_NOTES_LENGTH:
            raw_notes = raw_notes[:MAX_NOTES_LENGTH] + "\n\n[Notes truncated due to length]"
            logger.warning(
                "raw_notes_truncated",
                customer_name=input_data.customer_name,
                original_length=len(input_data.raw_notes or ""),
                truncated_to=MAX_NOTES_LENGTH,
            )

        # Build linked pages section if we have content from linked documents
        linked_pages_section = ""
        if input_data.linked_pages_content:
            linked_content = input_data.linked_pages_content
            if len(linked_content) > MAX_LINKED_CONTENT_LENGTH:
                linked_content = linked_content[:MAX_LINKED_CONTENT_LENGTH] + "\n\n[Content truncated due to length]"
                logger.warning(
                    "linked_pages_truncated",
                    customer_name=input_data.customer_name,
                    original_length=len(input_data.linked_pages_content),
                    truncated_to=MAX_LINKED_CONTENT_LENGTH,
                )
            linked_pages_section = f"\n# Linked Documents\n{linked_content}\n"

        return ENRICHMENT_PROMPT.format(
            customer_name=input_data.customer_name,
            context_section=context_section,
            existing_goals_section=existing_goals_section,
            raw_notes=raw_notes or "(No notes provided)",
            linked_pages_section=linked_pages_section,
            goal_inference_section=goal_inference_section,
        )

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """
        Extract JSON from LLM response, handling various formats.

        Args:
            response_text: Raw LLM response text

        Returns:
            Parsed JSON as dict

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        text = response_text.strip()

        # Try 1: Direct JSON parse (clean response)
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try 2: Extract from markdown code block
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Try 3: Find JSON object anywhere in text
        json_pattern = r"\{[\s\S]*\}"
        json_matches = re.findall(json_pattern, text)
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Nothing worked
        raise json.JSONDecodeError("No valid JSON found in response", text, 0)

    async def enrich_customer(
        self,
        customer_id: str,
        customer_name: str,
        raw_notes: str | None,
        linked_pages_content: str | None = None,
        existing_tier: str | None = None,
        existing_arr_cents: int | None = None,
        existing_lifecycle: str | None = None,
    ) -> EnrichmentOutput:
        """
        Enrich a single customer with AI-extracted data.

        Args:
            customer_id: Customer UUID
            customer_name: Customer name
            raw_notes: Raw CRM notes to process
            linked_pages_content: Combined content from linked pages (Notion, etc.)
            existing_tier: Current tier (for context)
            existing_arr_cents: Current ARR (for context)
            existing_lifecycle: Current lifecycle stage (for context)

        Returns:
            EnrichmentOutput with extracted data

        Raises:
            AIServiceError: If LLM call fails after retries
        """
        has_notes = bool(raw_notes and raw_notes.strip())
        has_linked = bool(linked_pages_content and linked_pages_content.strip())

        logger.info(
            "enrichment_started",
            customer_id=customer_id,
            customer_name=customer_name,
            has_notes=has_notes,
            has_linked_pages=has_linked,
        )

        # If no content to process, return empty output
        if not has_notes and not has_linked:
            logger.info(
                "enrichment_skipped",
                customer_id=customer_id,
                reason="no_content",
            )
            return EnrichmentOutput(
                extraction_notes="No raw notes or linked pages provided for enrichment"
            )

        # Build input and prompt
        input_data = EnrichmentInput(
            customer_id=customer_id,
            customer_name=customer_name,
            raw_notes=raw_notes or "",
            linked_pages_content=linked_pages_content,
            existing_tier=existing_tier,
            existing_arr_cents=existing_arr_cents,
            existing_lifecycle=existing_lifecycle,
        )
        prompt = await self._build_prompt(input_data)

        try:
            # Call LLM
            response_text = await self._call_llm(prompt)

            # Parse and validate response
            raw_output = self._extract_json(response_text)
            output = EnrichmentOutput.model_validate(raw_output)

            logger.info(
                "enrichment_completed",
                customer_id=customer_id,
                stakeholders_count=len(output.stakeholders),
                goals_count=len(output.goals),
                signals_count=len(output.signals),
                has_risk_brief=output.risk_brief is not None,
            )

            return output

        except json.JSONDecodeError as e:
            logger.error(
                "enrichment_parse_error",
                customer_id=customer_id,
                error=str(e),
            )
            return EnrichmentOutput(
                extraction_notes=f"Failed to parse LLM response: {e}"
            )

        except Exception as e:
            logger.error(
                "enrichment_failed",
                customer_id=customer_id,
                error=str(e),
            )
            raise AIServiceError(f"Enrichment failed for {customer_name}: {e}")

    async def process_and_save_enrichment(
        self,
        customer_id: str,
        customer_name: str,
        raw_notes: str | None,
        linked_pages_content: str | None = None,
        existing_tier: str | None = None,
        existing_arr_cents: int | None = None,
        existing_lifecycle: str | None = None,
    ) -> dict[str, Any]:
        """
        Enrich a customer and save all extracted data to the database.

        This is the main entry point for background enrichment processing.

        Args:
            customer_id: Customer UUID
            customer_name: Customer name
            raw_notes: Raw CRM notes to process
            linked_pages_content: Combined content from linked pages (Notion, etc.)
            existing_tier: Current tier
            existing_arr_cents: Current ARR
            existing_lifecycle: Current lifecycle stage

        Returns:
            dict with enrichment results summary
        """
        dc = get_dataconnect_client()

        try:
            # Mark as processing
            await dc.execute_mutation(
                "UpdateCustomerEnrichmentStatus",
                {
                    "id": customer_id,
                    "enrichmentStatus": "processing",
                    "enrichmentAttempts": 1,  # TODO: Increment from current
                    "enrichmentError": None,
                },
            )

            # Run enrichment
            output = await self.enrich_customer(
                customer_id=customer_id,
                customer_name=customer_name,
                raw_notes=raw_notes,
                linked_pages_content=linked_pages_content,
                existing_tier=existing_tier,
                existing_arr_cents=existing_arr_cents,
                existing_lifecycle=existing_lifecycle,
            )

            # Save extracted data
            results = await self._save_enrichment_data(customer_id, output)

            # Mark as completed
            await dc.execute_mutation(
                "CompleteCustomerEnrichment",
                {
                    "id": customer_id,
                    "oneLiner": output.one_liner,
                    "enrichmentStatus": "completed",
                },
            )

            return {
                "status": "completed",
                "customer_id": customer_id,
                **results,
            }

        except Exception as e:
            # Mark as failed
            await dc.execute_mutation(
                "UpdateCustomerEnrichmentStatus",
                {
                    "id": customer_id,
                    "enrichmentStatus": "failed",
                    "enrichmentError": str(e)[:500],  # Truncate long errors
                },
            )
            raise

    # Vague goal patterns that indicate low-quality goals
    VAGUE_GOAL_PATTERNS = [
        # Too generic
        r"^use\s+(the\s+)?product$",
        r"^get\s+value$",
        r"^improve\s+(things|processes|operations)$",
        r"^be(come)?\s+(more\s+)?(successful|better|efficient)$",
        r"^make\s+(things|it)\s+(work|better)$",
        # Activity-focused, not outcome-focused
        r"^(implement|deploy|install|set\s*up)\s+\w+$",
        r"^integrate\s+with\s+\w+$",
        r"^use\s+\w+\s+(feature|functionality)$",
        # Missing specificity
        r"^(better|more|improved)\s+\w+$",
        r"^(do|have|get)\s+(more|better)\s+\w+$",
    ]

    # Keywords that indicate higher-quality goals
    QUALITY_GOAL_INDICATORS = [
        # Measurability
        r"\d+%",  # Percentage
        r"\d+\s*(days?|weeks?|months?|hours?)",  # Time-based
        r"by\s+(q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)",
        r"(reduce|increase|improve)\s+.*\s+by",
        # Specificity
        r"(team|department|role)s?\s+(of|for|in)",
        r"(enable|empower)\s+\w+\s+to",
        r"(before|after|during)\s+\w+",
        # Outcome language
        r"(achieve|accomplish|complete|deliver)",
        r"(roi|revenue|cost|efficiency|productivity)",
    ]

    def _validate_goal_quality(self, goal_text: str) -> tuple[bool, str | None]:
        """
        Validate that a goal meets quality standards.

        Returns:
            (is_valid, rejection_reason) - is_valid=True means goal passes
        """
        import re

        text = goal_text.lower().strip()

        # Check minimum length
        if len(text) < 10:
            return False, "Goal too short - needs more specificity"

        # Check against vague patterns
        for pattern in self.VAGUE_GOAL_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return False, f"Goal is too vague - matches pattern: {pattern}"

        # Check for quality indicators (bonus, not required)
        quality_score = 0
        for pattern in self.QUALITY_GOAL_INDICATORS:
            if re.search(pattern, text, re.IGNORECASE):
                quality_score += 1

        # Warn if no quality indicators but don't reject
        if quality_score == 0:
            logger.debug(
                "goal_low_quality_score",
                goal_text=goal_text[:50],
                hint="No measurability or specificity indicators found",
            )

        return True, None

    def _extract_goal_keywords(self, text: str) -> set[str]:
        """
        Extract meaningful keywords from goal text for semantic comparison.

        Removes common stopwords and extracts core concepts.
        """
        # Common stopwords to ignore
        stopwords = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "need",
            "our", "their", "your", "my", "this", "that", "these", "those",
            "it", "its", "we", "they", "them", "us", "all", "each", "every",
        }

        # Normalize and tokenize
        normalized = self._normalize_goal_text(text)
        words = normalized.split()

        # Filter stopwords and short words
        keywords = {w for w in words if w not in stopwords and len(w) > 2}

        return keywords

    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity between two goal texts using keyword overlap.

        Returns a score between 0.0 (no similarity) and 1.0 (identical).
        """
        keywords1 = self._extract_goal_keywords(text1)
        keywords2 = self._extract_goal_keywords(text2)

        if not keywords1 or not keywords2:
            return 0.0

        # Jaccard similarity
        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        return len(intersection) / len(union) if union else 0.0

    def _normalize_goal_text(self, text: str) -> str:
        """Normalize goal text for deduplication comparison."""
        # Lowercase, strip whitespace, remove punctuation variations
        normalized = text.lower().strip()
        # Remove common punctuation that might vary
        for char in [".", ",", "!", "?", "-", "—", "'"]:
            normalized = normalized.replace(char, "")
        # Collapse multiple spaces
        normalized = " ".join(normalized.split())
        return normalized

    def _is_duplicate_goal(self, new_text: str, existing_goals: list[dict]) -> tuple[bool, str | None]:
        """
        Check if a goal with similar text already exists.

        Uses multiple strategies:
        1. Exact match after normalization
        2. Substring containment
        3. Semantic similarity via keyword overlap

        Returns:
            (is_duplicate, matching_goal_text) - is_duplicate=True means it's a duplicate
        """
        normalized_new = self._normalize_goal_text(new_text)

        for existing in existing_goals:
            existing_text = existing.get("text", "")
            normalized_existing = self._normalize_goal_text(existing_text)

            # Strategy 1: Exact match after normalization
            if normalized_new == normalized_existing:
                return True, existing_text

            # Strategy 2: Substring containment (handles minor variations)
            if len(normalized_new) > 20 and len(normalized_existing) > 20:
                if normalized_new in normalized_existing or normalized_existing in normalized_new:
                    return True, existing_text

            # Strategy 3: Semantic similarity (keyword overlap > 70%)
            similarity = self._calculate_semantic_similarity(new_text, existing_text)
            if similarity >= 0.7:
                logger.debug(
                    "goal_semantic_duplicate",
                    new_goal=new_text[:50],
                    existing_goal=existing_text[:50],
                    similarity=similarity,
                )
                return True, existing_text

        return False, None

    async def _save_enrichment_data(
        self,
        customer_id: str,
        output: EnrichmentOutput,
    ) -> dict[str, int]:
        """
        Save extracted stakeholders, goals, and signals to database.

        Args:
            customer_id: Customer UUID
            output: Enrichment output with extracted data

        Returns:
            dict with counts of created records
        """
        dc = get_dataconnect_client()
        results = {
            "stakeholders_created": 0,
            "goals_created": 0,
            "goals_skipped_duplicate": 0,
            "goals_skipped_low_quality": 0,
            "signals_created": 0,
            "observations_created": 0,
        }

        # Track created goal IDs for observation linking
        created_goal_ids: list[str] = []

        # Create stakeholders
        for stakeholder in output.stakeholders:
            try:
                await dc.execute_mutation(
                    "CreateStakeholder",
                    {
                        "workspaceId": self.workspace_id,
                        "customerId": customer_id,
                        "name": stakeholder.name,
                        "email": stakeholder.email,
                        "role": stakeholder.role,
                        "sentimentNote": stakeholder.sentiment_note,
                    },
                )
                results["stakeholders_created"] += 1
            except Exception as e:
                logger.warning(
                    "stakeholder_create_failed",
                    customer_id=customer_id,
                    stakeholder_name=stakeholder.name,
                    error=str(e),
                )

        # Fetch existing goals for deduplication
        existing_goals = []
        try:
            goals_result = await dc.execute_query(
                "GetCustomerGoals",
                {
                    "customerId": customer_id,
                    "workspaceId": self.workspace_id,
                },
            )
            existing_goals = goals_result.get("goals", [])
        except Exception as e:
            logger.warning(
                "existing_goals_fetch_failed",
                customer_id=customer_id,
                error=str(e),
            )

        # Create goals with validation, source attribution and deduplication
        created_goal_texts: list[str] = []
        for i, goal in enumerate(output.goals):
            # Step 1: Validate goal quality
            is_valid, rejection_reason = self._validate_goal_quality(goal.text)
            if not is_valid:
                logger.info(
                    "goal_skipped_low_quality",
                    customer_id=customer_id,
                    goal_text=goal.text[:50],
                    reason=rejection_reason,
                )
                results["goals_skipped_low_quality"] += 1
                continue

            # Step 2: Check for duplicates (including semantic similarity)
            is_duplicate, matching_goal = self._is_duplicate_goal(goal.text, existing_goals)
            if is_duplicate:
                logger.info(
                    "goal_skipped_duplicate",
                    customer_id=customer_id,
                    goal_text=goal.text[:50],
                    matches=matching_goal[:50] if matching_goal else None,
                )
                results["goals_skipped_duplicate"] += 1
                continue

            # Step 3: Create the goal
            try:
                await dc.execute_mutation(
                    "CreateGoalWithSource",
                    {
                        "workspaceId": self.workspace_id,
                        "customerId": customer_id,
                        "text": goal.text,
                        "source": "Sidekick",
                        "sourceType": "ai_inferred",
                        "sortOrder": i,
                    },
                )
                results["goals_created"] += 1
                created_goal_texts.append(goal.text)
                # Add to existing goals to prevent duplicates within same batch
                existing_goals.append({"text": goal.text})
            except Exception as e:
                logger.warning(
                    "goal_create_failed",
                    customer_id=customer_id,
                    goal_text=goal.text[:50],
                    error=str(e),
                )

        # Fetch all goal IDs for observation linking (include newly created)
        all_goals = []
        try:
            goals_result = await dc.execute_query(
                "GetCustomerGoals",
                {
                    "customerId": customer_id,
                    "workspaceId": self.workspace_id,
                },
            )
            all_goals = goals_result.get("goals", [])
        except Exception as e:
            logger.warning(
                "goals_fetch_for_observations_failed",
                customer_id=customer_id,
                error=str(e),
            )

        # Create signals
        for signal in output.signals:
            try:
                await dc.execute_mutation(
                    "CreateSignal",
                    {
                        "workspaceId": self.workspace_id,
                        "customerId": customer_id,
                        "kind": signal.kind,
                        "state": signal.state,
                        "sentence": signal.sentence,
                        "evidenceText": signal.evidence_text,
                        "model": self.model_name,
                        "promptVersion": "enrichment-v1",
                        "inputsHash": "enrichment",  # TODO: Generate proper hash
                        "handbookVersionId": "00000000-0000-0000-0000-000000000000",  # Placeholder
                    },
                )
                results["signals_created"] += 1
            except Exception as e:
                logger.warning(
                    "signal_create_failed",
                    customer_id=customer_id,
                    signal_kind=signal.kind,
                    error=str(e),
                )

        # Create GoalObservations from signals with evidence
        # Link observations to the first active goal if available
        active_goals = [g for g in all_goals if g.get("status") == "active"]
        if active_goals and output.signals:
            first_goal = active_goals[0]
            goal_id = first_goal["id"]

            for signal in output.signals:
                # Only create observation if we have evidence text
                if not signal.evidence_text:
                    continue

                # Generate fingerprint for deduplication
                fingerprint_input = f"{self.workspace_id}:{goal_id}:{signal.sentence}"
                fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:32]

                # Map signal state to confidence level
                confidence_map = {
                    "ok": "high",
                    "warn": "medium",
                    "risk": "high",  # Risk signals are important, high confidence
                }
                confidence = confidence_map.get(signal.state, "medium")

                try:
                    await dc.execute_mutation(
                        "CreateGoalObservation",
                        {
                            "workspaceId": self.workspace_id,
                            "customerId": customer_id,
                            "goalId": goal_id,
                            "text": signal.sentence,
                            "confidence": confidence,
                            "sourceType": "crm notes",
                            "sourceInteractionId": None,
                            "fingerprint": fingerprint,
                        },
                    )
                    results["observations_created"] += 1
                    logger.info(
                        "goal_observation_created",
                        customer_id=customer_id,
                        goal_id=goal_id,
                        observation_text=signal.sentence[:50],
                    )
                except Exception as e:
                    # Likely duplicate fingerprint, skip
                    logger.debug(
                        "goal_observation_create_failed",
                        customer_id=customer_id,
                        goal_id=goal_id,
                        error=str(e),
                    )

        return results

    def _extract_linked_pages_content(self, linked_pages_json: str | None) -> str | None:
        """
        Extract and combine content from linked pages JSON.

        Args:
            linked_pages_json: JSON string of linked pages array

        Returns:
            Combined content from all linked pages with titles, or None if no content
        """
        if not linked_pages_json:
            return None

        try:
            linked_pages = json.loads(linked_pages_json)
            if not isinstance(linked_pages, list):
                return None

            content_parts = []
            for page in linked_pages:
                content = page.get("content")
                if content and content.strip():
                    title = page.get("title", "Untitled")
                    source = page.get("source", "unknown")
                    content_parts.append(f"## {title} ({source})\n{content}")

            if not content_parts:
                return None

            return "\n\n---\n\n".join(content_parts)

        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "linked_pages_parse_error",
                error=str(e),
            )
            return None

    async def get_pending_customers(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get customers pending enrichment.

        Args:
            limit: Maximum customers to return

        Returns:
            List of customer dicts with id, name, rawNotes, etc.
        """
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetPendingEnrichmentCustomers",
            {
                "workspaceId": self.workspace_id,
                "limit": limit,
            },
        )
        return result.get("customers", [])

    async def process_batch(self, batch_size: int = 10) -> dict[str, Any]:
        """
        Process a batch of pending enrichments.

        Args:
            batch_size: Number of customers to process in this batch

        Returns:
            dict with processing results
        """
        import asyncio

        pending = await self.get_pending_customers(limit=batch_size)

        if not pending:
            logger.info("no_pending_enrichments", workspace_id=self.workspace_id)
            return {"processed": 0, "failed": 0, "remaining": 0}

        processed = 0
        failed = 0

        for customer in pending:
            try:
                # Extract linked pages content if available
                linked_pages_content = self._extract_linked_pages_content(
                    customer.get("linkedPages")
                )

                await self.process_and_save_enrichment(
                    customer_id=customer["id"],
                    customer_name=customer["name"],
                    raw_notes=customer.get("rawNotes"),
                    linked_pages_content=linked_pages_content,
                    existing_tier=customer.get("tier"),
                    existing_arr_cents=customer.get("arrCents"),
                    existing_lifecycle=customer.get("lifecycle"),
                )
                processed += 1
            except Exception as e:
                logger.error(
                    "batch_enrichment_failed",
                    customer_id=customer["id"],
                    error=str(e),
                )
                failed += 1

            # Rate limiting - 1 second between customers
            await asyncio.sleep(1)

        # Check remaining
        remaining_customers = await self.get_pending_customers(limit=1)
        remaining = len(remaining_customers)

        logger.info(
            "batch_completed",
            workspace_id=self.workspace_id,
            processed=processed,
            failed=failed,
            remaining=remaining,
        )

        return {
            "processed": processed,
            "failed": failed,
            "remaining": remaining,
        }


async def process_enrichment_queue(workspace_id: str) -> None:
    """
    Background task to process all pending enrichments for a workspace.

    Continues until queue is empty or max iterations reached.
    """
    service = EnrichmentService(workspace_id)
    max_iterations = 100  # Safety limit

    for i in range(max_iterations):
        result = await service.process_batch(batch_size=10)

        if result["remaining"] == 0:
            logger.info(
                "enrichment_queue_empty",
                workspace_id=workspace_id,
                total_iterations=i + 1,
            )
            break

        if result["processed"] == 0 and result["failed"] > 0:
            logger.warning(
                "enrichment_queue_stalled",
                workspace_id=workspace_id,
                iteration=i + 1,
            )
            break


async def enrich_single_customer(workspace_id: str, customer_id: str) -> dict:
    """
    Enrich a single customer by ID.

    Fetches the customer data and runs enrichment. Used for manual sync operations.

    Args:
        workspace_id: Workspace UUID
        customer_id: Customer UUID

    Returns:
        dict with enrichment results
    """
    dc = get_dataconnect_client()

    # Fetch customer data (use PUBLIC query since this may be called from event processor without user auth)
    result = await dc.execute_query(
        "GetCustomerPublic",
        {"id": customer_id},
    )

    customer = result.get("customer")
    if not customer:
        raise ValueError(f"Customer {customer_id} not found")

    # Run enrichment
    service = EnrichmentService(workspace_id)

    # Extract linked pages content
    linked_pages_content = service._extract_linked_pages_content(
        customer.get("linkedPages")
    )

    return await service.process_and_save_enrichment(
        customer_id=customer_id,
        customer_name=customer["name"],
        raw_notes=customer.get("rawNotes"),
        linked_pages_content=linked_pages_content,
        existing_tier=customer.get("tier"),
        existing_arr_cents=int(customer["arrCents"]) if customer.get("arrCents") else None,
        existing_lifecycle=customer.get("lifecycle"),
    )
