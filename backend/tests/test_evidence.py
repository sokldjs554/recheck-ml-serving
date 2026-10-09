"""Real API + database + retrieval tests, including adverse event ordering."""
import asyncio
import importlib.util
import time

import httpx
import pytest
from test_recheck import setup, closing_clients


async def lab(tmp_path):
    app, worker, model, client, sid = await setup(tmp_path)
    response = await client.get(f'/api/sessions/{sid}/evidence')
    assert response.status_code == 200, 'persistent evidence API is not implemented'
    return app, model, client, sid, f'/api/sessions/{sid}/evidence'


def event(revision=2, text='하루 이체 한도는 100만 원입니다. 송금 본인 인증이 필요합니다.', deleted=False):
    return dict(source_id='transfer', revision=revision, text=text, deleted=deleted)


def prepare(key='one', product='answer'):
    return dict(query='하루 이체 한도', product=product, idempotency_key=key)


async def test_real_content_edit_refuses_old_receipt_and_paired_rebuild_restores(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        assert '300만 원' in receipt['output']
        assert (await client.post(base+f"/receipts/{receipt['id']}/use", json={})).json()['valid']
        assert (await client.post(base+'/events', json=event())).status_code == 200
        denied = (await client.post(base+f"/receipts/{receipt['id']}/use", json={})).json()
        assert not denied['valid'] and denied['reason'] == 'source_changed'
        assert denied['affected_sources'] == ['transfer']
        assert (await client.post(base+'/prepare', json=prepare('dirty'))).status_code == 409
        report = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        assert report['passed'] and 'artifact' not in report
        active = await client.post(base+f"/releases/{report['id']}/promote", json={})
        assert active.status_code == 200 and active.json()['release_epoch'] == 2
        fresh = (await client.post(base+'/prepare', json=prepare('fresh'))).json()
        assert '100만 원' in fresh['output'] and '300만 원' not in fresh['output']
        assert (await client.post(base+f"/receipts/{fresh['id']}/use", json={})).json()['valid']


async def test_delete_replay_and_out_of_order_events_cannot_resurrect_source(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        receipt = (await client.post(base+'/prepare', json=prepare())).json()
        deleted = event(3, '', True)
        assert (await client.post(base+'/events', json=deleted)).json()['applied']
        assert not (await client.post(base+'/events', json=deleted)).json()['applied']
        assert (await client.post(base+'/events', json=event(2))).status_code == 409
        assert (await client.post(base+'/events', json=event(3))).status_code == 409
        state = (await client.get(base)).json()
        assert next(s for s in state['sources'] if s['source_id']=='transfer')['deleted']
        use = (await client.post(base+f"/receipts/{receipt['id']}/use", json={})).json()
        assert not use['valid'] and use['reason']=='source_deleted'


@pytest.mark.parametrize('candidate', ['mismatch','regressed'])
async def test_failed_candidate_never_changes_active_release(tmp_path, candidate):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        before = (await client.get(base)).json()['active_release']
        report = (await client.post(base+'/releases/evaluate', json={'candidate':candidate})).json()
        assert not report['passed']
        assert (await client.post(base+f"/releases/{report['id']}/promote", json={})).status_code == 409
        assert (await client.get(base)).json()['active_release'] == before


async def test_stale_report_and_competing_promotion_fail_closed(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        report = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        await client.post(base+'/events', json=event())
        assert (await client.post(base+f"/releases/{report['id']}/promote", json={})).status_code == 409
        r1 = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        r2 = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        assert (await client.post(base+f"/releases/{r1['id']}/promote", json={})).status_code == 200
        assert (await client.post(base+f"/releases/{r2['id']}/promote", json={})).status_code == 409


async def test_cross_session_reports_receipts_and_idempotency(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        first = (await client.post(base+'/prepare', json=prepare())).json()
        duplicate = (await client.post(base+'/prepare', json=prepare())).json()
        assert first == duplicate
        assert (await client.post(base+'/prepare', json=prepare(product='checklist'))).status_code == 409
        other = (await client.post('/api/sessions')).json()['session_id']
        other_base = f'/api/sessions/{other}/evidence'
        assert (await client.post(other_base+f"/receipts/{first['id']}/use", json={})).status_code == 404
        report = (await client.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        assert (await client.post(other_base+f"/releases/{report['id']}/promote", json={})).status_code == 404


async def test_state_persists_in_second_app_and_old_release_receipt_is_rejected(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    from recheck.api import create_app
    second = create_app(app.state.store.settings, model_client=model)
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url='http://second')
    async with closing_clients(model, client, other):
        first = (await client.post(base+'/prepare', json=prepare())).json()
        assert (await other.post(base+f"/receipts/{first['id']}/use", json={})).json()['valid']
        report = (await other.post(base+'/releases/evaluate', json={'candidate':'paired'})).json()
        await other.post(base+f"/releases/{report['id']}/promote", json={})
        assert (await client.post(base+f"/receipts/{first['id']}/use", json={})).json()['reason']=='release_changed'


async def test_validation_expiry_and_unrelated_event_selectivity(tmp_path, monkeypatch):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        first = (await client.post(base+'/prepare', json=prepare())).json()
        await client.post(base+'/events', json=dict(event(), source_id='card'))
        assert (await client.post(base+f"/receipts/{first['id']}/use", json={})).json()['valid']
        from recheck import evidence
        monkeypatch.setattr(evidence, 'now', lambda: time.time()+121)
        assert (await client.post(base+f"/receipts/{first['id']}/use", json={})).json()['reason']=='receipt_expired'


async def test_inflight_retrieval_is_fenced_after_actual_content_change(tmp_path, monkeypatch):
    app, model, client, sid, base = await lab(tmp_path)
    from recheck import evidence
    import threading
    started, proceed = threading.Event(), threading.Event()
    original = evidence.retrieve
    def held(*args, **kwargs):
        started.set()
        assert proceed.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(evidence, 'retrieve', held)
    async with closing_clients(model, client):
        pending = asyncio.create_task(client.post(base+'/prepare', json=prepare()))
        assert await asyncio.to_thread(started.wait, 3)
        try:
            await client.post(base+'/events', json=event())
        finally:
            proceed.set()
        assert (await pending).status_code == 409


async def test_sdk_two_consumers_share_real_lifecycle_and_refuse_changed_sources(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    assert importlib.util.find_spec('recheck.sdk'), 'HTTP SDK missing'
    from recheck.sdk import EvidenceClient
    async with closing_clients(model, client):
        sdk = EvidenceClient(client, sid)
        answer = await sdk.prepare('하루 이체 한도', product='answer')
        checklist = await sdk.prepare('하루 이체 한도', product='checklist')
        assert answer['output'] != checklist['output']
        assert answer['references']==checklist['references']
        assert (await sdk.validate(answer['id']))['valid']
        await client.post(base+'/events', json=event())
        assert not (await sdk.validate(checklist['id']))['valid']


async def test_invalid_inputs_empty_query_and_retention_limits(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        assert (await client.post(base+'/prepare', json=dict(prepare(),query=' '))).status_code == 422
        assert (await client.post(base+'/events', json=dict(event(),text='x'*601))).status_code == 422
        assert (await client.post(base+'/events', json=dict(event(),source_id='unknown'))).status_code == 422
        for i in range(40):
            assert (await client.post(base+'/prepare', json=prepare(str(i)))).status_code == 200
        assert (await client.post(base+'/prepare', json=prepare('full'))).status_code == 429


def test_schema_initializer_includes_evidence_table_in_fresh_process(tmp_path):
    import subprocess
    import sys
    import os
    result = subprocess.run([sys.executable, '-c',
        "from recheck.store import Store; from recheck.config import Settings; from sqlalchemy import inspect; "
        "s=Store(Settings(database_url='sqlite:///:memory:')); print(inspect(s.engine).get_table_names())"],
        capture_output=True,text=True,env=dict(os.environ,PYTHONPATH=str(__import__('pathlib').Path(__file__).parents[1])))
    assert result.returncode == 0, result.stderr
    assert 'evidence_states' in result.stdout, 'schema-init must create new tables before replicated APIs start'


async def test_empty_active_document_is_rejected_but_empty_tombstone_is_allowed(tmp_path):
    app, model, client, sid, base = await lab(tmp_path)
    async with closing_clients(model, client):
        blank = dict(event(),source_id='refund',text='   ')
        assert (await client.post(base+'/events',json=blank)).status_code == 422
        state = (await client.get(base)).json()
        refund = next(s for s in state['sources'] if s['source_id']=='refund')
        assert refund['revision']==1 and refund['text'].strip()
        assert (await client.post(base+'/events',json=dict(blank,deleted=True))).status_code == 200
