import time

import httpx
import pytest
from sqlalchemy import event

from test_recheck import body, closing_clients, setup


@pytest.mark.parametrize("budget,code,reason", [(60, 504, "deadline_exceeded_after_commit"), (250, 409, "receipt_expired_after_commit")])
async def test_slow_final_database_write_cannot_deliver_a_late_clear(tmp_path, budget, code, reason):
    app, worker, model, client, sid = await setup(tmp_path, deadline_ms=budget, receipt_ttl_ms=70)
    @event.listens_for(app.state.store.engine, "before_cursor_execute")
    def slow_write(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE decisions"):
            time.sleep(0.1)
    async with closing_clients(model, client):
        started = time.monotonic()
        response = await client.post(f"/api/sessions/{sid}/decisions", json=body())
        elapsed_ms = (time.monotonic() - started) * 1000
        assert response.status_code == code, f"Delivered {response.status_code} after {elapsed_ms:.1f} ms"
        assert response.json()["detail"] == reason
        # Persistence is an immutable historical fact; delivery failure must not
        # rewrite it or execute a second inference on an idempotent retry.
        stored = (await client.get(f"/api/sessions/{sid}/decisions")).json()["receipts"][0]
        retry = await client.post(f"/api/sessions/{sid}/decisions", json=body())
        assert retry.status_code == 200
        assert retry.json() == stored
        assert worker.state.completed == 1
        validation = (await client.get(f"/api/sessions/{sid}/decisions/{stored['id']}/validate")).json()
        assert validation["valid"] is False
        assert validation["reason"] == "expired"


@pytest.mark.parametrize("sampler", ["parentbased_always_on", "always_off"])
async def test_unsampled_traces_do_not_break_gateway_or_worker(tmp_path, monkeypatch, sampler):
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", sampler)
    app, worker, model, client, sid = await setup(tmp_path)
    trace_id = "0123456789abcdef0123456789abcdef"
    headers = {"traceparent": f"00-{trace_id}-0123456789abcdef-00"}
    async with closing_clients(model, client):
        response = await client.post(f"/api/sessions/{sid}/decisions", json=body(), headers=headers)
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["status"] == "clear"
        assert receipt["trace_id"] == trace_id
        assert receipt["spans"] == []
        direct = await model.post("/infer", json={"features": [0.1, 0, 0, 0.1], "model_version": "risk-v1",
                    "delay_ms": 0, "fault": "none", "deadline_ms": 300}, headers=headers)
        assert direct.status_code == 200
        assert direct.json()["trace_id"] == trace_id
        assert direct.json()["spans"] == []
