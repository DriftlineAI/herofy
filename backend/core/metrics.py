"""
OpenTelemetry tracing for agent steps and LLM calls.

Provides decorators for automatic span creation and context propagation.
Gracefully degrades when OpenTelemetry is not configured.

Production: Auto-exports to Google Cloud Trace
Development: Uses OTLP endpoint if configured, otherwise logs only

Example:
    @trace_step("GapAnalysisStep")
    async def gap_analysis_step(ctx):
        pass

    @trace_llm_call("gemini-2.5-flash")
    async def call_llm(prompt: str):
        pass
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, TypeVar

from .logging import get_logger

logger = get_logger("Metrics")

T = TypeVar("T")

# OpenTelemetry imports (optional)
_tracer = None
_otel_available = False
_gcp_trace_available = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource

    _otel_available = True
except ImportError:
    logger.debug("opentelemetry_not_installed", message="OpenTelemetry spans disabled")

# Check for GCP Cloud Trace exporter
try:
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    _gcp_trace_available = True
except ImportError:
    _gcp_trace_available = False


def _init_tracer():
    """
    Initialize OpenTelemetry tracer.

    Production: Auto-exports to Google Cloud Trace (no config needed)
    Development: Uses OTLP endpoint if OTEL_EXPORTER_ENDPOINT is set
    """
    global _tracer

    if not _otel_available:
        return None

    if _tracer is not None:
        return _tracer

    # Lazy import to avoid circular dependency
    from config import settings

    # Create resource (same for all environments)
    resource = Resource.create(
        {
            "service.name": "herofy-backend",
            "service.version": "1.0.0",
            "deployment.environment": settings.environment,
        }
    )

    # Production: Use Google Cloud Trace
    if settings.is_production and _gcp_trace_available:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider = TracerProvider(resource=resource)
            exporter = CloudTraceSpanExporter(
                project_id=settings.firebase_project_id
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            _tracer = trace.get_tracer(__name__)
            logger.info(
                "cloud_trace_initialized",
                project_id=settings.firebase_project_id,
            )
            return _tracer

        except Exception as e:
            logger.warning("cloud_trace_initialization_failed", error=str(e))
            # Fall through to try OTLP or no-op

    # Development: Use OTLP endpoint if configured
    otel_endpoint = getattr(settings, "otel_exporter_endpoint", None)
    if otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            _tracer = trace.get_tracer(__name__)
            logger.info(
                "otlp_tracer_initialized",
                endpoint=otel_endpoint,
            )
            return _tracer

        except Exception as e:
            logger.warning("otlp_initialization_failed", error=str(e))

    # No tracing configured
    logger.debug(
        "tracing_disabled",
        is_production=settings.is_production,
        gcp_available=_gcp_trace_available,
        otel_endpoint=bool(otel_endpoint),
    )
    return None


def get_tracer():
    """Get OpenTelemetry tracer or None if not available."""
    global _tracer
    if _tracer is None:
        _tracer = _init_tracer()
    return _tracer


def trace_step(step_name: str, record_output: bool = False):
    """
    Decorator to trace an agent step with OpenTelemetry.

    Args:
        step_name: Step name (e.g., "GapAnalysisStep")
        record_output: Whether to record output size (default: False for PII)

    Example:
        @trace_step("GapAnalysisStep")
        async def gap_analysis_step(ctx):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            start_time = time.time()

            # Extract context from first arg (usually ctx)
            ctx = args[0] if args else None
            run_id = str(getattr(ctx, "run_id", "unknown")) if ctx else "unknown"
            workspace_id = str(getattr(ctx, "workspace_id", "unknown")) if ctx else "unknown"

            if tracer and _otel_available:
                with tracer.start_as_current_span(step_name) as span:
                    span.set_attribute("run_id", run_id)
                    span.set_attribute("workspace_id", workspace_id)
                    span.set_attribute("step_name", step_name)

                    try:
                        result = await func(*args, **kwargs)

                        duration_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("duration_ms", duration_ms)
                        span.set_attribute("status", "success")

                        if record_output:
                            output_size = len(str(result)) if result else 0
                            span.set_attribute("output_size_bytes", output_size)

                        # Also log for non-OTEL environments
                        logger.debug(
                            "step_traced",
                            step=step_name,
                            duration_ms=duration_ms,
                            status="success",
                        )

                        return result

                    except Exception as e:
                        duration_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("duration_ms", duration_ms)
                        span.set_attribute("status", "error")
                        span.set_attribute("error_type", type(e).__name__)
                        span.set_attribute("error_message", str(e))

                        logger.debug(
                            "step_traced",
                            step=step_name,
                            duration_ms=duration_ms,
                            status="error",
                            error=str(e),
                        )
                        raise
            else:
                # No OTEL - just execute with logging
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "step_completed",
                        step=step_name,
                        duration_ms=duration_ms,
                        run_id=run_id,
                    )
                    return result
                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "step_failed",
                        step=step_name,
                        duration_ms=duration_ms,
                        run_id=run_id,
                        error=str(e),
                    )
                    raise

        return wrapper

    return decorator


