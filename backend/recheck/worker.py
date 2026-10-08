import asyncio
from contextlib import asynccontextmanager
import math
import time

from fastapi import FastAPI, HTTPException, Request
from opentelemetry import propagate, trace

from .admission import Admission, DeadlineExceeded, Overloaded
from .config import Settings
from .model import get_model
from .schemas import InferenceRequest
from .telemetry import telemetry


def create_app(settings=None):
    settings = settings or Settings.from_env()
    tracer, display, provider = telemetry("recheck-worker")
    # Both prepared artifacts are ready before requests or model version changes.
    models = {version: get_model(version) for version in ("risk-v1", "risk-v2")}

    @asynccontextmanager
    async def lifespan(app):
        yield
        provider.shutdown()

    app = FastAPI(title="RECHECK synthetic model worker", lifespan=lifespan)
    app.state.admission = Admission(settings.worker_concurrency, settings.worker_queue)
    app.state.completed = 0
    app.state.failures = 0
    app.state.display = display

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "recheck-worker", "models": {v: m.model_hash for v, m in models.items()},
                "active": app.state.admission.active, "admitted": app.state.admission.admitted,
                "completed": app.state.completed, "failures": app.state.failures,
                "peak_active": app.state.admission.peak_active, "peak_admitted": app.state.admission.peak_admitted}

    @app.post("/infer")
    async def infer(body: InferenceRequest, request: Request):
        started = time.monotonic()
        deadline = started + min(body.deadline_ms, settings.deadline_ms) / 1000
        try:
            model = get_model(body.model_version)
        except ValueError:
            raise HTTPException(503, "model_version_unavailable")
        if any(not math.isfinite(x) or x < 0 or x > 1 for x in body.features):
            raise HTTPException(422, "features must be finite values in [0,1]")
        try:
            start_ns = time.time_ns()
            with tracer.start_as_current_span("model.infer", context=propagate.extract(dict(request.headers)), kind=trace.SpanKind.SERVER) as span:
                trace_id = f"{span.get_span_context().trace_id:032x}"
                async with app.state.admission.slot(deadline):
                    if body.fault == "unavailable":
                        raise HTTPException(503, "model_unavailable")
                    delay = body.delay_ms / 1000 if body.fault != "timeout" else body.deadline_ms / 1000 + 0.05
                    remaining = deadline - time.monotonic()
                    if delay:
                        with tracer.start_as_current_span("model.injected_delay"):
                            await asyncio.wait_for(asyncio.sleep(delay), timeout=max(0, remaining))
                    if time.monotonic() >= deadline:
                        raise DeadlineExceeded()
                    # Tiny deterministic logistic regression executes synchronously. There is
                    # no cancellable thread whose semaphore could be released before CPU work ends.
                    with tracer.start_as_current_span("model.predict"):
                        score = model.score(body.features)
                    if time.monotonic() >= deadline:
                        raise DeadlineExceeded()
                    app.state.completed += 1
            return {"risk_score": score, "model_version": body.model_version,
                    "model_hash": model.model_hash,
                    "latency_ms": (time.monotonic() - started) * 1000,
                    "trace_id": trace_id, "spans": display.records(trace_id, start_ns)}
        except Overloaded:
            app.state.failures += 1
            raise HTTPException(429, "overloaded")
        except (TimeoutError, DeadlineExceeded):
            app.state.failures += 1
            raise HTTPException(504, "deadline_exceeded")
        except HTTPException:
            app.state.failures += 1
            raise

    return app


app = create_app()
