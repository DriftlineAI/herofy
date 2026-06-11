"""
Unified Ingestion Pipeline - Event Models

All sources (Notion, Gmail, Slack) emit ChangeEvent objects.
SignalWatcher consumes these and routes to appropriate handlers.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
import hashlib

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class ChangeEventSource(str, Enum):
    """Source systems that emit events."""
    NOTION = "notion"
    GMAIL = "gmail"
    SLACK = "slack"
    CALENDAR = "calendar"
    MANUAL = "manual"


class ChangeEventClass(str, Enum):
    """
    Event classification - determines routing through SignalWatcher.

    Set by the classification cascade after the event is received.
    """
    NEW_CUSTOMER = "new_customer"                     # Notion trigger fired → HandoffAuto
    STRUCTURED_FIELD_UPDATE = "structured_field_update"  # Mapped property changed → direct sync
    UNSTRUCTURED_CONTENT = "unstructured_content"     # Notes/body/email/Slack → LLM classify
    UNKNOWN_SENDER = "unknown_sender"                 # Unrecognized contact → drop or hold


# =============================================================================
# Artifacts Tracking (validated JSON structure)
# =============================================================================


class ArtifactsCreated(BaseModel):
    """
    Tracks artifacts created from a single ChangeEvent (fan-out).

    Stored as JSON in change_events.artifacts_created column.
    This model validates the structure - no free-form JSON allowed.
    """
    interactions: list[str] = Field(default_factory=list)  # UUID strings
    signals: list[str] = Field(default_factory=list)       # UUID strings
    needs: list[str] = Field(default_factory=list)         # UUID strings
    agent_runs: list[str] = Field(default_factory=list)    # UUID strings
    customer_updates: list[str] = Field(default_factory=list)  # UUID strings of updated customers
    stakeholders: list[str] = Field(default_factory=list)  # UUID strings of created/updated stakeholders
    meetings: list[str] = Field(default_factory=list)      # UUID strings of created/updated meetings


# =============================================================================
# ChangeEvent - The Universal Event Envelope
# =============================================================================


class ChangeEvent(BaseModel):
    """
    Universal event envelope for all ingestion sources.

    All sources (Notion, Gmail, Slack) emit this shape.
    SignalWatcher consumes these and routes to appropriate handlers.

    Lifecycle:
    1. Emitter creates ChangeEvent with source info and raw_payload
    2. Orchestrator persists to change_events table (fingerprint dedup)
    3. SignalWatcher reads unprocessed events
    4. Classification cascade sets event_class
    5. Router dispatches to handler based on event_class
    6. Handler creates artifacts, updates artifacts_created
    7. Event marked as processed
    """
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID

    # Source identification
    source: ChangeEventSource
    source_event_type: str          # "notion_new_record", "notion_field_update", "gmail_message", etc.
    source_record_id: str           # External ID for dedup and linking
    fingerprint: str                # Computed from source + source_record_id + content hash

    # Customer linkage (resolved at emit time if possible)
    customer_id: UUID | None = None

    # Event data
    raw_payload: dict[str, Any]     # Full data from source
    occurred_at: datetime           # When event happened in source system

    # Classification (set after cascade analysis)
    event_class: ChangeEventClass | None = None

    # Processing state
    processed: bool = False
    processed_at: datetime | None = None
    processing_error: str | None = None

    # Fan-out tracking (validated structure)
    artifacts_created: ArtifactsCreated = Field(default_factory=ArtifactsCreated)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def compute_fingerprint(
        cls,
        source: str,
        source_record_id: str,
        content_hash: str = "",
    ) -> str:
        """
        Compute deduplication fingerprint.

        Fingerprint is unique per (workspace, source, source_record_id, content).
        The workspace_id is NOT included here - uniqueness is enforced at DB level
        via composite index on (workspace_id, fingerprint).
        """
        raw = f"{source}:{source_record_id}:{content_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database insertion."""
        import json
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "source": self.source.value,
            "source_event_type": self.source_event_type,
            "source_record_id": self.source_record_id,
            "fingerprint": self.fingerprint,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "raw_payload": json.dumps(self.raw_payload),
            "occurred_at": self.occurred_at.isoformat(),
            "event_class": self.event_class.value if self.event_class else None,
            "processed": self.processed,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "processing_error": self.processing_error,
            "artifacts_created": self.artifacts_created.model_dump_json(),
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Payload Schemas - Type-safe structures for each event type
# =============================================================================


class NotionNewRecordPayload(BaseModel):
    """Payload when a new Notion record matches the trigger."""
    page_id: str
    company_name: str
    properties: dict[str, Any]          # All properties from the page
    rich_text_content: dict[str, str]   # {"Notes": "...", "Technical": "..."}


class NotionFieldUpdatePayload(BaseModel):
    """Payload when a mapped Notion property changed."""
    page_id: str
    property_name: str                  # Notion property name
    mapped_field: str                   # Herofy Customer column
    old_value: Any | None = None
    new_value: Any


class NotionContentUpdatePayload(BaseModel):
    """Payload when unstructured Notion content (rich text) changed."""
    page_id: str
    field_name: str                     # Which rich text field changed
    old_content: str | None = None
    new_content: str


class MessagePayload(BaseModel):
    """Payload for Gmail/Slack messages."""
    sender_email: str
    sender_name: str
    sender_domain: str | None = None
    subject: str | None = None
    body: str
    channel: str                        # "email" | "slack"
    reply_to_id: str | None = None
    thread_id: str | None = None


# =============================================================================
# Configuration Models
# =============================================================================


class NotionTriggerConfig(BaseModel):
    """
    Trigger configuration for Notion polling.

    Stored in WorkspaceIntegration.config JSON under "trigger_config" key.
    """
    mode: str = "existence_based"       # "existence_based" | "status_based"
    status_property: str | None = None  # Only for status_based mode
    trigger_values: list[str] = Field(default_factory=list)  # Only for status_based mode

    def matches_trigger(self, page_properties: dict[str, Any]) -> bool:
        """
        Check if a page matches the trigger criteria.

        Args:
            page_properties: Dict of property_name -> value

        Returns:
            True if the page should trigger a new_customer event
        """
        if self.mode == "existence_based":
            return True

        if self.mode == "status_based" and self.status_property:
            status_value = page_properties.get(self.status_property)
            return status_value in self.trigger_values

        return False


class NotionIntegrationConfig(BaseModel):
    """
    Full Notion integration configuration.

    Stored in WorkspaceIntegration.config JSON.
    """
    database_id: str
    database_name: str | None = None

    # Field mappings: Notion property name -> Herofy field
    # e.g., {"Company Name": "name", "Lifecycle Stage": "lifecycle"}
    # This IS the authority allowlist: if a field is mapped, Notion can update it
    field_mappings: dict[str, str] = Field(default_factory=dict)

    # Trigger configuration
    trigger_config: NotionTriggerConfig = Field(default_factory=NotionTriggerConfig)

    # Rich text fields to track for content updates
    rich_text_fields: list[str] = Field(default_factory=list)

    # Last polling watermark
    last_watermark: str | None = None


# =============================================================================
# Customer Resolution - Personal Domain Blocklist
# =============================================================================


PERSONAL_EMAIL_DOMAINS = frozenset([
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.co.uk",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "fastmail.com",
    "zoho.com",
    "mail.com",
    "gmx.com",
    "gmx.net",
    "ymail.com",
    "rocketmail.com",
])


def is_personal_email_domain(domain: str) -> bool:
    """
    Check if a domain is a personal email provider.

    Used to skip domain-based customer matching for personal emails.
    """
    return domain.lower() in PERSONAL_EMAIL_DOMAINS
