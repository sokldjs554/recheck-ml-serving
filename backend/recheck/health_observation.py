"""Readiness phase envelopes; excludes host startup and client network transit."""
from contextlib import contextmanager
import json
import logging
import time

from fastapi import HTTPException
from opentelemetry import propagate, trace

logger = logging.getLogger("recheck.health")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


class HealthObservation:
    def __init__(self, tracer):
        self.tracer = tracer
        self.phases = {}

    @contextmanager
    def phase(self, name):
        started = time.perf_counter()
        try:
            with self.tracer.start_as_current_span("health." + name):
                yield
        finally:
            self.phases[name] = round((time.perf_counter() - started) * 1000, 3)


@contextmanager
def observe_health(tracer, request=None, response=None):
    started = time.perf_counter()
    observation = HealthObservation(tracer)
    error, outcome = None, "ok"
    with tracer.start_as_current_span("health",
            context=propagate.extract(request.headers) if request is not None else None) as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        try:
            yield observation
        except HTTPException as exc:
            error, outcome = exc, str(exc.detail)
            span.set_status(trace.StatusCode.ERROR, outcome)
            raise
        except BaseException as exc:
            outcome = "cancelled" if type(exc).__name__ == "CancelledError" else "unexpected"
            span.set_status(trace.StatusCode.ERROR, outcome)
            raise
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            phases = observation.phases
            names = {"database": "health_db", "model_http": "health_model"}
            timing = [f"{names[name]};dur={value}" for name, value in phases.items()]
            timing.append(f"health_app;dur={elapsed}")
            headers = {"X-Recheck-Trace-Id": trace_id, "Server-Timing": ", ".join(timing)}
            if error is not None:
                error.headers = {**(error.headers or {}), **headers}
            elif response is not None:
                response.headers.update(headers)
            logger.info(json.dumps(dict(event="health_finished", trace_id=trace_id,
                outcome=outcome, duration_ms=elapsed, phases_ms=phases)))
