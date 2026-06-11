"""
Customer Classification Service

AI-powered classification for customers during setup.
Analyzes CRM data + linked Notion pages to determine:
- Which grouping the customer belongs to (not-yet-customer, pointer-needed, ready-to-confirm)
- Confidence score
- Reasoning for the Sidekick panel
- What Sidekick knows vs is uncertain about

This service is used:
1. During setup to group imported customers correctly
2. By auto-handoff agent to understand customer state
3. For future imports to apply learned mappings

Usage:
    from services.customer_classifier import CustomerClassifier

    classifier = CustomerClassifier(workspace_id)
    result = await classifier.classify_customer(customer_data, linked_pages)
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from google import genai

from config import get_settings
from core.errors import AIServiceError
from core.logging import get_logger
from core.retry import retry_with_backoff

logger = get_logger("CustomerClassifier")


# Classification categories
ClassificationGroup = Literal[
    "not_yet_customer",  # Lead, prospect - not a customer yet
    "pointer_needed",    # Onboarding but we don't know their progress
    "ready_to_confirm",  # We have enough info to show what we inferred
    "new_customer",      # Just signed, no onboarding progress yet
]


@dataclass
class CustomerInput:
    """Input data for customer classification."""
    customer_id: str
    customer_name: str
    lifecycle: str | None  # From CRM: lead, onboarding, active, churned, etc.
    tier: str | None
    arr_cents: int | None
    days_as_customer: int | None  # Days since they became a customer
    onboarding_day_current: int | None
    onboarding_day_total: int | None
    raw_notes: str | None  # Any notes from CRM
    linked_pages: list[dict] | None  # Linked Notion pages with content


@dataclass
class LinkedPageSummary:
    """Summary of what we know from a linked page."""
    title: str
    page_type: str  # handoff, tracker, notes, other
    has_milestones: bool
    milestone_count: int
    completed_count: int
    in_progress_count: int
    key_findings: list[str]


@dataclass
class ClassificationResult:
    """Result of customer classification."""
    customer_id: str
    group: ClassificationGroup
    confidence: int  # 0-100

    # For Sidekick panel
    reasoning: str  # 1-2 sentence explanation
    what_i_know: list[str]  # Bullet points of what Sidekick knows
    what_im_uncertain_about: list[str]  # What needs clarification (phrased as questions)

    # If ready_to_confirm, include inferred details
    suggested_playbook: str | None
    playbook_code: str | None
    current_state: str | None  # "Day 5 of 14", "Healthy · no signals", etc.
    next_milestone: str | None

    # From linked pages
    linked_page_summaries: list[LinkedPageSummary]

    # Data inconsistencies detected
    data_inconsistencies: list[str]  # Mismatches between CRM and tracker data


CLASSIFICATION_PROMPT = """You are Sidekick, an AI assistant helping classify a customer during workspace setup.

# Customer Data from CRM
Name: {customer_name}
Lifecycle field: {lifecycle}
Tier: {tier}
ARR: {arr_display}
Days as customer: {days_as_customer}
Onboarding progress: {onboarding_progress}

# Notes from CRM
{raw_notes}

# Linked Notion Pages
{linked_pages_content}

# Your Task
Classify this customer into ONE of these groups. BE SMART ABOUT DATA INCONSISTENCIES.

**IMPORTANT: Don't blindly trust the lifecycle status.** Look for evidence that contradicts it:
- A "Lead" in the CRM for 30+ days with ARR/tier info might actually be a customer someone forgot to update
- A "Lead" with linked onboarding docs is probably a customer
- An "Active" customer with "Not Started" in their tracker might be mislabeled
- If the data doesn't add up, flag it in "what_im_uncertain_about" and ask a clarifying question

## Groups:

1. **not_yet_customer**: Truly a lead/prospect, not a customer yet
   - Lifecycle like "lead", "prospect" AND no contradicting evidence
   - No ARR, no tier, no onboarding activity
   - If in doubt, classify as pointer_needed and ask to confirm

2. **new_customer**: Just signed, no onboarding progress yet
   - Recent customer (< 7 days) with no linked docs
   - OR lifecycle says customer but everything else is blank
   - Need to start fresh

3. **pointer_needed**: They're a customer but we can't determine their progress
   - Lifecycle suggests onboarding/active but we lack details
   - No linked tracker pages, OR linked pages are unclear
   - ALSO USE THIS when data is inconsistent and we need user to clarify
   - Example: "Lead" status but has ARR → ask "Did you close this deal?"

4. **ready_to_confirm**: We have enough info to show what we've inferred
   - Clear lifecycle AND consistent data
   - OR linked pages have clear milestone/progress data
   - We can confidently show what we think

