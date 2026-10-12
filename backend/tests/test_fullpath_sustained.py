"""Accounting regressions: late sends, refusal, uncertain commits and recovery."""
import importlib.util
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


def harness():
    path = SCRIPTS / 'benchmark_fullpath_sustained.py'
    assert path.exists(), 'sustained harness is missing'
    spec = importlib.util.spec_from_file_location('sustained', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(i, due, sent, done, status=200, reason='no_current_warning'):
    return dict(index=i, phase=0, due_seconds=due, sent_seconds=sent, completed_seconds=done,
                session_id='s', idempotency_key=str(i), http_status=status,
                response=dict(id=str(i), reason=reason), good=status == 200 and reason == 'no_current_warning' and done-due <= .5)


def test_accounting_distinguishes_cohort_from_wall_time_and_all_outcomes():
    # Replacing scheduled-time goodput with HTTP-200 throughput must fail this.
    m = harness()
    rows = [row(0, 0, .01, .1), row(1, 1, 1.6, 1.7), row(2, 2, 2, 2.1, 429, 'overloaded'),
            row(3, 3, 3, 3.1, 200, 'deadline_exceeded'), row(4, 4.9, 5.1, 5.2, 504, 'deadline_exceeded_after_commit')]
    rows.append(dict(index=5, phase=0, due_seconds=4.95, sent_seconds=4.95, completed_seconds=6,
                     session_id='s', idempotency_key='5', error='ReadTimeout', good=False))
    summary = m.summarize_phase(rows, dict(index=0, start_seconds=0, duration_seconds=5, target_rps=1.2))
    assert summary['attempted'] == 6
    assert summary['good'] == 1
    assert summary['cohort_rates_rps']['good'] == 1/6
    assert summary['wall_window_rates_rps'] == dict(sent=1, completed=.8, good=.2)
    assert summary['categories'] == dict(useful_on_time=1, useful_late=1, refused=1, deferred=1, server_timeout=1, client_timeout=1)
    assert summary['generator_lag_ms']['p99'] > 100


def test_reconciliation_retains_uncertain_commits_and_detects_missing_extra_and_mismatch():
    m = harness()
    rows = [row(0,0,0,.1), row(1,0,0,.6,504), row(2,0,0,.1), row(3,0,0,.1)]
    sql = [dict(session_id='s', idempotency_key='0', payload=rows[0]['response']),
           dict(session_id='s', idempotency_key='1', payload=dict(id='1',reason='no_current_warning')),
           dict(session_id='s', idempotency_key='3', payload=dict(id='wrong')),
           dict(session_id='s', idempotency_key='extra', payload={})]
    result = m.reconcile(rows, sql)
    assert result['delivered_equal_sql'] == 1
    assert result['missing_delivered_keys'] == [['s','2']]
    assert result['mismatched_delivered_keys'] == [['s','3']]
    assert result['committed_without_200_keys'] == [['s','1']]
    assert result['unexpected_sql_keys'] == [['s','extra']]
    assert result['passed'] is False


def test_recovery_requires_two_complete_good_windows_and_queue_drain():
    m = harness()
    rows = [row(i, i, i+.001, i+.1) for i in range(20)]
    samples = [dict(offset_seconds=i, worker=dict(active=1,admitted=1)) for i in range(20)]
    samples[1]['worker']['admitted'] = 6
    result = m.recovery(rows, samples, dict(start_seconds=0,duration_seconds=20,target_rps=1),150)
    assert result['stabilized_window_start_seconds'] == 5
    assert result['confirmed_after_seconds'] == 15
    assert m.recovery(rows[:8],samples,dict(start_seconds=0,duration_seconds=8,target_rps=1),150)['confirmed_after_seconds'] is None


def test_local_database_guard_rejects_reused_or_remote_database():
    m = harness()
    import pytest
    for url in ['postgresql+psycopg://u:p@example.com/fullpath_sustained_x',
                'postgresql+psycopg://u:p@127.0.0.1/recheck']:
        with pytest.raises(ValueError):
            m.validate_database_url(url)
    assert m.validate_database_url('postgresql+psycopg://u:p@127.0.0.1/fullpath_sustained_x').database == 'fullpath_sustained_x'


def test_probe_error_prevents_recovery_even_when_worker_reply_arrived():
    m = harness()
    rows = [row(i, i, i+.001, i+.1) for i in range(10)]
    samples = [dict(offset_seconds=i,worker=dict(active=0,admitted=0)) for i in range(10)]
    samples[2]['probe_error'] = 'ReadTimeout'
    assert m.recovery(rows,samples,dict(start_seconds=0,duration_seconds=10,target_rps=1),150)['confirmed_after_seconds'] is None


def test_reconciliation_rejects_duplicate_and_pending_sql_records():
    m = harness()
    request = row(0,0,0,.1,504)
    sql = dict(session_id='s',idempotency_key='0',payload=None)
    result = m.reconcile([request],[sql,sql])
    assert result['duplicate_sql_keys'] == [['s','0']]
    assert result['pending_sql_keys'] == [['s','0']]
    assert result['passed'] is False


async def test_cancelled_schedule_retains_completed_attempts_in_partial_report():
    import asyncio
    import httpx
    m = harness()
    partial = {}
    def respond(request):
        if request.url.path == '/health':
            return httpx.Response(200,json=dict(active=0,admitted=0))
        if request.url.path == '/metrics':
            return httpx.Response(200,text='recheck_http_inflight{service="api"} 0\n')
        return httpx.Response(200,json=dict(id='receipt',reason='no_current_warning'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        task = asyncio.create_task(m.run_schedule(client,client,'http://local','http://local',['s'],[],
            [dict(index=0,start_seconds=0,duration_seconds=10,target_rps=10)],300,.5,partial=partial))
        await asyncio.sleep(.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    assert len(partial['records']) >= 1
    assert partial['records'][0]['response']['id'] == 'receipt'
    assert partial['interrupted'] is True
