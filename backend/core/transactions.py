"""
Transaction context manager with validation and observability.

Wraps database transactions with:
- Pre-transaction validation
- Structured logging
- Automatic rollback on failure

Example:
    async with critical_transaction(
        db=get_db_client(),
        transaction_name="create_handoff_with_plan",
        validation_checks=[
            ("customer_exists", lambda: check_customer(customer_id)),
        ]
    ) as conn:
        await conn.execute("INSERT INTO ...")
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

import asyncpg

from .logging import get_logger

logger = get_logger("Transactions")


@asynccontextmanager
async def critical_transaction(
    db,  # DatabaseClient
    transaction_name: str,
    validation_checks: list[tuple[str, Callable[[], bool | Awaitable[bool]]]] | None = None,
) -> AsyncIterator[asyncpg.Connection]:
    """
    Critical transaction with pre-validation and structured logging.

    Args:
        db: Database client instance (with transaction() method)
        transaction_name: Human-readable transaction name (for logs/metrics)
        validation_checks: List of (check_name, check_fn) tuples to run before transaction
            - check_fn can be sync or async
            - Should return True if validation passes

    Yields:
        asyncpg.Connection for executing queries

    Raises:
        ValueError: If any validation check fails
        Exception: Re-raises any exception from the transaction (triggers rollback)

    Example:
        async with critical_transaction(
            db=get_db_client(),
            transaction_name="create_brief_and_plan",
            validation_checks=[
                ("handbook_version_exists", lambda: ctx.handbook_version_id is not None),
            ]
        ) as conn:
            brief = await conn.fetchrow("INSERT INTO handoff_briefs ...")
            plan = await conn.fetchrow("INSERT INTO ai_plans ...")
    """
    # Pre-transaction validation
    if validation_checks:
        for check_name, check_fn in validation_checks:
            try:
                # Handle both sync and async check functions
                if asyncio.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()

                if not result:
                    logger.error(
                        "transaction_validation_failed",
                        transaction=transaction_name,
                        check=check_name,
                        result="returned_false",
                    )
                    raise ValueError(f"Validation failed: {check_name}")

            except ValueError:
                raise
            except Exception as e:
                logger.error(
                    "transaction_validation_error",
                    transaction=transaction_name,
                    check=check_name,
                    error=str(e),
                )
                raise ValueError(f"Validation check '{check_name}' raised error: {e}")

    logger.info("transaction_started", transaction=transaction_name)

    try:
        async with db.transaction() as conn:
            yield conn

        logger.info("transaction_committed", transaction=transaction_name)

    except Exception as e:
        logger.error(
            "transaction_rolled_back",
            transaction=transaction_name,
            error_type=type(e).__name__,
            error=str(e),
        )
        raise


@asynccontextmanager
async def optional_transaction(
    db,  # DatabaseClient
    use_transaction: bool = True,
    transaction_name: str = "anonymous",
) -> AsyncIterator[asyncpg.Connection | None]:
    """
    Optional transaction wrapper - can run with or without transaction.

    Useful for operations that should be atomic in production but
    can run without transactions in testing/development.

    Args:
        db: Database client instance
        use_transaction: Whether to wrap in transaction (default: True)
        transaction_name: Name for logging

    Yields:
        Connection if in transaction, None otherwise

    Example:
        async with optional_transaction(db, use_transaction=settings.is_production) as conn:
            if conn:
                # In transaction
                await conn.execute(...)
            else:
                # No transaction
                await db.execute(...)
    """
    if use_transaction:
        async with critical_transaction(db, transaction_name) as conn:
            yield conn
    else:
        logger.debug(
            "transaction_skipped",
            transaction=transaction_name,
            reason="use_transaction=False",
        )
        yield None


class TransactionBuilder:
    """
    Builder pattern for constructing transactions with multiple validations.

    Example:
        async with (
            TransactionBuilder(db)
            .name("create_customer_with_brief")
            .validate("workspace_exists", lambda: workspace_id is not None)
            .validate("deal_data_valid", lambda: deal_data.get("company_name"))
            .build()
        ) as conn:
            await conn.execute(...)
    """

    def __init__(self, db):
        self.db = db
        self._name = "anonymous"
        self._validations: list[tuple[str, Callable]] = []

    def name(self, transaction_name: str) -> "TransactionBuilder":
        """Set transaction name for logging."""
        self._name = transaction_name
        return self

    def validate(self, check_name: str, check_fn: Callable) -> "TransactionBuilder":
        """Add a validation check."""
        self._validations.append((check_name, check_fn))
        return self

    @asynccontextmanager
    async def build(self) -> AsyncIterator[asyncpg.Connection]:
        """Build and execute the transaction."""
        async with critical_transaction(
            db=self.db,
            transaction_name=self._name,
            validation_checks=self._validations,
        ) as conn:
            yield conn