## Detecting Inconsistencies - Flag These:
- Lifecycle says "Lead" but has ARR/tier → "Did you close this one and forget to update status?"
- Lifecycle says "Active" but tracker says "Not Started" → "Status mismatch - which is correct?"
- Been in CRM for 30+ days as "Lead" with activity → "This looks like it might be a customer"
- Has onboarding docs linked but lifecycle says "Lead" → "This appears to have onboarding activity"

# Output Format (JSON only)
{{
  "group": "not_yet_customer" | "new_customer" | "pointer_needed" | "ready_to_confirm",
  "confidence": 0-100,
  "reasoning": "1-2 sentence explanation of why this classification",
  "what_i_know": ["Bullet 1", "Bullet 2"],
  "what_im_uncertain_about": ["Question or uncertainty - phrase as question if asking user to clarify"],
  "suggested_playbook": "Playbook name if applicable" or null,
  "playbook_code": "PB-XXX-XXX" or null,
  "current_state": "Day X of Y" or "Healthy · no signals" or null,
  "next_milestone": "Milestone description" or null,
  "linked_page_findings": [
    {{
      "title": "Page title",
      "page_type": "handoff|tracker|notes|other",
      "has_milestones": true/false,
      "milestone_count": 0,
      "completed_count": 0,
      "in_progress_count": 0,
      "key_findings": ["Finding 1", "Finding 2"]
    }}
  ],
  "data_inconsistencies": ["Any data mismatches you detected"] or []
}}

