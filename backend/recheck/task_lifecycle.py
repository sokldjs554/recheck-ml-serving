"""Keep ownership of synchronous work through repeated caller cancellation."""
import asyncio
import json
import logging

from opentelemetry import trace

logger = logging.getLogger("recheck.lifecycle")


async def run_owned_thread(fn, *args, **kwargs):
    # Cancelling a to_thread task cannot stop its underlying thread. Never await
    # that task unshielded, including while joining after the first cancellation.
    task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        error = task.exception()  # retrieve late exceptions, without leaking SQL/DSNs
        if error is not None:
            logger.warning(json.dumps({
                "event": "owned_work_failed_after_cancel",
                "operation": getattr(fn, "__name__", "call"),
                "error_type": type(error).__name__,
                "trace_id": f"{trace.get_current_span().get_span_context().trace_id:032x}",
            }))
        raise asyncio.CancelledError()
    return task.result()
