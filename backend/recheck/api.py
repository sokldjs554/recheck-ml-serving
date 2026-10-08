import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from opentelemetry import propagate, trace
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from .admission import Admission, DeadlineExceeded, Overloaded
from .config import Settings
from .model import get_model
from .observability import install_metrics
from .schemas import DecisionRequest, MutationRequest
from .store import Store
from .telemetry import finishing_span, telemetry

logger = logging.getLogger("recheck")


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def create_app(settings=None, model_client=None):
    settings = settings or Settings.from_env()
    store = Store(settings)
    tracer, display, provider = telemetry("recheck-api")
    expected_hashes = {v: get_model(v, settings.workload).model_hash for v in ("risk-v1", "risk-v2")}
    supplied_client = model_client is not None
    model_client = model_client or httpx.AsyncClient(base_url=settings.model_service_url, limits=httpx.Limits(max_connections=settings.gateway_concurrency, max_keepalive_connections=settings.gateway_concurrency), trust_env=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if not supplied_client:
            await model_client.aclose()
        store.engine.dispose()
        provider.shutdown()

    app = FastAPI(title="RECHECK version-fenced inference receipts", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type", "traceparent", "tracestate"])
    install_metrics(app, "api")
    app.state.store = store
    app.state.admission = Admission(settings.gateway_concurrency, settings.gateway_queue)
    app.state.active_sessions = Counter()
    app.state.display = display

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error("database operation failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "database_unavailable"})

    @app.get("/ready")
    @app.get("/health")
    async def health():
        def check_database():
            with store.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        try:
            await asyncio.to_thread(check_database)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "database_unavailable") from exc
        try:
            response = await model_client.get("/health", timeout=0.3)
            response.raise_for_status()
            if response.json().get("models") != expected_hashes:
                raise HTTPException(503, "model_registry_mismatch")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, "model_unavailable") from exc
        return {"status": "ok", "service": "recheck-api", "mode": "live", "model_service": settings.model_service_url}

    @app.post("/api/sessions")
    async def create_session():
        return store.create_session()

    @app.post("/api/sessions/{sid}/mutations")
    async def mutate(sid: str, body: MutationRequest):
        return store.mutate(sid, body.kind)

    @app.get("/api/sessions/{sid}/decisions")
    async def receipts(sid: str):
        return {"receipts": store.receipts(sid)}

    @app.get("/api/sessions/{sid}/decisions/{did}/validate")
    async def validate(sid: str, did: str):
        return store.validate(sid, did)

    @app.get("/api/sessions/{sid}/metrics")
    async def metrics(sid: str):
        return store.metrics(sid, app.state.active_sessions[sid])

    @app.post("/api/sessions/{sid}/decisions")
    async def decide(sid: str, body: DecisionRequest, request: Request):
        started = time.monotonic()
        deadline = started + settings.deadline_ms / 1000
        try:
            async with app.state.admission.slot(deadline):
                app.state.active_sessions[sid] += 1
                try:
                    receipt = await admitted_decision(sid, body, request, started, deadline)
                    # ORM flush/commit occurs after finalization. Preserve the
                    # immutable historical receipt, but do not deliver clear work
                    # that this request already knows missed its delivery budget.
                    if receipt["status"] == "clear" and time.monotonic() >= deadline:
                        raise HTTPException(504, "deadline_exceeded_after_commit")
                    return receipt
                finally:
                    app.state.active_sessions[sid] -= 1
                    if app.state.active_sessions[sid] == 0:
                        del app.state.active_sessions[sid]
        except Overloaded:
            raise HTTPException(429, "overloaded")
        except DeadlineExceeded:
            raise HTTPException(504, "deadline_exceeded_before_admission")

    async def admitted_decision(sid, body, request, started, deadline):
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(exclude={"idempotency_key"}), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        start_ns = time.time_ns()
        with finishing_span(tracer, "decision", context=propagate.extract(dict(request.headers)), kind=trace.SpanKind.SERVER) as root:
            trace_id = f"{root.get_span_context().trace_id:032x}"
            with tracer.start_as_current_span("snapshot"):
                did, snapshot, existing = store.reserve(sid, body.idempotency_key, fingerprint)
            if existing is not None:
                return existing
            if snapshot is None:
                while time.monotonic() < deadline:
                    receipt, reserved_at = store.pending(sid, did)
                    if receipt is not None:
                        return receipt
                    # A crashed owner is never silently replaced by another model
                    # execution. Report the abandoned reservation and require a new key.
                    if time.time() > reserved_at + settings.deadline_ms / 1000 + 0.25:
                        raise HTTPException(409, "abandoned_request_requires_new_key")
                    await asyncio.sleep(0.005)
                raise HTTPException(409, "request_in_progress_retry_same_key")

            worker_spans = []
            score = None
            status, reason = "review", "model_unavailable"
            cancelled = False
            try:
                if body.protected and time.time() >= snapshot["updated_at"] + settings.feature_ttl_ms / 1000:
                    reason = "feature_stale"
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    with tracer.start_as_current_span("model.http", kind=trace.SpanKind.CLIENT) as model_span:
                        headers = {}
                        propagate.inject(headers)
                        features = [min(body.amount / 2000000, 1), float(body.recipient != "demo-recipient"),
                                    min((snapshot["feature_version"] - 1) / 2, 1), 0.15]
                        response = await asyncio.wait_for(model_client.post("/infer", json={"features": features, "model_version": snapshot["model_version"],
                            "delay_ms": body.delay_ms, "fault": body.fault, "deadline_ms": max(1, remaining * 1000)}, headers=headers, timeout=remaining), timeout=remaining)
                        if response.status_code != 200:
                            reason = {429: "overloaded", 504: "deadline_exceeded"}.get(response.status_code, "model_unavailable")
                            model_span.set_status(trace.StatusCode.ERROR, reason)
                        else:
                            result = response.json()
                            if result.get("model_version") != snapshot["model_version"] or result.get("model_hash") != get_model(snapshot["model_version"], settings.workload).model_hash:
                                reason = "model_version_mismatch"
                                model_span.set_status(trace.StatusCode.ERROR, reason)
                            else:
                                score = float(result["risk_score"])
                                if not 0 <= score <= 1:
                                    raise ValueError("invalid score")
                                # Each session owns its policy version. A changed policy is
                                # evaluated only when versions match at the final fence.
                                threshold = 0.65 if snapshot["policy_version"] % 2 else 0.45
                                status = "clear" if score < threshold else "review"
                                reason = "no_current_warning" if status == "clear" else "risk_signal"
                                worker_spans = result.get("spans", [])[:16]
            except (TimeoutError, httpx.TimeoutException):
                status, reason, score = "review", "deadline_exceeded", None
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                status, reason, score = "review", "model_unavailable", None
            except asyncio.CancelledError:
                status, reason, score = "review", "request_cancelled", None
                cancelled = True
            if time.monotonic() > deadline and status == "clear":
                status, reason, score = "review", "deadline_exceeded", None
            receipt = {"id": did, "session_id": sid, "status": status, "reason": reason, "risk_score": score,
                       **{k: snapshot[k] for k in ("feature_version", "policy_version", "model_version")},
                       "created_at": iso(snapshot["created_at"]), "expires_at": iso(snapshot["created_at"] + settings.receipt_ttl_ms / 1000),
                       "latency_ms": (time.monotonic() - started) * 1000, "trace_id": trace_id,
                       "spans": [], "protected": body.protected, "model_hash": get_model(snapshot["model_version"], settings.workload).model_hash}
            if status != "clear":
                root.set_status(trace.StatusCode.ERROR, reason)
            with finishing_span(tracer, "fence.commit") as fence:
                # Versions are locked in finish; this short transaction is the
                # receipt issuance linearization point, not the later HTTP send.
                def finalize(fenced_receipt):
                    # The final row lock may consume the remaining time budget.
                    # Never issue a clear result merely because HTTP inference
                    # completed before the deadline but the fence did not.
                    if fenced_receipt["status"] == "clear" and time.monotonic() >= deadline:
                        fenced_receipt.update(status="review", reason="deadline_exceeded", risk_score=None)
                    if fenced_receipt["status"] != "clear":
                        root.set_status(trace.StatusCode.ERROR, fenced_receipt["reason"])
                    fence.end()
                    root.end()
                    local_spans = display.records(trace_id, start_ns)
                    http_span = next((s for s in local_spans if s["name"] == "model.http"), None)
                    if http_span:
                        # Keep remote spans within their HTTP request, without assuming
                        # synchronized wall clocks. Full OTel exports retain true times.
                        for item in worker_spans:
                            local_spans.append({"name": item["name"], "start_ms": http_span["start_ms"] + item["start_ms"],
                                                "duration_ms": item["duration_ms"], "status": item["status"]})
                    fenced_receipt["spans"] = sorted(local_spans, key=lambda span: span["start_ms"])
                    fenced_receipt["latency_ms"] = (time.monotonic() - started) * 1000
                    return fenced_receipt
                receipt = store.finish(sid, did, snapshot, receipt, finalize=finalize)
        logger.info(json.dumps({"receipt_id": did, "session_id": sid, "trace_id": trace_id,
                                "status": receipt["status"], "reason": receipt["reason"]}))
        if cancelled:
            raise asyncio.CancelledError()
        if receipt["status"] == "clear":
            if time.monotonic() >= deadline:
                raise HTTPException(504, "deadline_exceeded_after_commit")
            if time.time() >= datetime.fromisoformat(receipt["expires_at"]).timestamp():
                raise HTTPException(409, "receipt_expired_after_commit")
        return receipt

    return app


app = create_app()