def trace_llm_call(model_name: str):
    """
    Decorator to trace LLM calls.

    Args:
        model_name: Model name (e.g., "gemini-2.5-flash")

    Example:
        @trace_llm_call("gemini-2.5-flash")
        async def call_llm(prompt: str):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            start_time = time.time()

            # Extract prompt from args if available
            prompt = kwargs.get("prompt") or (args[0] if args else None)
            prompt_length = len(str(prompt)) if prompt else 0

            if tracer and _otel_available:
                with tracer.start_as_current_span("llm_call") as span:
                    span.set_attribute("model_name", model_name)
                    span.set_attribute("prompt_length", prompt_length)

                    try:
                        result = await func(*args, **kwargs)

                        latency_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("latency_ms", latency_ms)
                        span.set_attribute("status", "success")

                        if result:
                            span.set_attribute("response_length", len(str(result)))

                        logger.debug(
                            "llm_call_traced",
                            model=model_name,
                            latency_ms=latency_ms,
                            prompt_length=prompt_length,
                        )

                        return result

                    except Exception as e:
                        latency_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("latency_ms", latency_ms)
                        span.set_attribute("status", "error")
                        span.set_attribute("error_type", type(e).__name__)

                        logger.debug(
                            "llm_call_failed",
                            model=model_name,
                            latency_ms=latency_ms,
                            error=str(e),
                        )
                        raise
            else:
                # No OTEL - just execute with logging
                try:
                    result = await func(*args, **kwargs)
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "llm_call_completed",
                        model=model_name,
                        latency_ms=latency_ms,
                        prompt_length=prompt_length,
                    )
                    return result
                except Exception as e:
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "llm_call_failed",
                        model=model_name,
                        latency_ms=latency_ms,
                        error=str(e),
                    )
                    raise

        return wrapper

    return decorator


def trace_tool_call(tool_name: str):
    """
    Decorator to trace autonomous agent tool calls.

    Args:
        tool_name: Tool name (e.g., "get_customer_info")

    Example:
        @trace_tool_call("get_customer_info")
        async def tool_get_customer_info(customer_id: str, workspace_id: str):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            start_time = time.time()

            # Extract common identifiers from kwargs
            workspace_id = kwargs.get("workspace_id", "unknown")
            customer_id = kwargs.get("customer_id", "unknown")

            if tracer and _otel_available:
                with tracer.start_as_current_span(f"tool:{tool_name}") as span:
                    span.set_attribute("tool_name", tool_name)
                    span.set_attribute("workspace_id", str(workspace_id))
                    span.set_attribute("customer_id", str(customer_id))

                    try:
                        result = await func(*args, **kwargs)

                        latency_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("latency_ms", latency_ms)
                        span.set_attribute("status", "success")

                        # Check for error in result
                        if isinstance(result, dict) and "error" in result:
                            span.set_attribute("status", "tool_error")
                            span.set_attribute("error_message", result.get("error", ""))

                        logger.debug(
                            "tool_call_traced",
                            tool=tool_name,
                            latency_ms=latency_ms,
                            workspace_id=workspace_id,
                        )

                        return result

                    except Exception as e:
                        latency_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("latency_ms", latency_ms)
                        span.set_attribute("status", "exception")
                        span.set_attribute("error_type", type(e).__name__)
                        span.set_attribute("error_message", str(e))

                        logger.debug(
                            "tool_call_failed",
                            tool=tool_name,
                            latency_ms=latency_ms,
                            error=str(e),
                        )
                        raise
            else:
                # No OTEL - just execute with logging
                try:
                    result = await func(*args, **kwargs)
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "tool_call_completed",
                        tool=tool_name,
                        latency_ms=latency_ms,
                        workspace_id=workspace_id,
                    )
                    return result
                except Exception as e:
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "tool_call_failed",
                        tool=tool_name,
                        latency_ms=latency_ms,
                        error=str(e),
                    )
                    raise

        return wrapper

    return decorator


