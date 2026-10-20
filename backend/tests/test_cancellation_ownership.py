"""Cancellation must not free admission while a real SQL thread owns work."""
import asyncio
import threading

import pytest
from sqlalchemy import event, select
from recheck.store import Decision
from test_recheck import setup, closing_clients, body


async def test_repeated_cancel_during_commit_keeps_slot_until_sql_finishes(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path, gateway_concurrency=1, gateway_queue=0, deadline_ms=2000)
    entered, release = threading.Event(), threading.Event()
    def hold(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE decisions'):
            entered.set()
            assert release.wait(5)
    event.listen(app.state.store.engine, 'before_cursor_execute', hold)
    async with closing_clients(model, client):
        task = asyncio.create_task(client.post(f'/api/sessions/{sid}/decisions', json=body()))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(.01)  # let the owner enter its cancellation handler
            task.cancel()
            await asyncio.sleep(.01)
            assert app.state.admission.active == 1, 'SQL still running but admission was released'
            rejected = await client.post(f'/api/sessions/{sid}/decisions', json=body('second'))
            assert rejected.status_code == 429
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            # Independent SQL connection confirms the actual persisted result.
            def stored():
                with app.state.store.transaction() as db:
                    return db.scalars(select(Decision).where(Decision.session_id == sid)).all()
            rows = await asyncio.to_thread(stored)
            event.remove(app.state.store.engine, 'before_cursor_execute', hold)
        assert app.state.admission.admitted == 0
        assert len(rows) == 1 and rows[0].payload is not None
        retry = await client.post(f'/api/sessions/{sid}/decisions', json=body())
        assert retry.status_code == 200 and retry.json()['id'] == rows[0].id
        assert worker.state.completed == 1


@pytest.mark.parametrize('fail', [False, True])
async def test_repeated_cancel_joins_thread_and_preserves_cancellation_on_late_failure(fail, caplog):
    from recheck.api import database_call
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    def transaction():
        entered.set()
        assert release.wait(3)
        finished.set()
        if fail:
            raise RuntimeError('private SQL or credentials')
        return 'done'
    task = asyncio.create_task(database_call(transaction))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(.005)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert finished.is_set()
    assert 'private SQL' not in caplog.text
    if fail:
        assert 'owned_work_failed_after_cancel' in caplog.text
        assert 'RuntimeError' in caplog.text


async def test_repeated_cancel_release_evaluation_keeps_bounded_capacity(tmp_path, monkeypatch):
    from recheck.evidence import EvidenceStore
    from test_evidence import lab
    entered, release = threading.Event(), threading.Event()
    calls = []
    def held_evaluation(self, sid, candidate):
        calls.append(candidate)
        entered.set()
        assert release.wait(5)
        return {'finished': True}
    monkeypatch.setattr(EvidenceStore, 'evaluate', held_evaluation)
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        tasks = [asyncio.create_task(client.post(base+'/releases/evaluate', json={'candidate':'paired'}))]
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            for _ in range(3):
                tasks[0].cancel()
                await asyncio.sleep(.005)
            assert not tasks[0].done()
            # Fill the second active slot and four waiting positions.
            tasks.extend(asyncio.create_task(client.post(base+'/releases/evaluate', json={'candidate':'paired'})) for _ in range(5))
            await asyncio.sleep(.03)
            response = await client.post(base+'/releases/evaluate', json={'candidate':'paired'})
            assert response.status_code == 429
            assert len(calls) == 2
        finally:
            release.set()
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(outcomes[0], asyncio.CancelledError)
        assert all(r.status_code == 200 for r in outcomes[1:])
        assert (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).status_code == 200
