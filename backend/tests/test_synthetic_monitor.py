"""Monitor must fail closed and count failed/slow probes in its denominator."""
import importlib.util
from pathlib import Path
import sys
import httpx
import pytest


def monitor():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'synthetic_monitor.py'
    assert path.exists(), 'scheduled monitor implementation missing'
    spec = importlib.util.spec_from_file_location('synthetic_monitor', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_slo_counts_failures_and_slowness():
    m = monitor()
    rows = [{'ok': True, 'duration_ms': 50}, {'ok': False, 'duration_ms': 5}, {'ok': True, 'duration_ms': 6000}]
    result = m.summarize(rows, target=0.99, budget_ms=5000)
    assert result['total'] == 3
    assert result['good'] == 1
    assert result['availability'] == pytest.approx(1 / 3)
    assert result['budget_consumed_ratio'] == pytest.approx(2 / .03)
    assert m.summarize([], target=.99, budget_ms=5000)['availability'] is None


@pytest.mark.asyncio
async def test_http_ok_with_wrong_service_is_failure():
    m = monitor()
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'status':'ok','service':'unrelated','mode':'live'}))) as client:
        row = await m.probe(client)
    assert row['ok'] is False
    assert row['failed_step'] == 'health'


def workflow_transport(initial_valid=True, changed_version=2, final_valid=False, final_reason="versions_changed"):
    checks = 0
    initial = {"feature_version": 1, "policy_version": 1, "model_version": "risk-v1"}
    changed = {**initial, "feature_version": changed_version}
    def handler(r):
        nonlocal checks
        if r.url.path == '/health': return httpx.Response(200, json={'status':'ok','service':'recheck-api','mode':'live'})
        if r.url.path.endswith('/validate'):
            checks += 1
            payload = {'valid':initial_valid,'reason':'current' if initial_valid else 'expired','current_versions':initial} if checks == 1 else {'valid':final_valid,'reason':final_reason,'current_versions':changed}
            return httpx.Response(200,json=payload)
        if r.url.path.endswith('/mutations'): return httpx.Response(200,json=changed)
        if r.url.path.endswith('/decisions'): return httpx.Response(200,json={'id':'r','status':'clear','model_hash':'a'*64,'trace_id':'b'*32,**initial})
        return httpx.Response(200,json={'session_id':'s',**initial})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_stale_result_being_accepted_fails_monitor():
    m = monitor()
    async with httpx.AsyncClient(base_url='https://owned.example', transport=workflow_transport(final_valid=True)) as client:
        row = await m.probe(client)
    assert row['ok'] is False
    assert row['failed_step'] == 'stale_rejection'


@pytest.mark.asyncio
@pytest.mark.parametrize('options,step', [({'initial_valid':False},'current_validation'),({'changed_version':1},'mutation'),({'final_reason':'expired'},'stale_rejection')])
async def test_broken_validation_or_no_mutation_cannot_pass(options, step):
    m = monitor()
    async with httpx.AsyncClient(base_url='https://owned.example', transport=workflow_transport(**options)) as client:
        row = await m.probe(client)
    assert row['ok'] is False
    assert row['failed_step'] == step


@pytest.mark.asyncio
async def test_valid_then_version_changed_probe_succeeds():
    m = monitor()
    async with httpx.AsyncClient(base_url='https://owned.example', transport=workflow_transport()) as client:
        row = await m.probe(client)
    assert row['ok'] is True
    assert row['steps'] == ['health','session','inference','current_validation','mutation','stale_rejection']


@pytest.mark.asyncio
async def test_malformed_health_json_is_recorded_as_failed_probe():
    m = monitor()
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(lambda r: httpx.Response(200,json=[]))) as client:
        row = await m.probe(client)
    assert row['ok'] is False
    assert row['failed_step'] == 'health'
    assert row['duration_ms'] >= 0