def trace_agent_run(agent_name: str):
    """
    Decorator to trace an entire agent run as a parent span.

    Args:
        agent_name: Agent name (e.g., "handoff_auto")

    Example:
        @trace_agent_run("handoff_auto")
        async def run_autonomous_handoff(workspace_id: str, customer_id: str):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            tracer = get_tracer()
            start_time = time.time()

            workspace_id = kwargs.get("workspace_id", "unknown")
            customer_id = kwargs.get("customer_id", "unknown")

            if tracer and _otel_available:
                with tracer.start_as_current_span(f"agent:{agent_name}") as span:
                    span.set_attribute("agent_name", agent_name)
                    span.set_attribute("workspace_id", str(workspace_id))
                    span.set_attribute("customer_id", str(customer_id))

                    try:
                        result = await func(*args, **kwargs)

                        duration_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("duration_ms", duration_ms)
                        span.set_attribute("status", "success")

                        # Extract useful info from result
                        if isinstance(result, dict):
                            span.set_attribute("run_id", result.get("run_id", ""))
                            span.set_attribute("tools_called", result.get("tools_called", 0))
                            if "quality_score" in result:
                                span.set_attribute("quality_score", result.get("quality_score", 0))

                        logger.info(
                            "agent_run_traced",
                            agent=agent_name,
                            duration_ms=duration_ms,
                            workspace_id=workspace_id,
                        )

                        return result

                    except Exception as e:
                        duration_ms = int((time.time() - start_time) * 1000)
                        span.set_attribute("duration_ms", duration_ms)
                        span.set_attribute("status", "error")
                        span.set_attribute("error_type", type(e).__name__)
                        span.set_attribute("error_message", str(e))

                        logger.error(
                            "agent_run_failed",
                            agent=agent_name,
                            duration_ms=duration_ms,
                            error=str(e),
                        )
                        raise
            else:
                # No OTEL - just execute with logging
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        "agent_run_completed",
                        agent=agent_name,
                        duration_ms=duration_ms,
                        workspace_id=workspace_id,
                    )
                    return result
                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.error(
                        "agent_run_failed",
                        agent=agent_name,
                        duration_ms=duration_ms,
                        error=str(e),
                    )
                    raise

        return wrapper

    return decorator


@contextmanager
def create_span(name: str, attributes: dict[str, Any] | None = None):
    """
    Context manager for creating custom spans.

    Args:
        name: Span name
        attributes: Optional attributes dict

    Example:
        with create_span("custom_operation", {"key": "value"}):
            # Do work
            pass
    """
    tracer = get_tracer()
    start_time = time.time()

    if tracer and _otel_available:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value) if value else "")
            try:
                yield span
                span.set_attribute("status", "success")
            except Exception as e:
                span.set_attribute("status", "error")
                span.set_attribute("error_type", type(e).__name__)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)
                span.set_attribute("duration_ms", duration_ms)
    else:
        # No OTEL - yield None
        yield None
        duration_ms = int((time.time() - start_time) * 1000)
        logger.debug("span_completed", name=name, duration_ms=duration_ms)
