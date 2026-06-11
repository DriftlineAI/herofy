"""
Playbook Generation Service

AI-powered extraction of playbook structure from natural language descriptions.
Uses Gemini to parse user descriptions of their onboarding process and extract:
- Type: onboarding or action playbook
- Trigger: when this playbook kicks off
- Variables: customer-specific data needed (customer.name, customer.champion, etc.)
- Mandates: required outcomes with deadlines
- Guardrails: rules about what NOT to do
- Milestones: the actual steps in the process
"""

import json
import re
from typing import Any

from google import genai

from config import get_settings
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase
from core.retry import retry_with_backoff
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("PlaybookGeneration")

# =============================================================================
# LLM Prompt
# =============================================================================

PLAYBOOK_GENERATION_PROMPT = """You are an expert Customer Success analyst. Extract a structured playbook from this natural language description.

## Description
{description}

## Task
Parse this description into a structured playbook with semantic understanding. Extract:

### 1. Playbook Metadata
- **type**: Is this an "onboarding" playbook (new customer setup) or an "action" playbook (responding to signals)?
- **trigger**: What event kicks off this playbook? (e.g., "new enterprise customer signs", "customer goes dark", "renewal approaching")
- **archetype**: Complexity level - "simple" (< 2 weeks), "standard" (2-4 weeks), "complex" (4+ weeks), "enterprise" (6+ weeks)

### 2. Variables (Customer Data Needed)
What customer-specific information does this playbook need? Common variables:
- customer.name, customer.champion, customer.tier
- customer.business_goal, customer.integration_needs
- customer.timeline, customer.launch_date
- customer.tech_stack, customer.team_size

### 3. Mandates (Required Outcomes)
Hard requirements with timing. Format as "[outcome] by [timing]"
Examples:
- "SSO + champion identified by week 2"
- "First workflow in production by day 21"
- "30-day check-in completed before day 35"

### 4. Guardrails (What to Avoid)
Rules about what NOT to do. Things that could derail onboarding.
Examples:
- "No kickoff calls on Friday or holiday weeks"
- "Never ship custom work without scoping doc"
- "Don't skip the 30-day check-in for any reason"

### 5. Milestones (The Steps)
Extract 4-8 concrete milestones. For each:
- **title**: Clear, action-oriented name
- **owner_side**: "us" (vendor), "customer", or "joint"
- **duration_days**: Days from start when this should complete
- **description**: What happens and what "done" looks like
- **phase**: Which phase this belongs to: "setup" (week 1), "activation" (weeks 2-3), "expansion" (weeks 4+), "success" (ongoing)

## Output Format (JSON only, no markdown)
{{
  "playbook_name": "Standard SaaS Onboarding",
  "type": "onboarding",
  "trigger": "new customer signs contract",
  "archetype": "standard",
  "fit_note": "Best for mid-market B2B SaaS with 2-4 week activation timeline",

  "variables": [
    "customer.name",
    "customer.champion",
    "customer.business_goal",
    "customer.integration_needs"
  ],

  "mandates": [
    "Champion identified by day 3",
    "First integration connected by week 1",
    "First workflow in production by day 21",
    "30-day check-in completed"
  ],

  "guardrails": [
    "No kickoff calls on Friday or holiday weeks",
    "Never promise custom work without eng review",
    "Don't skip weekly async check-ins"
  ],

  "milestones": [
    {{
      "title": "Kickoff Call",
      "owner_side": "us",
      "duration_days": 3,
      "description": "Review goals, align on integrations, set timeline expectations",
      "phase": "setup"
    }},
    {{
      "title": "Technical Setup",
      "owner_side": "customer",
      "duration_days": 7,
      "description": "Customer creates workspace, connects first data source, verifies auth",
      "phase": "setup"
    }},
    {{
      "title": "First Workflow Live",
      "owner_side": "joint",
      "duration_days": 21,
      "description": "First production workflow running with real data",
      "phase": "activation"
    }},
    {{
      "title": "30-Day Check-in",
      "owner_side": "us",
      "duration_days": 30,
      "description": "Review progress, surface blockers, identify expansion opportunities",
      "phase": "expansion"
    }}
  ],

  "sidekick_adds": "Sidekick will handle step sequencing, deadline tracking, and flag when milestones are at risk",
  "extraction_confidence": 0.85,
  "extraction_notes": "Clear timeline mentioned. Assumed standard tech setup based on SaaS context."
}}

IMPORTANT:
- Extract ONLY what is stated or clearly implied
- Use sensible defaults for timing if not specified (kickoff = day 3, first value = day 14-21)
- Variables should use dot notation (customer.X, integration.X)
- Mandates must have timing attached
- Guardrails are about what NOT to do
"""


# =============================================================================
# Response Models
# =============================================================================

class PlaybookExtraction:
    """Structured extraction result from AI."""

    def __init__(self, data: dict[str, Any]):
        self.playbook_name = data.get("playbook_name", "Generated Playbook")
        self.type = data.get("type", "onboarding")
        self.trigger = data.get("trigger", "customer signs")
        self.archetype = data.get("archetype", "standard")
        self.fit_note = data.get("fit_note")

        self.variables = data.get("variables", [])
        self.mandates = data.get("mandates", [])
        self.guardrails = data.get("guardrails", [])
        self.milestones = data.get("milestones", [])

        self.sidekick_adds = data.get("sidekick_adds", "Structure and step sequencing")
        self.extraction_confidence = data.get("extraction_confidence", 0.5)
        self.extraction_notes = data.get("extraction_notes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_name": self.playbook_name,
            "type": self.type,
            "trigger": self.trigger,
            "archetype": self.archetype,
            "fit_note": self.fit_note,
            "variables": self.variables,
            "mandates": self.mandates,
            "guardrails": self.guardrails,
            "milestones": self.milestones,
            "sidekick_adds": self.sidekick_adds,
            "extraction_confidence": self.extraction_confidence,
            "extraction_notes": self.extraction_notes,
        }


