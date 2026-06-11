"""
Langfuse ADK callbacks — superseded by OTel auto-instrumentation.

Google ADK is now instrumented via openinference-instrumentation-google-adk which
automatically captures every agent call, tool call, and model completion as OTel
spans exported to Langfuse. The manual after_model_callback approach below is no
longer needed and has been replaced with a no-op.

The stub is kept so existing specialist imports (`from .langfuse_callbacks import
after_model_callback_langfuse`) continue to compile without changes. The callbacks
can safely be removed from specialist builders in a follow-up cleanup.
"""


async def after_model_callback_langfuse(callback_context, llm_response):
    """OTel auto-instrumentation handles Langfuse tracing. We additionally capture each
    model output to Firestore for the Lab trace view. Deferred import avoids a circular
    import with callbacks.py. Best-effort; returns None to leave the response unchanged."""
    try:
        from .callbacks import stream_model_output
        await stream_model_output(callback_context, llm_response)
    except Exception:
        pass
    return None
