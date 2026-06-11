"""
Pydantic validation decorators for step outputs.

Provides validation of LLM-generated JSON responses against Pydantic models.
Ensures contract compliance at runtime.

Example:
    class GapAnalysisOutput(BaseModel):
        confidence: Literal["high", "medium", "low"]
        risks: list[str]

    @validate_output(GapAnalysisOutput, extract_field="gap_analysis")
    async def gap_analysis_step(ctx):
        return ctx.with_gap_analysis({...})
"""

from functools import wraps
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import StepFailedError
from .logging import get_logger

logger = get_logger("Validation")

T = TypeVar("T")


def validate_output(model: Type[BaseModel], extract_field: str | None = None):
    """
    Decorator to validate step output against a Pydantic model.

    Args:
        model: Pydantic model class to validate against
        extract_field: If provided, validate ctx.<field> instead of full context

    Example:
        class GapAnalysisOutput(BaseModel):
            confidence: Literal["high", "medium", "low"]
            risks: list[str]

        @validate_output(GapAnalysisOutput, extract_field="gap_analysis")
        async def gap_analysis_step(ctx):
            return ctx.with_gap_analysis({...})
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            result = await func(*args, **kwargs)

            # Extract data to validate
            if extract_field:
                data = getattr(result, extract_field, None)
                if data is None:
                    logger.warning(
                        "validation_field_missing",
                        step=func.__name__,
                        field=extract_field,
                    )
                    # Don't fail - field might be intentionally None
                    return result
            else:
                # Validate the entire result
                data = result

            # Convert context to dict if needed
            if hasattr(data, "model_dump"):
                data = data.model_dump()
            elif hasattr(data, "__dict__"):
                data = vars(data)

            # Validate
            try:
                model.model_validate(data)
                logger.debug(
                    "output_validated",
                    step=func.__name__,
                    model=model.__name__,
                )
            except ValidationError as e:
                logger.error(
                    "output_validation_failed",
                    step=func.__name__,
                    model=model.__name__,
                    errors=e.errors(),
                )
                raise StepFailedError(
                    f"Output validation failed: {e}",
                    step_name=func.__name__,
                )

            return result

        return wrapper

    return decorator


def validate_input(model: Type[BaseModel], arg_index: int = 0):
    """
    Decorator to validate step input against a Pydantic model.

    Args:
        model: Pydantic model class to validate against
        arg_index: Index of the argument to validate (default: 0)

    Example:
        class DealInput(BaseModel):
            company_name: str
            arr_cents: int

        @validate_input(DealInput, arg_index=1)
        async def process_deal(ctx, deal_data: dict):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Extract input to validate
            if arg_index < len(args):
                data = args[arg_index]
            else:
                logger.warning(
                    "validation_arg_missing",
                    step=func.__name__,
                    arg_index=arg_index,
                )
                return await func(*args, **kwargs)

            # Convert to dict if needed
            if hasattr(data, "model_dump"):
                data = data.model_dump()
            elif hasattr(data, "__dict__") and not isinstance(data, dict):
                data = vars(data)

            # Validate
            try:
                model.model_validate(data)
                logger.debug(
                    "input_validated",
                    step=func.__name__,
                    model=model.__name__,
                )
            except ValidationError as e:
                logger.error(
                    "input_validation_failed",
                    step=func.__name__,
                    model=model.__name__,
                    errors=e.errors(),
                )
                raise StepFailedError(
                    f"Input validation failed: {e}",
                    step_name=func.__name__,
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def validate_dict(data: dict | Any, model: Type[BaseModel]) -> BaseModel:
    """
    Validate a dictionary against a Pydantic model and return validated instance.

    Args:
        data: Dictionary or object to validate
        model: Pydantic model class

    Returns:
        Validated model instance

    Raises:
        ValidationError: If validation fails
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif hasattr(data, "__dict__") and not isinstance(data, dict):
        data = vars(data)

    return model.model_validate(data)


def safe_validate(data: dict | Any, model: Type[BaseModel]) -> tuple[BaseModel | None, list | None]:
    """
    Safely validate data against a Pydantic model.

    Args:
        data: Dictionary or object to validate
        model: Pydantic model class

    Returns:
        Tuple of (validated_instance, errors)
        - On success: (model_instance, None)
        - On failure: (None, list_of_errors)
    """
    try:
        validated = validate_dict(data, model)
        return validated, None
    except ValidationError as e:
        return None, e.errors()
