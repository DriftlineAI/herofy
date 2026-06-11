"""
Exponential backoff retry logic for transient failures.

Provides decorators for LLM calls and external API operations that may
experience transient errors (rate limits, timeouts, network issues).

Example:
    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    async def call_llm(prompt: str):
        return await model.generate_content_async(prompt)
"""

import asyncio
import random
from functools import wraps
from typing import Callable, Type, TypeVar

from .logging import get_logger

logger = get_logger("RetryLogic")

T = TypeVar("T")

# Default retryable exception types (transient errors)
RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
)


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] | None = None,
):
    """
    Decorator for exponential backoff retry.

    Args:
        max_attempts: Maximum retry attempts (1 = no retry, 2 = 1 retry, etc.)
        base_delay: Base delay in seconds (doubled each attempt)
        max_delay: Maximum delay cap
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry (defaults to RETRYABLE_EXCEPTIONS)

    Example:
        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        async def call_llm(prompt: str):
            return await model.generate_content_async(prompt)
    """
    exceptions_to_retry = retryable_exceptions or RETRYABLE_EXCEPTIONS

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions_to_retry as e:
                    last_exception = e

                    if attempt >= max_attempts:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error_type=type(e).__name__,
                            error=str(e),
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

                    # Add jitter (±25% randomness)
                    if jitter:
                        delay *= random.uniform(0.75, 1.25)

                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=round(delay, 2),
                        error_type=type(e).__name__,
                        error=str(e),
                    )

                    await asyncio.sleep(delay)

                except Exception as e:
                    # Non-retryable exception - fail immediately
                    logger.error(
                        "non_retryable_error",
                        function=func.__name__,
                        error_type=type(e).__name__,
                        error=str(e),
                    )
                    raise

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic reached unexpected state")

        return wrapper

    return decorator


def retry_sync_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] | None = None,
):
    """
    Synchronous version of retry_with_backoff for non-async functions.

    Same parameters as retry_with_backoff.
    """
    import time

    exceptions_to_retry = retryable_exceptions or RETRYABLE_EXCEPTIONS

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions_to_retry as e:
                    last_exception = e

                    if attempt >= max_attempts:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error=str(e),
                        )
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        delay *= random.uniform(0.75, 1.25)

                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        delay_seconds=round(delay, 2),
                        error=str(e),
                    )

                    time.sleep(delay)

                except Exception as e:
                    # Non-retryable exception - fail immediately
                    logger.error(
                        "non_retryable_error",
                        function=func.__name__,
                        error_type=type(e).__name__,
                        error=str(e),
                    )
                    raise

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic reached unexpected state")

        return wrapper

    return decorator
