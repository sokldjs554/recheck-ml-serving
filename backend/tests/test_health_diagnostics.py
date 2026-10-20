"""Attribute readiness time to application phases without claiming network cause."""
import json
import logging
import re
import time

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from test_recheck import setup, closing_clients


@pytest.mark.parametrize('failure', [None, 'database', 'model'])
async def test_health_phases_trace_and_failure_survive_in_response_and_log(tmp_path, caplog, failure):
    caplog.set_level(logging.INFO, logger='recheck.health')
    app, worker, model, client, sid = await setup(tmp_path)
    def database_boundary(conn, cursor, statement, parameters, context, many):
        if statement == 'SELECT 1':
            if failure == 'database':
                raise OperationalError('private SQL', {}, Exception('secret DSN'))
            time.sleep(.02)
    event.listen(app.state.store.engine, 'before_cursor_execute', database_boundary)
    if failure == 'model':
        worker.state.execution._failed = True
    trace_id = '1234567890abcdef1234567890abcdef'
    try:
        async with closing_clients(model, client):
            response = await client.get('/health', headers={'traceparent':f'00-{trace_id}-1234567890abcdef-01'})
            assert response.status_code == (200 if failure is None else 503)
            assert response.headers.get('x-recheck-trace-id') == trace_id
            timings = dict((name, float(value)) for name, value in re.findall(r'(health_db|health_model|health_app);dur=([\d.]+)', response.headers['server-timing']))
            assert timings['health_app'] >= timings['health_db']
            assert ('health_model' in timings) == (failure != 'database')
            if failure != 'database':
                assert timings['health_db'] >= 20
            records = [json.loads(r.message) for r in caplog.records if r.name == 'recheck.health']
            result = next(r for r in records if r['trace_id'] == trace_id)
            assert result['outcome'] == ('ok' if failure is None else failure + '_unavailable')
            assert 'secret' not in str(result) and 'private SQL' not in str(result)
            spans = app.state.display.traces[trace_id]
            assert {'health', 'health.database'} <= {s['name'] for s in spans}
            if failure != 'database':
                assert 'health.model_http' in {s['name'] for s in spans}
            # Existing readiness response contract stays usable by the observer.
            if failure is None:
                assert response.json()['service'] == 'recheck-api'
    finally:
        event.remove(app.state.store.engine, 'before_cursor_execute', database_boundary)


async def test_real_http_probe_correlates_health_log_and_keeps_original_budget(tmp_path):
    import os
    from test_http_processes import servers
    from test_synthetic_monitor import monitor
    if os.getenv('RECHECK_NETWORK_TESTS') != '1':
        pytest.skip('set RECHECK_NETWORK_TESTS=1 for loopback process verification')
    with servers(tmp_path) as (api_url, _):
        async with httpx.AsyncClient(base_url=api_url, trust_env=False) as client:
            row = await monitor().probe(client)
        assert row['ok']
        health = row['requests'][0]
        assert health['request_trace_id'] == health['response_trace_id']
        assert set(health['server_phases_ms']) == {'health_db', 'health_model', 'health_app'}
        records = [json.loads(line) for line in (tmp_path/'api.log').read_text().splitlines() if line.startswith('{')]
        matched = [r for r in records if r.get('trace_id') == health['request_trace_id']]
        assert len(matched) == 1 and matched[0]['outcome'] == 'ok'
        assert health['server_phases_ms']['health_db'] == matched[0]['phases_ms']['database']
        assert monitor().summarize([dict(row, duration_ms=6000)], budget_ms=5000)['bad'] == 1
        (tmp_path/'probe.json').write_text(json.dumps(row, indent=2))
