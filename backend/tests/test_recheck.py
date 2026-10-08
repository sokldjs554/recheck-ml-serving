"""Each test asserts externally visible behavior using a real worker and database."""
import asyncio
import importlib.util
import os
from datetime import datetime
from contextlib import asynccontextmanager

import httpx
import pytest


def applications(tmp_path, **overrides):
    assert importlib.util.find_spec("recheck.api"), "Gateway application is not implemented"
    from recheck.api import create_app
    from recheck.config import Settings
    from recheck.worker import create_app as worker_app
    settings = Settings(database_url=os.getenv("RECHECK_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}"), **overrides)
    worker = worker_app(settings)
    model_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=worker), base_url="http://worker")
    app = create_app(settings, model_client=model_client)
    return app, worker, model_client


@asynccontextmanager
async def closing_clients(*clients):
    try:
        yield
    finally:
        for client in clients:
            await client.aclose()


async def session(client):
    response = await client.post("/api/sessions")
    assert response.status_code == 200
    return response.json()["session_id"]


def body(key="same", **overrides):
    return dict(amount=150000, recipient="demo-recipient", idempotency_key=key,
                delay_ms=0, fault="none", protected=True, **overrides)


async def setup(tmp_path, **overrides):
    app, worker, model = applications(tmp_path, **overrides)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api")
    sid = await session(client)
    return app, worker, model, client, sid


async def test_trained_model_is_reproducible_and_sensitive_to_features():
    assert importlib.util.find_spec("recheck.model"), "Trained model is not implemented"
    from recheck.model import train_model
    first, second = train_model("risk-v1"), train_model("risk-v1")
    assert first.model_hash == second.model_hash
    assert len(first.model_hash) == 64
    assert first.score([0.1, 0, 0, 0.1]) < first.score([0.95, 1, 1, 0.9])
    assert first.report["test_auc"] > 0.8