# =============================================================================
# Service
# =============================================================================

class PlaybookGenerationService:
    """
    Service for generating playbooks from natural language descriptions.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.model_name = get_model(ModelUseCase.PLAYBOOK_GENERATION)
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Lazy initialize GenAI client."""
        if self._client is None:
            settings = get_settings()
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
    async def extract_playbook(self, description: str) -> PlaybookExtraction:
        """
        Extract playbook structure from a natural language description.

        Args:
            description: User's natural language description of their process

        Returns:
            PlaybookExtraction with full semantic structure
        """
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")

        client = self._get_client()
        prompt = PLAYBOOK_GENERATION_PROMPT.format(description=description)

        logger.info(
            "playbook_extraction_started",
            workspace_id=self.workspace_id,
            description_length=len(description),
            model=self.model_name,
        )

        try:
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            response_text = response.text.strip()

            # Parse JSON response
            parsed = self._extract_json(response_text)
            extraction = PlaybookExtraction(parsed)

            logger.info(
                "playbook_extraction_completed",
                workspace_id=self.workspace_id,
                playbook_name=extraction.playbook_name,
                milestone_count=len(extraction.milestones),
                variable_count=len(extraction.variables),
                mandate_count=len(extraction.mandates),
                guardrail_count=len(extraction.guardrails),
                confidence=extraction.extraction_confidence,
            )

            return extraction

        except json.JSONDecodeError as e:
            logger.error(
                "playbook_extraction_parse_error",
                workspace_id=self.workspace_id,
                error=str(e),
            )
            raise ValueError(f"Failed to parse AI response: {e}")

        except Exception as e:
            logger.error(
                "playbook_extraction_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )
            raise

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        text = response_text.strip()

        # Try direct parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try markdown code block
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Try finding JSON anywhere
        json_pattern = r"\{[\s\S]*\}"
        json_matches = re.findall(json_pattern, text)
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("No valid JSON found", text, 0)

    async def create_playbook_from_extraction(
        self,
        extraction: PlaybookExtraction,
    ) -> dict[str, Any]:
        """
        Create a playbook in the database from extraction results.

        Args:
            extraction: PlaybookExtraction from extract_playbook()

        Returns:
            dict with created playbook ID and milestone IDs
        """
        dc = get_dataconnect_client()

        # Build fit_note that includes the semantic extraction info
        # This preserves mandates/guardrails for the UI to display
        metadata = {
            "type": extraction.type,
            "trigger": extraction.trigger,
            "variables": extraction.variables,
            "mandates": extraction.mandates,
            "guardrails": extraction.guardrails,
            "sidekick_adds": extraction.sidekick_adds,
        }
        fit_note_with_metadata = json.dumps(metadata)

        # Create the playbook
        playbook_result = await dc.execute_mutation(
            "CreatePlaybook",
            {
                "workspaceId": self.workspace_id,
                "name": extraction.playbook_name,
                "archetype": extraction.archetype,
                "fitNote": fit_note_with_metadata,
            },
        )

        playbook_id = playbook_result.get("playbook_insert", {}).get("id")
        if not playbook_id:
            raise ValueError("Failed to create playbook")

        # Create milestones
        milestone_ids = []

        for idx, milestone in enumerate(extraction.milestones):
            # Map owner_side to enum value
            owner_side = milestone.get("owner_side", "joint")
            if owner_side not in ("us", "customer", "joint"):
                owner_side = "joint"

            # Include phase in description if present
            description = milestone.get("description", "")
            phase = milestone.get("phase")
            if phase:
                description = f"[{phase.upper()}] {description}"

            milestone_result = await dc.execute_mutation(
                "CreatePlaybookMilestone",
                {
                    "playbookId": playbook_id,
                    "title": milestone.get("title", f"Step {idx + 1}"),
                    "ownerSide": owner_side,
                    "durationDays": milestone.get("duration_days", 7),
                    "description": description,
                    "sortOrder": idx,
                },
            )

            milestone_id = milestone_result.get("playbookMilestone_insert", {}).get("id")
            if milestone_id:
                milestone_ids.append(milestone_id)

        logger.info(
            "playbook_created_from_extraction",
            workspace_id=self.workspace_id,
            playbook_id=playbook_id,
            milestone_count=len(milestone_ids),
        )

        return {
            "playbook_id": playbook_id,
            "milestone_ids": milestone_ids,
            "playbook_name": extraction.playbook_name,
            "archetype": extraction.archetype,
            "milestone_count": len(milestone_ids),
        }


async def generate_and_create_playbook(
    workspace_id: str,
    description: str,
) -> dict[str, Any]:
    """
    Convenience function to extract and create a playbook in one call.

    Args:
        workspace_id: Workspace UUID
        description: Natural language description of onboarding process

    Returns:
        dict with playbook ID, extraction data, and creation metadata
    """
    service = PlaybookGenerationService(workspace_id)

    # Extract playbook structure from description
    extraction = await service.extract_playbook(description)

    # Create in database
    created = await service.create_playbook_from_extraction(extraction)

    return {
        **created,
        "extraction": extraction.to_dict(),
    }


async def extract_playbook_preview(
    workspace_id: str,
    description: str,
) -> dict[str, Any]:
    """
    Extract playbook structure WITHOUT creating it.

    Used for live preview in the UI while user is typing.

    Args:
        workspace_id: Workspace UUID
        description: Natural language description

    Returns:
        Extraction data for UI display
    """
    service = PlaybookGenerationService(workspace_id)
    extraction = await service.extract_playbook(description)
    return extraction.to_dict()
