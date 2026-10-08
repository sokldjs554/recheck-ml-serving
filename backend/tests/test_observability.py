"""Metrics must describe all outcomes without identifier cardinality."""
import importlib.util

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from test_recheck import setup, closing_clients, body


async def test_metrics_bound_unknown_paths_methods_and_session_ids(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        await client.post(f'/api/sessions/{sid}/decisions', json=body())
        for number in range(30):
            await client.get(f'/unknown-{number}')
            await client.request(f'CUSTOM{number}', '/unknown')
        response = await client.get('/metrics')
        assert response.status_code == 200
        metrics = response.text
        assert 'recheck_http_requests_total' in metrics
        assert sid not in metrics and '/unknown-' not in metrics and 'CUSTOM' not in metrics
        assert 'route="/api/sessions/{sid}/decisions"' in metrics
        assert 'route="unmatched"' in metrics and 'method="OTHER"' in metrics
        assert 'outcome="clear"' in metrics
        assert 'recheck_http_request_duration_seconds_bucket' in metrics


async def test_http_errors_rejections_and_exceptions_are_measured():
    assert importlib.util.find_spec('recheck.observability'), 'metrics module is missing'
    from recheck.observability import install_metrics
    app = FastAPI()
    install_metrics(app, 'model')

    @app.post('/infer')
    async def infer(status: int, reason: str = "model_unavailable"):
        if status == 500:
            raise RuntimeError('unexpected')
        raise HTTPException(status, 'overloaded' if status == 429 else reason)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://model') as client:
        for status in [429, 503, 500, 422]:
            assert (await client.post('/infer', params={'status': status})).status_code == status
        assert (await client.post('/infer', params={'status': 503, 'reason': 'model_executor_unavailable'})).status_code == 503
        metrics = (await client.get('/metrics')).text
    assert 'reason="model_executor_unavailable"' in metrics
    for status in [429, 503, 500, 422]:
        assert f'status="{status}"' in metrics
    assert 'outcome="rejected"' in metrics and 'outcome="error"' in metrics
    assert 'reason="overloaded"' in metrics
    assert 'recheck_http_inflight{service="model"} 0.0' in metrics


async def test_business_failure_is_counted_even_when_http_is_200(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request['fault'] = 'unavailable'
        response = await client.post(f'/api/sessions/{sid}/decisions', json=request)
        assert response.status_code == 200 and response.json()['reason'] == 'model_unavailable'
        metrics = (await client.get('/metrics')).text
        assert 'outcome="review",reason="model_unavailable"' in metrics
        assert 'recheck_business_duration_seconds_bucket' in metrics
        assert 'le="0.3",outcome="review",reason="model_unavailable"' in metrics


async def test_liveness_survives_dependency_failure_readiness_does_not(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        assert (await client.get('/live')).status_code == 200
        assert (await client.get('/ready')).status_code == 200
        app.state.store.engine.dispose()
        # A read-only connection points at a database file that does not exist.
        from sqlalchemy import create_engine
        app.state.store.engine = create_engine(f'sqlite:///file:{tmp_path}/missing.db?mode=ro&uri=true')
        assert (await client.get('/live')).status_code == 200
        assert (await client.get('/ready')).status_code == 503


async def test_freshness_invalidation_has_specific_bounded_outcome(tmp_path):
    import asyncio
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        request = body()
        request['delay_ms'] = 100
        pending = asyncio.create_task(client.post(f'/api/sessions/{sid}/decisions', json=request))
        while worker.state.admission.active == 0:
            await asyncio.sleep(.001)
        await client.post(f'/api/sessions/{sid}/mutations', json={'kind': 'policy'})
        assert (await pending).json()['status'] == 'invalidated'
        metrics = (await client.get('/metrics')).text
        assert 'outcome="invalidated",reason="versions_changed"' in metrics


async def test_cancellation_keeps_attempt_in_denominator():
    import asyncio
    from recheck.observability import install_metrics
    entered = asyncio.Event()
    app = FastAPI()
    install_metrics(app, 'model')

    @app.post('/infer')
    async def infer():
        entered.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://model') as client:
        task = asyncio.create_task(client.post('/infer'))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        metrics = (await client.get('/metrics')).text
        assert 'status="499"' in metrics
        assert 'outcome="cancelled",reason="request_cancelled"' in metrics
        assert 'recheck_http_inflight{service="model"} 0.0' in metrics


async def test_cors_rejections_are_http_attempts(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    async with closing_clients(model, client):
        response = await client.options('/api/sessions', headers={
            'Origin': 'https://not-permitted.example', 'Access-Control-Request-Method': 'POST'})
        assert response.status_code == 400
        assert 'status="400"' in (await client.get('/metrics')).text
