import asyncio
import time

import httpx
import pytest

from recheck.config import Settings
from recheck.model import get_model
from recheck.worker import create_app


def test_cpu_ensemble_has_reproducible_epoch_and_workload_identity():
    model = get_model('risk-v1', workload='cpu-ensemble')
    features = [0.4, 1, 0, 0.3]
    assert model.score(features) == model.score(features)
    assert 0 <= model.score(features) <= 1
    assert model.model_hash != get_model('risk-v1', workload='lightweight').model_hash
    assert model.model_hash != get_model('risk-v3', workload='cpu-ensemble').model_hash
    assert model.score(features) == get_model('risk-v3', workload='cpu-ensemble').score(features)
    assert model.report['scenario_rows'] >= 1024
    assert model.report['test_auc'] > 0.65


@pytest.mark.parametrize('field,value', [('workload', 'fake'), ('execution_mode', 'threads')])
def test_unknown_compute_configuration_rejected(field, value):
    with pytest.raises(ValueError):
        Settings(**{field: value})


async def test_isolated_inference_keeps_health_responsive_and_cancelled_capacity_occupied():
    worker = create_app(Settings(workload='cpu-ensemble', execution_mode='process', worker_concurrency=1, worker_queue=0, deadline_ms=2000))
    async with worker.router.lifespan_context(worker):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker), base_url='http://worker') as client:
            body = dict(features=[0.4, 1, 0, 0.3], model_version='risk-v1', deadline_ms=2000)
            pending = asyncio.create_task(client.post('/infer', json=body))
            until = time.monotonic() + 2
            while worker.state.execution.submitted == 0:
                assert time.monotonic() < until
                await asyncio.sleep(0)
            health = (await client.get('/health')).json()
            assert health['active'] == 1
            assert health['completed'] == 0
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert worker.state.admission.active == 1
            rejected = await client.post('/infer', json=body)
            assert rejected.status_code == 429
            await asyncio.gather(*tuple(worker.state.inflight))
            assert worker.state.admission.admitted == 0
            response = await client.post('/infer', json=body)
            assert response.status_code == 200
            assert response.json()['model_hash'] == get_model('risk-v1', workload='cpu-ensemble').model_hash


async def test_cpu_deadline_returns_504_before_execution_releases_admission():
    worker = create_app(Settings(workload='cpu-ensemble', execution_mode='process', worker_concurrency=1, worker_queue=0, deadline_ms=2000))
    async with worker.router.lifespan_context(worker):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker), base_url='http://worker') as client:
            response = await client.post('/infer', json=dict(features=[0.4, 1, 0, 0.3], model_version='risk-v1', deadline_ms=1))
            assert response.status_code == 504
            assert worker.state.execution.submitted == 1
            assert worker.state.admission.active == worker.state.admission.admitted == 1
            await asyncio.gather(*tuple(worker.state.inflight), return_exceptions=True)
            assert worker.state.admission.admitted == 0
            assert worker.state.completed == 0


async def test_dead_pool_fails_inference_readiness_health_and_liveness_closed():
    worker = create_app(Settings(workload='cpu-ensemble', execution_mode='process', worker_concurrency=1))
    async with worker.router.lifespan_context(worker):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker, raise_app_exceptions=False), base_url='http://worker') as client:
            assert (await client.get('/ready')).status_code == 200
            # Abrupt failure of an owned CPU child, not a mock executor exception.
            child = next(iter(worker.state.execution.pool._processes.values()))
            child.kill()
            await asyncio.to_thread(child.join, 2)
            assert not child.is_alive()
            until = time.monotonic() + 2
            while (await client.get('/ready')).status_code != 503:
                assert time.monotonic() < until, 'idle pool death never failed readiness'
                await asyncio.sleep(0.001)
            response = await client.post('/infer', json=dict(features=[0.4, 1, 0, 0.3], model_version='risk-v1', deadline_ms=300))
            assert response.status_code == 503
            assert response.json()['detail'] == 'model_executor_unavailable'
            assert (await client.get('/ready')).status_code == 503
            assert (await client.get('/health')).status_code == 503
            assert (await client.get('/live')).status_code == 503
            assert worker.state.admission.admitted == 0
