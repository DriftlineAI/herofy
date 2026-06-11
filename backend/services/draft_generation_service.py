"""
Draft Generation Service

AI-powered draft generation for email responses in Customer Success conversations.
Generates contextual, voice-aligned drafts based on:
- Thread history (recent interactions)
- Customer context (signals, commitments, lifecycle)
- Workspace voice guidelines (handbook docs)
- User instructions

Usage:
    from services.draft_generation_service import DraftGenerationService

    service = DraftGenerationService(workspace_id)
    draft = await service.generate_draft(thread_id, instructions)
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from google import genai

from config import get_settings
from core.errors import AIServiceError
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase
from core.retry import retry_with_backoff
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("DraftGenerationService")


@dataclass
class DraftContext:
    """Context gathered for draft generation."""

    # Thread info
    thread_id: str
    subject: str
    channel: str
    thread_type: str | None

    # Customer info
    customer_id: str
    customer_name: str
    customer_tier: str | None
    customer_lifecycle: str | None
    customer_one_liner: str | None

    # Interactions (most recent first)
    interactions: list[dict[str, Any]]

    # Customer signals (recent)
    signals: list[dict[str, Any]]

    # Open commitments
    commitments: list[dict[str, Any]]

    # Voice docs
    voice_core: str | None
    voice_foundations: list[str]
    voice_scenarios: list[str]

    # User instructions
    instructions: str | None


@dataclass
class DraftResult:
    """Result from draft generation."""

    body: str
    model: str
    prompt_version: str
    handbook_version_id: str | None
    voice_docs_used: list[str]  # IDs of voice docs used


# Prompt version for tracking
PROMPT_VERSION = "draft-v1"

# Draft generation prompt
DRAFT_PROMPT = """You are a Customer Success Manager drafting an email response.
Write a professional, helpful response that aligns with the voice guidelines and customer context.

# Voice Guidelines
{voice_section}

# Customer Context
Name: {customer_name}
{customer_context}

# Recent Signals
{signals_section}

# Open Commitments
{commitments_section}

# Conversation Thread
Subject: {subject}

{conversation_history}

# Task
{task_section}

# Guidelines
- Be concise and direct
- Match the tone established in voice guidelines
- Address the customer's specific question or concern
- Don't overpromise or commit to things you can't deliver
- Keep the response focused and actionable
- Sign off appropriately (e.g., "Best," or "Thanks,")