async def test_receipt_and_trace_contain_actual_worker_inference(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        response = await client.post(f"/api/sessions/{sid}/decisions", json=body())
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["status"] == "clear"
        assert 0 < receipt["risk_score"] < 1
        assert len(receipt["model_hash"]) == 64
        assert len(receipt["trace_id"]) == 32
        assert {"decision", "snapshot", "model.http", "fence.commit"} <= {s["name"] for s in receipt["spans"]}
        assert worker.state.completed == 1
        valid = (await client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate")).json()
        assert valid["valid"] is True
        assert datetime.fromisoformat(receipt["expires_at"]) > datetime.fromisoformat(receipt["created_at"])


@pytest.mark.parametrize("kind", ["feature", "policy", "model"])
async def test_update_during_inference_cannot_issue_usable_receipt(tmp_path, kind):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 100
        pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(0.001)
        mutation = await client.post(f"/api/sessions/{sid}/mutations", json={"kind": kind})
        assert mutation.status_code == 200
        receipt = (await pending).json()
        assert receipt["status"] == "invalidated"
        assert receipt["reason"] == "versions_changed"
        assert (await client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate")).json()["valid"] is False


async def test_use_time_validation_rejects_later_updates_and_session_isolation(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        other = await session(client)
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        await client.post(f"/api/sessions/{other}/mutations", json={"kind": "feature"})
        url = f"/api/sessions/{sid}/decisions/{receipt['id']}/validate"
        assert (await client.get(url)).json()["valid"] is True
        await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "feature"})
        assert (await client.get(url)).json() ["reason"] == "versions_changed"
        assert (await client.get(f"/api/sessions/{other}/decisions/{receipt['id']}/validate")).status_code == 404


async def test_expiry_is_checked_at_use(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, receipt_ttl_ms=30)
    async with closing_clients(model, client):
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        await asyncio.sleep(0.05)
        validation = (await client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate")).json()
        assert validation["valid"] is False
        assert validation["reason"] == "expired"


async def test_simultaneous_retries_create_one_receipt_and_one_model_call(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 60
        responses = await asyncio.gather(*[client.post(f"/api/sessions/{sid}/decisions", json=request) for _ in range(6)])
        assert all(r.status_code == 200 for r in responses)
        assert len({r.json()["id"] for r in responses}) == 1
        assert worker.state.completed == 1
        receipts = (await client.get(f"/api/sessions/{sid}/decisions")).json()["receipts"]
        assert len(receipts) == 1


async def test_reusing_key_with_changed_body_conflicts(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        await client.post(f"/api/sessions/{sid}/decisions", json=body())
        request = body()
        request["amount"] = 900000
        assert (await client.post(f"/api/sessions/{sid}/decisions", json=request)).status_code == 409


@pytest.mark.parametrize("fault,reason", [("unavailable", "model_unavailable"), ("timeout", "deadline_exceeded")])
async def test_provider_failure_is_explicit_review(tmp_path, fault, reason):
    app, worker, model, client, sid = await setup(tmp_path, deadline_ms=80)
    async with closing_clients(model, client):
        request = body()
        request["fault"] = fault
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=request)).json()
        assert receipt["status"] == "review"
        assert receipt["reason"] == reason
        assert receipt["risk_score"] is None
        assert any(s["status"] == "error" for s in receipt["spans"])
        await asyncio.sleep(0.02)
        assert worker.state.admission.active == 0


async def test_gateway_and_worker_admission_are_bounded(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, gateway_concurrency=2, gateway_queue=1,
                                                worker_concurrency=1, worker_queue=1, deadline_ms=120)
    async with closing_clients(model, client):
        async def run(index):
            request = body(key=str(index))
            request["delay_ms"] = 90
            return await client.post(f"/api/sessions/{sid}/decisions", json=request)
        responses = await asyncio.gather(*[run(i) for i in range(20)])
        assert all(r.status_code in (200, 429) for r in responses)
        assert any(r.status_code == 429 or r.json()["reason"] == "overloaded" for r in responses)
        assert app.state.admission.peak_active <= 2
        assert app.state.admission.peak_admitted <= 3
        assert worker.state.admission.peak_active <= 1
        assert worker.state.admission.peak_admitted <= 2
        await asyncio.sleep(0.03)
        assert app.state.admission.admitted == worker.state.admission.admitted == 0


async def test_baseline_exhibits_stale_result_but_validator_still_rejects_it(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request.update(protected=False, delay_ms=60)
        pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(0.001)
        await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "feature"})
        receipt = (await pending).json()
        assert receipt["status"] == "clear"
        assert receipt["protected"] is False
        validation = (await client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate")).json()
        assert validation["valid"] is False


async def test_receipts_are_immutable_and_metrics_reflect_current_validity(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "policy"})
        assert (await client.get(f"/api/sessions/{sid}/decisions")).json()["receipts"][0] == receipt
        metrics = (await client.get(f"/api/sessions/{sid}/metrics")).json()
        assert metrics["total"] == 1
        assert metrics["invalidated"] == 1
        assert metrics["valid"] == metrics["active"] == 0


async def test_model_versions_are_monotonic_to_prevent_aba_revalidation(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "model"})
        version = (await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "model"})).json()
        assert version["model_version"] == "risk-v3"
        assert (await client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate")).json()["valid"] is False
        fresh = (await client.post(f"/api/sessions/{sid}/decisions", json=body(key="fresh"))).json()
        assert fresh["status"] == "clear"
        assert fresh["model_version"] == "risk-v3"
        assert fresh["model_hash"] != receipt["model_hash"]


async def test_first_committed_receipt_already_contains_complete_trace(tmp_path):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from recheck.store import Decision
    app, worker, model, client, sid = await setup(tmp_path)
    observed = []
    @event.listens_for(app.state.store.engine, "commit")
    def observe(connection):
        # A separate DB connection reads the last committed state, never uncommitted rows.
        with Session(app.state.store.engine) as observer:
            from sqlalchemy import select
            for payload in observer.scalars(select(Decision.payload).where(Decision.session_id == sid)):
                if payload is not None:
                    observed.append(payload)
    async with closing_clients(model, client):
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        observed.extend(app.state.store.receipts(sid))
        assert all(p["spans"] for p in observed), "A committed receipt was visible without trace spans"
        assert all(p == receipt for p in observed), "Receipt changed after issuance"


async def test_features_too_old_require_refresh_before_inference(tmp_path):
    import time
    from recheck.store import DemoSession
    app, worker, model, client, sid = await setup(tmp_path, feature_ttl_ms=1000)
    async with closing_clients(model, client):
        with app.state.store.transaction(write=True) as db:
            db.get(DemoSession, sid).updated_at = time.time() - 2
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=body())).json()
        assert receipt["reason"] == "feature_stale"
        assert receipt["status"] == "review"
        assert receipt["risk_score"] is None
        assert worker.state.completed == 0
        await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "feature"})
        fresh = (await client.post(f"/api/sessions/{sid}/decisions", json=body(key="fresh"))).json()
        assert fresh["reason"] != "feature_stale"


