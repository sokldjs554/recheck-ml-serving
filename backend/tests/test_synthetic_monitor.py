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


@pytest.mark.asyncio
async def test_stale_result_being_accepted_fails_monitor():
    m = monitor()
    def handler(r):
        if r.url.path == '/health': return httpx.Response(200, json={'status':'ok','service':'recheck-api','mode':'live'})
        if r.url.path.endswith('/validate'): return httpx.Response(200,json={'valid':True})
        if r.url.path.endswith('/mutations'): return httpx.Response(200,json={})
        if r.url.path.endswith('/decisions'): return httpx.Response(200,json={'id':'r','status':'clear','model_hash':'hash','trace_id':'trace'})
        return httpx.Response(200,json={'session_id':'s'})
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(handler)) as client:
        row = await m.probe(client)
    assert row['ok'] is False
    assert row['failed_step'] == 'stale_rejection'