Write ONLY the email body text. No subject line, no explanation, no markdown formatting.
"""


class DraftGenerationService:
    """
    Service for AI-powered draft generation.

    Gathers context from thread, customer, and voice docs,
    then generates a contextual draft response.
    """

    def __init__(self, workspace_id: str, tier: str | None = None):
        self.workspace_id = workspace_id
        self.settings = get_settings()
        self._client: genai.Client | None = None
        self.model_name = get_model(ModelUseCase.DRAFT_EMAIL, tier=tier)

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
            prompt: The draft generation prompt

        Returns:
            Generated draft text
        """
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        return response.text.strip()

    async def _gather_context(
        self,
        thread_id: str,
        instructions: str | None = None,
    ) -> DraftContext:
        """
        Gather all context needed for draft generation.

        Args:
            thread_id: Thread UUID
            instructions: Optional user instructions

        Returns:
            DraftContext with all gathered data
        """
        dc = get_dataconnect_client()

        # Get thread with customer context
        result = await dc.execute_query("GetThreadForDraft", {"id": thread_id})
        thread = result.get("thread")

        if not thread:
            raise AIServiceError(f"Thread {thread_id} not found")

        customer = thread.get("customer", {})
        workspace = thread.get("workspace", {})

        # Get voice docs for workspace
        voice_result = await dc.execute_query(
            "GetVoiceDocsPublic",
            {"workspaceId": workspace.get("id", self.workspace_id)},
        )
        voice_docs = voice_result.get("handbookDocs", [])

        # Separate voice docs by kind
        voice_core = None
        voice_foundations = []
        voice_scenarios = []

        for doc in voice_docs:
            kind = doc.get("kind")
            body = doc.get("body", "")
            if kind == "VOICE_CORE":
                voice_core = body
            elif kind == "VOICE_FOUNDATION":
                voice_foundations.append(body)
            elif kind == "VOICE_SCENARIO":
                # Check if this scenario applies to email drafts
                surfaces = doc.get("affectsSurfaces") or []
                if not surfaces or "EMAIL_DRAFT" in surfaces:
                    voice_scenarios.append(body)

        return DraftContext(
            thread_id=thread_id,
            subject=thread.get("subject", ""),
            channel=thread.get("channel", "email"),
            thread_type=thread.get("threadType"),
            customer_id=customer.get("id", ""),
            customer_name=customer.get("name", "Customer"),
            customer_tier=customer.get("tier"),
            customer_lifecycle=customer.get("lifecycle"),
            customer_one_liner=customer.get("oneLiner"),
            interactions=thread.get("interactions_on_thread", []),
            signals=customer.get("signals_on_customer", []),
            commitments=customer.get("commitments_on_customer", []),
            voice_core=voice_core,
            voice_foundations=voice_foundations,
            voice_scenarios=voice_scenarios,
            instructions=instructions,
        )

    def _format_voice_section(self, context: DraftContext) -> str:
        """Format voice docs for prompt."""
        parts = []

        if context.voice_core:
            parts.append(f"## Core Voice\n{context.voice_core}")

        if context.voice_foundations:
            parts.append("## Voice Foundations")
            for i, foundation in enumerate(context.voice_foundations[:3], 1):
                # Truncate long foundations
                if len(foundation) > 500:
                    foundation = foundation[:500] + "..."
                parts.append(foundation)

        if context.voice_scenarios:
            parts.append("## Relevant Scenarios")
            for scenario in context.voice_scenarios[:2]:
                if len(scenario) > 300:
                    scenario = scenario[:300] + "..."
                parts.append(scenario)

        if not parts:
            return "(No voice guidelines configured. Use a professional, helpful tone.)"

        return "\n\n".join(parts)

    def _format_customer_context(self, context: DraftContext) -> str:
        """Format customer context for prompt."""
        parts = []

        if context.customer_tier:
            parts.append(f"Tier: {context.customer_tier}")
        if context.customer_lifecycle:
            parts.append(f"Lifecycle: {context.customer_lifecycle}")
        if context.customer_one_liner:
            parts.append(f"About: {context.customer_one_liner}")

        return "\n".join(parts) if parts else "(No additional context)"

    def _format_signals_section(self, context: DraftContext) -> str:
        """Format recent signals for prompt."""
        if not context.signals:
            return "(No recent signals)"

        lines = []
        for signal in context.signals[:5]:
            kind = signal.get("kind", "unknown")
            state = signal.get("state", "ok")
            sentence = signal.get("sentence", "")

            # Format: [sentiment: warn] Customer expressed frustration about...
            lines.append(f"[{kind}: {state}] {sentence}")

        return "\n".join(lines)

    def _format_commitments_section(self, context: DraftContext) -> str:
        """Format open commitments for prompt."""
        if not context.commitments:
            return "(No open commitments)"

        lines = []
        for commitment in context.commitments[:5]:
            side = commitment.get("side", "ours")
            text = commitment.get("text", "")
            due = commitment.get("dueLabel", "")

            owner = "We committed" if side == "ours" else "They committed"
            due_str = f" (due: {due})" if due else ""
            lines.append(f"- {owner}: {text}{due_str}")

        return "\n".join(lines)

    def _format_conversation_history(self, context: DraftContext) -> str:
        """Format conversation history for prompt."""
        if not context.interactions:
            return "(No previous messages)"

        # Interactions are in reverse chronological order, we want chronological
        interactions = list(reversed(context.interactions))

        lines = []
        for interaction in interactions[-10:]:  # Last 10 messages
            direction = interaction.get("direction", "inbound")
            sender = interaction.get("senderName", "Unknown")
            body = interaction.get("bodyEncrypted", "")

            # Truncate long messages
            if len(body) > 1000:
                body = body[:1000] + "...[truncated]"

            if direction == "inbound":
                role = "Customer"
            elif direction == "outbound":
                role = "Us"
            else:
                role = sender or "Unknown"
            lines.append(f"[{role}] {sender}:\n{body}")

        return "\n\n---\n\n".join(lines)

    def _format_task_section(self, context: DraftContext) -> str:
        """Format the task/instructions section."""
        base_task = "Draft a response to the most recent customer message."

        if context.instructions:
            return f"{base_task}\n\nSpecific instructions: {context.instructions}"

        return base_task

    def _build_prompt(self, context: DraftContext) -> str:
        """Build the full draft generation prompt."""
        return DRAFT_PROMPT.format(
            voice_section=self._format_voice_section(context),
            customer_name=context.customer_name,
            customer_context=self._format_customer_context(context),
            signals_section=self._format_signals_section(context),
            commitments_section=self._format_commitments_section(context),
            subject=context.subject,
            conversation_history=self._format_conversation_history(context),
            task_section=self._format_task_section(context),
        )

    def _clean_draft(self, raw_draft: str) -> str:
        """Clean up the generated draft."""
        # Remove any markdown code blocks if present
        if raw_draft.startswith("```"):
            # Extract content from code block
            match = re.search(r"```(?:\w+)?\s*\n?([\s\S]*?)\n?```", raw_draft)
            if match:
                raw_draft = match.group(1)

        # Remove leading/trailing whitespace
        draft = raw_draft.strip()

        # Remove any "Subject:" or "Email:" prefixes if LLM added them
        lines = draft.split("\n")
        while lines and (
            lines[0].lower().startswith("subject:") or
            lines[0].lower().startswith("email:") or
            lines[0].lower().startswith("body:")
        ):
            lines = lines[1:]

        return "\n".join(lines).strip()

    async def generate_draft(
        self,
        thread_id: str,
        instructions: str | None = None,
    ) -> DraftResult:
        """
        Generate a draft response for a thread.

        Args:
            thread_id: Thread UUID
            instructions: Optional user instructions

        Returns:
            DraftResult with generated draft and metadata
        """
        logger.info(
            "draft_generation_started",
            thread_id=thread_id,
            has_instructions=bool(instructions),
        )

        # Gather context
        context = await self._gather_context(thread_id, instructions)

        # Build prompt
        prompt = self._build_prompt(context)

        # Generate draft
        try:
            raw_draft = await self._call_llm(prompt)
            draft_body = self._clean_draft(raw_draft)

            # Collect voice doc IDs used
            voice_doc_ids = []
            # We'd need to track this from the context gathering, simplified for now

            logger.info(
                "draft_generation_completed",
                thread_id=thread_id,
                draft_length=len(draft_body),
            )

            return DraftResult(
                body=draft_body,
                model=self.model_name,
                prompt_version=PROMPT_VERSION,
                handbook_version_id=None,  # TODO: Track latest handbook version
                voice_docs_used=voice_doc_ids,
            )

        except Exception as e:
            logger.error(
                "draft_generation_failed",
                thread_id=thread_id,
                error=str(e),
            )
            raise AIServiceError(f"Draft generation failed: {e}")

    async def generate_and_save_draft(
        self,
        thread_id: str,
        instructions: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a draft and save it to the database.

        Args:
            thread_id: Thread UUID
            instructions: Optional user instructions

        Returns:
            Dict with draft_id and status
        """
        # Generate draft
        result = await self.generate_draft(thread_id, instructions)

        # Get thread to retrieve customer_id
        dc = get_dataconnect_client()
        thread_result = await dc.execute_query("GetThreadForDraft", {"id": thread_id})
        thread = thread_result.get("thread", {})
        customer = thread.get("customer", {})

        # Save to database — capture the inserted id so the (synchronous) caller can hand the draft
        # straight back to the client for an immediate optimistic render (refetch-after-write doesn't
        # reliably surface DataConnect writes).
        insert = await dc.execute_mutation(
            "CreateDraftResponse",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer.get("id"),
                "threadId": thread_id,
                "subject": thread.get("subject"),
                "body": result.body,
                "model": result.model,
                "promptVersion": result.prompt_version,
                "handbookVersionId": result.handbook_version_id or "00000000-0000-0000-0000-000000000000",
            },
        )
        node = insert.get("draftResponse_insert") if isinstance(insert, dict) else None
        draft_id = node.get("id") if isinstance(node, dict) else (node if isinstance(node, str) else None)

        logger.info(
            "draft_saved",
            thread_id=thread_id,
            model=result.model,
        )

        return {
            "status": "completed",
            "thread_id": thread_id,
            "draft_id": draft_id,
            "draft_body": result.body,
            "model": result.model,
        }
