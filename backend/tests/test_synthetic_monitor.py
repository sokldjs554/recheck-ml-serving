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


@pytest.mark.asyncio
async def test_step_timings_identify_slow_request_without_changing_budget(monkeypatch):
    m = monitor()
    clock = [0.0]
    monkeypatch.setattr(m.time, 'perf_counter', lambda: clock[0])
    original = workflow_transport()
    def handler(request):
        clock[0] += 54 if request.url.path == '/health' else .1
        return original.handle_request(request)
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(handler)) as client:
        row = await m.probe(client)
    assert row['ok'] is True
    assert row['duration_ms'] == pytest.approx(54500)
    assert [entry['step'] for entry in row['requests']] == row['steps']
    assert {k:v for k,v in row['requests'][0].items() if k != 'request_trace_id'} == {'step':'health', 'method':'GET', 'duration_ms':54000.0, 'http_status':200}
    assert len(row['requests'][0]['request_trace_id']) == 32
    assert row['requests'][2]['duration_ms'] == pytest.approx(100)
    assert m.summarize([row], budget_ms=5000)['bad'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['timeout', 'http', 'semantic'])
async def test_failed_request_keeps_its_timing_without_logging_payload_or_url(failure):
    m = monitor()
    def handler(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret URL and credentials', request=request)
        return httpx.Response(503 if failure == 'http' else 200, json={'secret':'do not log'})
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(handler)) as client:
        row = await m.probe(client)
    assert row['ok'] is False and row['failed_step'] == 'health'
    assert len(row['requests']) == 1
    entry = row['requests'][0]
    assert entry['step'] == 'health' and entry['duration_ms'] >= 0
    assert entry['http_status'] == (None if failure == 'timeout' else 503 if failure == 'http' else 200)
    assert set(entry) <= {'step','method','duration_ms','http_status','error_type','request_trace_id'}
    assert 'secret' not in str(row) and 'owned.example' not in str(row)


@pytest.mark.asyncio
async def test_probe_keeps_safe_health_phases_and_trace_on_failure():
    m = monitor()
    seen = []
    def handler(request):
        seen.append(request.headers.get('traceparent'))
        return httpx.Response(503, json={'detail':'database_unavailable'}, headers={
            'Server-Timing':'health_db;dur=24.3, health_app;dur=25.1, secret;dur=999',
            'X-Recheck-Trace-Id': 'a'*32,
            'Authorization':'secret'})
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(handler)) as client:
        row = await m.probe(client)
    assert seen[0] and len(seen[0]) == 55
    item = row['requests'][0]
    assert item['request_trace_id'] == seen[0].split('-')[1]
    assert item['response_trace_id'] == 'a'*32
    assert item['server_phases_ms'] == {'health_db':24.3, 'health_app':25.1}
    assert 'secret' not in str(row)
    assert not row['ok'] and m.summarize([row])['bad'] == 1


@pytest.mark.asyncio
async def test_timeout_retains_sent_trace_without_inventing_server_timings():
    m = monitor()
    sent = []
    def handler(request):
        sent.append(request.headers.get('traceparent'))
        raise httpx.ReadTimeout('private address', request=request)
    async with httpx.AsyncClient(base_url='https://owned.example', transport=httpx.MockTransport(handler)) as client:
        row = await m.probe(client)
    assert sent[0]
    item = row['requests'][0]
    assert item['request_trace_id'] == sent[0].split('-')[1]
    assert 'server_phases_ms' not in item and 'response_trace_id' not in item
    assert row['failed_step'] == 'health' and item['http_status'] is None
