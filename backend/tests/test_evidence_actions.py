"""Synthetic actions must validate and persist under the document writer's SQL lock."""
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import event as sql_event

from test_evidence import lab, prepare, event
from test_recheck import closing_clients


async def execute(client, base, rid, key='task'):
    return await client.post(f'{base}/receipts/{rid}/execute', json={'idempotency_key': key})


async def test_records_current_task_with_original_evidence_and_lists_history(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        response = await execute(client, base, receipt['id'])
        assert response.status_code == 200, 'atomic synthetic task endpoint missing'
        action = response.json()
        assert set(action) == {'action_id', 'receipt_id', 'output', 'committed_at',
                               'release_epoch', 'references', 'scope', 'replayed'}
        assert action['receipt_id'] == receipt['id']
        assert action['output'] == receipt['output']
        assert action['references'] == receipt['references']
        assert action['release_epoch'] == receipt['release_epoch']
        assert receipt['created_at'] <= action['committed_at'] < receipt['expires_at']
        assert action['replayed'] is False
        assert 'local' in action['scope'] and 'external' in action['scope']
        assert (await client.get(base+'/actions')).json() == {'actions': [action]}


@pytest.mark.parametrize('change,reason', [('edit', 'source_changed'), ('delete', 'source_deleted'),
    ('expiry', 'receipt_expired'), ('release', 'release_changed'), ('aba', 'source_changed')])
async def test_rejects_invalid_evidence_without_recording(tmp_path, monkeypatch, change, reason):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        if change in ('edit', 'delete', 'aba'):
            await client.post(base+'/events', json=event(deleted=change=='delete'))
            if change == 'aba':
                await client.post(base+'/events', json=event(3, receipt['references'][0]['text']))
        elif change == 'expiry':
            from recheck import evidence
            monkeypatch.setattr(evidence, 'now', lambda: receipt['expires_at'])
        else:
            report = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
            await client.post(base+f"/releases/{report['id']}/promote", json={})
        response = await execute(client, base, receipt['id'])
        assert response.status_code == 409
        assert response.json()['detail'] == reason
        assert (await client.get(base+'/actions')).json() == {'actions': []}


async def test_unrelated_edit_does_not_block_task(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        await client.post(base+'/events', json=dict(event(), source_id='card'))
        assert (await execute(client, base, receipt['id'])).status_code == 200


async def test_replay_preserves_historical_action_after_edit_expiry_and_release(tmp_path, monkeypatch):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        original = (await execute(client, base, receipt['id'])).json()
        assert 'action_id' in original
        await client.post(base+'/events', json=event())
        report = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        await client.post(base+f"/releases/{report['id']}/promote", json={})
        from recheck import evidence
        monkeypatch.setattr(evidence, 'now', lambda: receipt['expires_at']+1)
        replay = await execute(client, base, receipt['id'])
        assert replay.status_code == 200
        assert replay.json() == dict(original, replayed=True)
        assert (await client.get(base+'/actions')).json() == {'actions': [original]}


async def test_key_conflict_session_isolation_and_missing_receipt(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        first = (await client.post(base+'/prepare', json=prepare())).json()
        second = (await client.post(base+'/prepare', json=prepare('second'))).json()
        assert (await execute(client, base, first['id'])).status_code == 200
        conflict = await execute(client, base, second['id'])
        assert conflict.status_code == 409
        assert conflict.json()['detail'] == 'action_idempotency_conflict'
        other = (await client.post('/api/sessions')).json()['session_id']
        other_base = f'/api/sessions/{other}/evidence'
        assert (await execute(client, other_base, first['id'])).status_code == 404
        assert (await client.get(other_base+'/actions')).json() == {'actions': []}
        own = (await client.post(other_base+'/prepare', json=prepare())).json()
        assert (await execute(client, other_base, own['id'])).status_code == 200


async def test_action_capacity_does_not_evict_retry_record(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        for i in range(40):
            response = await execute(client, base, receipt['id'], str(i))
            assert response.status_code == 200
        excess = await execute(client, base, receipt['id'], 'full')
        assert excess.status_code == 429
        assert excess.json()['detail'] == 'evidence_action_capacity'
        assert (await execute(client, base, receipt['id'], '0')).json()['replayed']
        assert len((await client.get(base+'/actions')).json()['actions']) == 40


@pytest.mark.parametrize('body', [{}, {'idempotency_key':''}, {'idempotency_key':'   '},
    {'idempotency_key':'x'*129}, {'idempotency_key':'key', 'unsafe':True}])
async def test_invalid_action_body_rejected(tmp_path, body):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        response = await client.post(base+'/receipts/missing/execute', json=body)
        assert response.status_code == 422


@pytest.mark.parametrize('first_operation', ['edit', 'execute'])
async def test_actual_sql_lock_serializes_edit_and_execute(tmp_path, monkeypatch, first_operation):
    from recheck.evidence import EvidenceStore
    from recheck import evidence_routes
    assert hasattr(evidence_routes, 'Execute'), 'execute request model missing'
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        holder = EvidenceStore(app.state.store)
        contender = EvidenceStore(app.state.store)
        locked, release, attempting_sql = threading.Event(), threading.Event(), threading.Event()
        original_locked = holder.locked

        @contextmanager
        def hold_sql_lock(session_id):
            with original_locked(session_id) as state:
                locked.set()
                assert release.wait(3)
                yield state

        monkeypatch.setattr(holder, 'locked', hold_sql_lock)
        contender_thread = []

        def observe_sql(conn, cursor, statement, parameters, context, executemany):
            if contender_thread and threading.get_ident() == contender_thread[0]:
                if statement == 'BEGIN IMMEDIATE' or 'FOR UPDATE' in statement:
                    attempting_sql.set()

        sql_event.listen(app.state.store.engine, 'before_cursor_execute', observe_sql)

        def run(store, operation, competing=False):
            if competing:
                contender_thread.append(threading.get_ident())
            try:
                if operation == 'edit':
                    return store.event(sid, evidence_routes.SourceEvent(**event()))
                return store.execute(sid, receipt['id'], evidence_routes.Execute(idempotency_key='concurrent'))
            except HTTPException as exc:
                return exc

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(run, holder, first_operation)
                assert locked.wait(3)
                second = pool.submit(run, contender, 'execute' if first_operation=='edit' else 'edit', True)
                try:
                    assert attempting_sql.wait(3)
                    # Real database contention: the other connection cannot complete
                    # while the holder owns BEGIN IMMEDIATE / SELECT FOR UPDATE.
                    with pytest.raises(TimeoutError):
                        second.result(timeout=0.02)
                finally:
                    release.set()
                first_result, second_result = first.result(3), second.result(3)
        finally:
            release.set()
            sql_event.remove(app.state.store.engine, 'before_cursor_execute', observe_sql)
        history = (await client.get(base+'/actions')).json()['actions']
        if first_operation == 'edit':
            assert first_result['applied']
            assert isinstance(second_result, HTTPException)
            assert (second_result.status_code, second_result.detail) == (409, 'source_changed')
            assert history == []
        else:
            assert first_result['receipt_id'] == receipt['id']
            assert second_result['applied']
            assert history == [first_result]


async def test_simultaneous_same_key_requests_record_once(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        responses = await asyncio.gather(*(execute(client, base, receipt['id']) for _ in range(6)))
        assert all(response.status_code == 200 for response in responses)
        actions = [response.json() for response in responses]
        assert len({action['action_id'] for action in actions}) == 1
        assert sum(not action['replayed'] for action in actions) == 1
        assert len((await client.get(base+'/actions')).json()['actions']) == 1


async def test_actual_db_lock_timeout_returns_503_then_same_key_recovers(tmp_path):
    from recheck.evidence import EvidenceStore
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        holder = EvidenceStore(app.state.store)
        acquired, release = threading.Event(), threading.Event()
        def hold():
            with holder.locked(sid):
                acquired.set()
                assert release.wait(5)
        with ThreadPoolExecutor(max_workers=1) as pool:
            held = pool.submit(hold)
            try:
                assert await asyncio.to_thread(acquired.wait, 2)
                busy = await execute(client, base, receipt['id'], 'recoverable')
                assert busy.status_code == 503
                assert busy.json() == {'detail': 'database_unavailable'}
            finally:
                release.set()
                held.result(2)
        recovered = await execute(client, base, receipt['id'], 'recoverable')
        assert recovered.status_code == 200 and not recovered.json()['replayed']
        replay = await execute(client, base, receipt['id'], 'recoverable')
        assert replay.json()['action_id'] == recovered.json()['action_id']
        assert replay.json()['replayed']
        assert len((await client.get(base+'/actions')).json()['actions']) == 1
