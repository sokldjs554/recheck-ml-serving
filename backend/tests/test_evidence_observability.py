"""Observe the real SQL result independently of HTTP delivery."""
import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event as sql_event
from sqlalchemy.exc import OperationalError
from test_evidence import lab, prepare, event
from test_evidence_actions import execute
from test_recheck import closing_clients


def records(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == 'recheck.evidence' and json.loads(r.message)['event'] == 'evidence_execution_finished']


async def test_execute_outcomes_trace_and_bounded_labels(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        incoming_trace = '1234567890abcdef1234567890abcdef'
        first = await client.post(base+f"/receipts/{receipt['id']}/execute", json={'idempotency_key':'private-key'},
            headers={'traceparent':f'00-{incoming_trace}-1234567890abcdef-01'})
        assert first.headers['x-recheck-trace-id'] == incoming_trace
        replay = await execute(client, base, receipt['id'], 'private-key')
        await client.post(base+'/events', json=event())
        blocked = await execute(client, base, receipt['id'], 'blocked-key')
        assert blocked.status_code == 409
        metrics = (await client.get('/metrics')).text
        for outcome in ['recorded', 'replayed', 'blocked']:
            assert f'outcome="{outcome}"' in metrics
        for value in [sid, receipt['id'], first.json()['action_id'], 'private-key', 'blocked-key']:
            assert value not in metrics
        for response in [first, replay, blocked]:
            trace_id = response.headers['x-recheck-trace-id']
            assert len(trace_id) == 32
            spans = app.state.display.traces[trace_id]
            assert 'evidence.execute' in {s['name'] for s in spans}
        saved = [r for r in records(caplog) if r['event'] == 'evidence_execution_finished']
        assert [r['outcome'] for r in saved] == ['recorded', 'replayed', 'blocked']
        assert saved[0]['action_id'] == saved[1]['action_id'] == first.json()['action_id']
        assert saved[0]['session_id'] == sid and saved[0]['request_key'] == 'private-key'
        assert saved[-1]['reason'] == 'source_changed' and saved[-1]['storage'] == 'not_written'
        assert {'lock_acquire', 'flush_commit'} <= saved[0]['phases_ms'].keys()


async def test_lock_timeout_and_flush_failure_are_distinct_and_retryable(tmp_path, caplog):
    from recheck.evidence import EvidenceStore
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        rid = (await client.post(base+'/prepare', json=prepare())).json()['id']
        acquired, release = threading.Event(), threading.Event()
        def hold():
            with EvidenceStore(app.state.store).locked(sid):
                acquired.set()
                assert release.wait(5)
        with ThreadPoolExecutor(max_workers=1) as pool:
            holder = pool.submit(hold)
            try:
                assert await asyncio.to_thread(acquired.wait, 2)
                assert (await execute(client, base, rid)).status_code == 503
            finally:
                release.set(); holder.result(2)
        assert records(caplog)[-1]['outcome'] == 'lock_timeout'
        assert records(caplog)[-1]['storage'] == 'not_written'
        def fail_write(conn, cursor, statement, parameters, context, many):
            if statement.startswith('UPDATE evidence_states'):
                raise OperationalError('injected update failure', {}, Exception('db failed'))
        sql_event.listen(app.state.store.engine, 'before_cursor_execute', fail_write)
        try:
            assert (await execute(client, base, rid)).status_code == 503
        finally:
            sql_event.remove(app.state.store.engine, 'before_cursor_execute', fail_write)
        failed = records(caplog)[-1]
        assert failed['outcome'] == 'db_error' and failed['storage'] == 'unknown'
        assert 'flush_commit' in failed['phases_ms']
        assert (await client.get(base+'/actions')).json()['actions'] == []
        saved = (await execute(client, base, rid)).json()
        assert (await execute(client, base, rid)).json()['action_id'] == saved['action_id']


async def test_cancelled_http_still_logs_final_commit_and_same_key_recovery(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        rid = (await client.post(base+'/prepare', json=prepare())).json()['id']
        entered, release = threading.Event(), threading.Event()
        def hold_write(conn, cursor, statement, parameters, context, many):
            if statement.startswith('UPDATE evidence_states'):
                entered.set()
                assert release.wait(5)
        sql_event.listen(app.state.store.engine, 'before_cursor_execute', hold_write)
        task = asyncio.create_task(execute(client, base, rid, 'cancelled-key'))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        for _ in range(200):
            if any(r.get('outcome') == 'recorded' for r in records(caplog)):
                break
            await asyncio.sleep(.01)
        sql_event.remove(app.state.store.engine, 'before_cursor_execute', hold_write)
        saved = next(r for r in records(caplog) if r.get('outcome') == 'recorded')
        assert saved['storage'] == 'committed'
        retry = (await execute(client, base, rid, 'cancelled-key')).json()
        assert retry['replayed'] and retry['action_id'] == saved['action_id']
        assert len((await client.get(base+'/actions')).json()['actions']) == 1
        assert 'outcome="cancelled"' in (await client.get('/metrics')).text


async def test_response_budget_overrun_preserves_committed_outcome(tmp_path, caplog, monkeypatch):
    from types import SimpleNamespace
    from recheck import evidence_observation as observation
    import time
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        rid = (await client.post(base+'/prepare', json=prepare())).json()['id']
        shift = [0.0]
        monkeypatch.setattr(observation, 'time', SimpleNamespace(monotonic=lambda: time.monotonic()+shift[0]))
        def advance_budget(conn, cursor, statement, parameters, context, many):
            if statement.startswith('UPDATE evidence_states'):
                shift[0] = 16.0
        sql_event.listen(app.state.store.engine, 'before_cursor_execute', advance_budget)
        try:
            response = await execute(client, base, rid, 'late-key')
        finally:
            sql_event.remove(app.state.store.engine, 'before_cursor_execute', advance_budget)
        result = records(caplog)[-1]
        assert response.status_code == 200  # Observation does not change the transaction contract.
        assert result['response_budget'] == 'exceeded' and result['storage'] == 'committed'
        assert result['action_id'] == response.json()['action_id']
        assert (await execute(client, base, rid, 'late-key')).json()['replayed']
        assert len((await client.get(base+'/actions')).json()['actions']) == 1


async def test_real_socket_disconnect_preserves_commit_and_records_transport_separately(tmp_path, caplog):
    import os
    import socket
    import httpx
    import uvicorn
    if os.getenv('RECHECK_NETWORK_TESTS') != '1':
        pytest.skip('set RECHECK_NETWORK_TESTS=1 for loopback socket verification')
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, internal, sid, base = await lab(tmp_path)
    async with closing_clients(model, internal):
        rid = (await internal.post(base+'/prepare', json=prepare())).json()['id']
        entered, release = threading.Event(), threading.Event()
        def hold_write(conn, cursor, statement, parameters, context, many):
            if statement.startswith('UPDATE evidence_states'):
                entered.set()
                assert release.wait(5)
        sql_event.listen(app.state.store.engine, 'before_cursor_execute', hold_write)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off', loop='asyncio'))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(300):
                if server.started: break
                await asyncio.sleep(.01)
            assert server.started
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', trust_env=False) as client:
                task = asyncio.create_task(execute(client, base, rid, 'socket-key'))
                assert await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError): await task
                # Give Uvicorn an event-loop turn to receive connection_lost;
                # SQL is still blocked at a known boundary in the other thread.
                await asyncio.sleep(.05)
                release.set()
                for _ in range(300):
                    if any('"outcome": "disconnected"' in r.message for r in caplog.records): break
                    await asyncio.sleep(.01)
                transport = [json.loads(r.message) for r in caplog.records if r.name == 'recheck.evidence' and '"event": "evidence_http_finished"' in r.message]
                assert any(r['outcome'] == 'disconnected' for r in transport)
                saved = next(r for r in records(caplog) if r['outcome'] == 'recorded')
                assert saved['storage'] == 'committed'
                assert any(r['trace_id'] == saved['trace_id'] and r['outcome'] == 'disconnected' for r in transport)
                replay = (await execute(client, base, rid, 'socket-key')).json()
                assert replay['replayed'] and replay['action_id'] == saved['action_id']
                assert len((await client.get(base+'/actions')).json()['actions']) == 1
        finally:
            release.set()
            sql_event.remove(app.state.store.engine, 'before_cursor_execute', hold_write)
            server.should_exit = True
            await asyncio.to_thread(thread.join, 5)
            sock.close()


async def test_budget_includes_dispatch_wait_not_only_worker_time(tmp_path, monkeypatch, caplog):
    from types import SimpleNamespace
    from recheck import observability
    import time
    caplog.set_level(logging.INFO, logger='recheck.evidence')
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        rid = (await client.post(base+'/prepare', json=prepare())).json()['id']
        # Model an arrival 16s before worker dispatch, without sleeping or
        # presenting a synthetic clock test as measured service performance.
        monkeypatch.setattr(observability, 'time', SimpleNamespace(monotonic=lambda: time.monotonic()-16))
        response = await execute(client, base, rid)
        assert response.status_code == 200
        result = records(caplog)[-1]
        assert result['response_budget'] == 'exceeded'
        assert result['dispatch_ms'] >= 16000
        assert result['duration_ms'] - result['worker_ms'] >= 15000


async def test_durable_journal_includes_bounded_evidence_outcomes(tmp_path):
    from recheck.operations import counters
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        rid = (await client.post(base+'/prepare', json=prepare())).json()['id']
        await execute(client, base, rid)
        rows = counters(app.state.prometheus.registry)
        assert any(r['name'] == 'recheck_evidence_executions_total' and r['labels']['outcome'] == 'recorded' for r in rows)
        assert any(r['name'] == 'recheck_evidence_http_total' for r in rows)
        assert sid not in json.dumps(rows)
