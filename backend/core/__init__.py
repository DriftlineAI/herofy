"""Core module - cross-cutting concerns."""

from .errors import (
    HerofyError,
    DatabaseError,
    DatabaseNotConnectedError,
    WorkspaceScopeError,
    AgentError,
    StepFailedError,
    AgentTimeoutError,
    ToolError,
    NotionToolError,
    ValidationError,
)
from .logging import get_logger, configure_logging
from .retry import retry_with_backoff, retry_sync_with_backoff
from .encryption import encrypt_field, decrypt_field, is_encryption_enabled
from .metrics import trace_step, trace_llm_call, create_span
from .validation import validate_output, validate_input, validate_dict
from .transactions import critical_transaction, optional_transaction
from .model_config import get_model, ModelUseCase

__all__ = [
    # Errors
    "HerofyError",
    "DatabaseError",
    "DatabaseNotConnectedError",
    "WorkspaceScopeError",
    "AgentError",
    "StepFailedError",
    "AgentTimeoutError",
    "ToolError",
    "NotionToolError",
    "ValidationError",
    # Logging
    "get_logger",
    "configure_logging",
    # Retry
    "retry_with_backoff",
    "retry_sync_with_backoff",
    # Encryption
    "encrypt_field",
    "decrypt_field",
    "is_encryption_enabled",
    # Metrics
    "trace_step",
    "trace_llm_call",
    "create_span",
    # Validation
    "validate_output",
    "validate_input",
    "validate_dict",
    # Transactions
    "critical_transaction",
    "optional_transaction",
    # Model config
    "get_model",
    "ModelUseCase",
]