async def test_gateway_cancellation_does_not_leave_background_inference(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 200
        pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(0.001)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await asyncio.sleep(0.01)
        assert worker.state.admission.admitted == app.state.admission.admitted == 0
        receipt = (await client.get(f"/api/sessions/{sid}/decisions")).json()["receipts"][0]
        assert receipt["status"] == "review"
        assert receipt["reason"] == "request_cancelled"
        assert worker.state.completed == 0


async def test_receipt_cap_keeps_existing_idempotency_key_retrievable(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, max_receipts=1)
    async with closing_clients(model, client):
        original = await client.post(f"/api/sessions/{sid}/decisions", json=body())
        assert (await client.post(f"/api/sessions/{sid}/decisions", json=body(key="second"))).status_code == 429
        retry = await client.post(f"/api/sessions/{sid}/decisions", json=body())
        assert retry.json() == original.json()


async def test_expired_at_issuance_is_not_clear(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, receipt_ttl_ms=20)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 40
        receipt = (await client.post(f"/api/sessions/{sid}/decisions", json=request)).json()
        assert receipt["status"] == "invalidated"
        assert receipt["reason"] == "expired_at_issue"


async def test_worker_queue_rejects_overload_and_cleans_up_timeouts(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, worker_concurrency=1, worker_queue=1, deadline_ms=70)
    async with closing_clients(model, client):
        requests = [model.post("/infer", json=dict(features=[0.1, 0, 0, 0.1], model_version="risk-v1",
                    delay_ms=120, fault="none", deadline_ms=70)) for _ in range(12)]
        responses = await asyncio.gather(*requests)
        assert sum(r.status_code == 429 for r in responses) == 10
        assert sum(r.status_code == 504 for r in responses) == 2
        assert worker.state.admission.admitted == 0
        assert worker.state.completed == 0


async def test_changed_body_conflicts_even_while_first_request_pending(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 80
        pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(0.001)
        request["recipient"] = "other"
        conflict = await client.post(f"/api/sessions/{sid}/decisions", json=request)
        assert conflict.status_code == 409
        assert (await pending).status_code == 200


async def test_deadline_includes_waiting_for_the_final_database_fence(tmp_path):
    import threading
    import time
    app, worker, model, client, sid = await setup(tmp_path, deadline_ms=60)
    async with closing_clients(model, client):
        request = body()
        request["delay_ms"] = 15
        pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(0.001)
        locked = threading.Event()
        def lock_final_fence():
            with app.state.store.transaction(write=True) as db:
                app.state.store.row(db, sid, lock=True)
                locked.set()
                time.sleep(0.075)
        thread = threading.Thread(target=lock_final_fence)
        thread.start()
        for _ in range(1000):
            if locked.is_set():
                break
            await asyncio.sleep(0.001)
        assert locked.is_set()
        receipt = (await pending).json()
        thread.join()
        assert receipt["status"] == "review"
        assert receipt["reason"] == "deadline_exceeded"