Be concise but informative. The "what_i_know" and "what_im_uncertain_about" will be shown in a Sidekick panel. When uncertain, phrase items as questions to the user like "Did you close this deal and forget to update the status?"
"""


class CustomerClassifier:
    """
    AI-powered customer classification for setup flow.

    Analyzes CRM data + linked Notion pages to determine the right
    grouping and provide context for the Sidekick panel.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.settings = get_settings()
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Get or create the GenAI client instance."""
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    async def _call_llm(self, prompt: str) -> str:
        """Call Gemini (no retry here - retry is at higher level)."""
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()

    @retry_with_backoff(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=(
            json.JSONDecodeError,  # AI returned garbage - retry
            ConnectionError,
            TimeoutError,
        ),
    )
    async def _call_and_parse(self, prompt: str) -> dict[str, Any]:
        """Call LLM and parse JSON response, with retry on bad responses."""
        response = await self._call_llm(prompt)
        return self._extract_json(response)

    def _build_prompt(self, input_data: CustomerInput) -> str:
        """Build the classification prompt from input data."""
        # Format ARR display (Int64 comes as string from DataConnect)
        arr_display = "Unknown"
        if input_data.arr_cents:
            try:
                arr_cents = int(input_data.arr_cents) if isinstance(input_data.arr_cents, str) else input_data.arr_cents
                arr_display = f"${arr_cents / 100:,.0f}"
            except (ValueError, TypeError):
                pass

        # Format onboarding progress
        onboarding_progress = "Unknown"
        if input_data.onboarding_day_current and input_data.onboarding_day_total:
            onboarding_progress = f"Day {input_data.onboarding_day_current} of {input_data.onboarding_day_total}"
        elif input_data.onboarding_day_current:
            onboarding_progress = f"Day {input_data.onboarding_day_current}"

        # Format linked pages content
        linked_pages_content = "(No linked pages)"
        if input_data.linked_pages:
            pages_text = []
            for page in input_data.linked_pages:
                page_text = f"## {page.get('title', 'Untitled')}\n"
                page_text += f"Type: {page.get('page_type', 'unknown')}\n"
                if page.get('content'):
                    # Truncate content to prevent token overflow
                    content = page['content'][:5000]
                    if len(page['content']) > 5000:
                        content += "\n[Truncated...]"
                    page_text += f"Content:\n{content}\n"
                pages_text.append(page_text)
            linked_pages_content = "\n---\n".join(pages_text)

        # Truncate raw notes
        raw_notes = input_data.raw_notes or "(No notes)"
        if len(raw_notes) > 10000:
            raw_notes = raw_notes[:10000] + "\n[Truncated...]"

        return CLASSIFICATION_PROMPT.format(
            customer_name=input_data.customer_name,
            lifecycle=input_data.lifecycle or "Unknown",
            tier=input_data.tier or "Unknown",
            arr_display=arr_display,
            days_as_customer=input_data.days_as_customer or "Unknown",
            onboarding_progress=onboarding_progress,
            raw_notes=raw_notes,
            linked_pages_content=linked_pages_content,
        )

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from LLM response, handling various formats."""
        text = response_text.strip()

        # Try 1: Direct JSON parse (clean response)
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try 2: Extract from markdown code block
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        match = re.search(code_block_pattern, text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try 3: Find JSON object in text
        json_pattern = r"\{[\s\S]*\}"
        match = re.search(json_pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("No valid JSON found in response", text, 0)

    def _parse_result(self, customer_id: str, raw_result: dict[str, Any]) -> ClassificationResult:
        """Parse raw LLM response into ClassificationResult."""
        # Parse linked page findings
        linked_summaries = []
        for page in raw_result.get("linked_page_findings", []):
            linked_summaries.append(LinkedPageSummary(
                title=page.get("title", "Untitled"),
                page_type=page.get("page_type", "other"),
                has_milestones=page.get("has_milestones", False),
                milestone_count=page.get("milestone_count", 0),
                completed_count=page.get("completed_count", 0),
                in_progress_count=page.get("in_progress_count", 0),
                key_findings=page.get("key_findings", []),
            ))

        return ClassificationResult(
            customer_id=customer_id,
            group=raw_result.get("group", "pointer_needed"),
            confidence=raw_result.get("confidence", 50),
            reasoning=raw_result.get("reasoning", "Unable to determine classification."),
            what_i_know=raw_result.get("what_i_know", []),
            what_im_uncertain_about=raw_result.get("what_im_uncertain_about", []),
            suggested_playbook=raw_result.get("suggested_playbook"),
            playbook_code=raw_result.get("playbook_code"),
            current_state=raw_result.get("current_state"),
            next_milestone=raw_result.get("next_milestone"),
            linked_page_summaries=linked_summaries,
            data_inconsistencies=raw_result.get("data_inconsistencies", []),
        )

    async def classify_customer(self, input_data: CustomerInput) -> ClassificationResult:
        """
        Classify a single customer.

        Args:
            input_data: Customer data including CRM fields and linked pages

        Returns:
            ClassificationResult with group, confidence, and reasoning
        """
        logger.info(
            "classifying_customer",
            customer_id=input_data.customer_id,
            customer_name=input_data.customer_name,
            lifecycle=input_data.lifecycle,
            linked_pages_count=len(input_data.linked_pages or []),
        )

        try:
            prompt = self._build_prompt(input_data)
            raw_result = await self._call_and_parse(prompt)
            result = self._parse_result(input_data.customer_id, raw_result)

            logger.info(
                "customer_classified",
                customer_id=input_data.customer_id,
                group=result.group,
                confidence=result.confidence,
            )

            return result

        except Exception as e:
            logger.error(
                "classification_failed",
                customer_id=input_data.customer_id,
                error=str(e),
            )
            # Return a fallback result with user-friendly message
            # Don't expose technical error details to the UI
            return ClassificationResult(
                customer_id=input_data.customer_id,
                group="pointer_needed",
                confidence=0,
                reasoning="I wasn't able to analyze this customer automatically. Please classify manually.",
                what_i_know=[],
                what_im_uncertain_about=["Classification requires manual review"],
                suggested_playbook=None,
                playbook_code=None,
                current_state=None,
                next_milestone=None,
                linked_page_summaries=[],
                data_inconsistencies=[],
            )

    async def classify_customers(
        self,
        customers: list[CustomerInput]
    ) -> list[ClassificationResult]:
        """
        Classify multiple customers.

        Args:
            customers: List of customer data to classify

        Returns:
            List of ClassificationResults in same order as input
        """
        results = []
        for customer in customers:
            result = await self.classify_customer(customer)
            results.append(result)
        return results


# Helper function for quick classification without linked pages
def quick_classify_by_lifecycle(lifecycle: str | None) -> ClassificationGroup:
    """
    Quick classification based only on lifecycle field.
    Used as fallback when AI classification isn't available.

    Args:
        lifecycle: The lifecycle value from CRM

    Returns:
        Classification group
    """
    if not lifecycle:
        return "pointer_needed"

    lc = lifecycle.lower().strip()

    # Not yet customer
    if lc in ("lead", "prospect", "opportunity", "pipeline", "mql", "sql"):
        return "not_yet_customer"

    # Onboarding - need more info
    if lc in ("onboarding", "implementation", "implementing", "setup", "deploying"):
        return "pointer_needed"

    # Active customers - ready to confirm
    if lc in ("active", "live", "renewing", "renewed", "healthy", "customer"):
        return "ready_to_confirm"

    # Churned - probably exclude
    if lc in ("churned", "cancelled", "lost", "inactive", "paused"):
        return "not_yet_customer"  # Treat as not active for setup purposes

    # Default to pointer needed
    return "pointer_needed"
