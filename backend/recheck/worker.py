import asyncio
from contextlib import asynccontextmanager
import math
import time

from fastapi import FastAPI, HTTPException, Request
from opentelemetry import propagate, trace

from .admission import Admission, DeadlineExceeded, Overloaded
from .config import Settings
from .model import get_model
from .execution import Execution, ExecutionUnavailable
from .schemas import InferenceRequest
from .telemetry import telemetry
from .observability import install_metrics


def create_app(settings=None):
    settings = settings or Settings.from_env()
    tracer, display, provider = telemetry("recheck-worker")
    # Both prepared artifacts are ready before requests or model version changes.
    models = {version: get_model(version, settings.workload) for version in ("risk-v1", "risk-v2")}

    execution = Execution(settings, models)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await execution.start()
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            await asyncio.gather(*tuple(app.state.inflight), return_exceptions=True)
            await execution.close()
            provider.shutdown()

    app = FastAPI(title="RECHECK synthetic model worker", lifespan=lifespan)
    app.state.admission = Admission(settings.worker_concurrency, settings.worker_queue)
    app.state.completed = 0
    app.state.failures = 0
    app.state.display = display
    app.state.execution = execution
    app.state.inflight = set()
    app.state.ready = settings.execution_mode == "inline"

    @app.get("/live")
    async def live():
        if execution.unavailable:
            raise HTTPException(503, "model_executor_unavailable")
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        if not app.state.ready or execution.unavailable:
            raise HTTPException(503, "model_not_ready")
        return {"status": "ok", "workload": settings.workload}


    @app.get("/health")
    async def health():
        if execution.unavailable:
            raise HTTPException(503, "model_executor_unavailable")
        return {"status": "ok", "service": "recheck-worker", "models": {v: m.model_hash for v, m in models.items()},
                "workload": settings.workload, "execution_mode": settings.execution_mode,
                "active": app.state.admission.active, "admitted": app.state.admission.admitted,
                "completed": app.state.completed, "failures": app.state.failures,
                "peak_active": app.state.admission.peak_active, "peak_admitted": app.state.admission.peak_admitted}

    @app.post("/infer")
    async def infer(body: InferenceRequest, request: Request):
        started = time.monotonic()
        deadline = started + min(body.deadline_ms, settings.deadline_ms) / 1000
        try:
            model = get_model(body.model_version, settings.workload)
        except ValueError:
            raise HTTPException(503, "model_version_unavailable")
        if any(not math.isfinite(x) or x < 0 or x > 1 for x in body.features):
            raise HTTPException(422, "features must be finite values in [0,1]")
        try:
            start_ns = time.time_ns()
            with tracer.start_as_current_span("model.infer", context=propagate.extract(dict(request.headers)), kind=trace.SpanKind.SERVER) as span:
                trace_id = f"{span.get_span_context().trace_id:032x}"
                cpu_started = False
                async def compute():
                    nonlocal cpu_started
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
                        with tracer.start_as_current_span("model.predict"):
                            cpu_started = True
                            score = await execution.score(model, body.features)
                        if time.monotonic() >= deadline:
                            raise DeadlineExceeded()
                        app.state.completed += 1
                        return score
                # Shield the task, not just the executor future: the task owns admission
                # until CPU execution actually ends, even after timeout/disconnection.
                task = asyncio.create_task(compute())
                app.state.inflight.add(task)
                def finished(done):
                    app.state.inflight.discard(done)
                    if not done.cancelled():
                        done.exception()  # Retrieve late failure after the HTTP caller left.
                task.add_done_callback(finished)
                try:
                    score = await asyncio.wait_for(asyncio.shield(task), timeout=max(0, deadline - time.monotonic()))
                except (asyncio.CancelledError, TimeoutError):
                    # Queued work and synthetic delay are cancellable. A submitted
                    # process job is not: keep its admission owner alive to completion.
                    if not cpu_started:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                    raise
            return {"risk_score": score, "model_version": body.model_version,
                    "model_hash": model.model_hash,
                    "latency_ms": (time.monotonic() - started) * 1000,
                    "trace_id": trace_id, "spans": display.records(trace_id, start_ns)}
        except ExecutionUnavailable:
            app.state.failures += 1
            app.state.ready = False
            raise HTTPException(503, "model_executor_unavailable")
        except Overloaded:
            app.state.failures += 1
            raise HTTPException(429, "overloaded")
        except (TimeoutError, DeadlineExceeded):
            app.state.failures += 1
            raise HTTPException(504, "deadline_exceeded")
        except HTTPException:
            app.state.failures += 1
            raise

    install_metrics(app, "model")
    return app


app = create_app()
