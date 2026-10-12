"""Focused evidence-harness tests; backend concurrency safety already has tests."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError


def harness():
    path=Path(__file__).resolve().parents[2]/'scripts/benchmark_consistency_costs.py'
    spec=importlib.util.spec_from_file_location('consistency_costs',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_supported_profiles_grow_real_sql_state_and_leave_action_headroom(tmp_path):
    m=harness()
    store=m.MeasuredStore(m.Settings(database_url=f'sqlite:///{tmp_path}/size.db'))
    lab=m.AuditedEvidenceStore(store)
    sizes=[]
    try:
        for profile,(receipts,reports,actions) in m.PROFILES.items():
            f=m.fixture(lab,profile)
            state=f['initial']['state']
            assert len(state['receipts'])==receipts
            assert len(state['reports'])==reports
            assert len(state['actions'])==actions
            assert actions+32<=40
            sizes.append(f['initial']['stored_json_bytes'])
            m.clean(lab,f['sid'])
        assert sizes==sorted(set(sizes))
    finally:
        store.engine.dispose()


def test_sql_reconciliation_includes_commit_followed_by_lost_response(tmp_path,monkeypatch):
    m=harness()
    store=m.MeasuredStore(m.Settings(database_url=f'sqlite:///{tmp_path}/lost.db'))
    lab=m.AuditedEvidenceStore(store)
    f=m.fixture(lab,'small')
    original=lab.execute
    def lose_response(*args):
        original(*args)
        raise OperationalError('response lost',None,Exception('synthetic lost acknowledgment'))
    monkeypatch.setattr(lab,'execute',lose_response)
    item=dict(operation='execute',sid=f['sid'],rid=f['rid'],key='uncertain')
    row=m.request(lab,item)
    result=m.reconcile([f],[row],{f['sid']:m.sql_state(store,f['sid'])})
    assert row['observed']=='operational_error'
    assert result['passed']
    assert result['new_actions']==1
    assert result['persisted_after_error']==['uncertain']
    assert len(result['unacknowledged_actions'])==1
    assert not result['operational_errors_without_action']
    m.clean(lab,f['sid'])
    store.engine.dispose()


def test_uncertain_action_cannot_hide_stale_or_duplicate_sql_record(tmp_path,monkeypatch):
    from copy import deepcopy
    m=harness()
    store=m.MeasuredStore(m.Settings(database_url=f'sqlite:///{tmp_path}/bad.db'))
    lab=m.AuditedEvidenceStore(store)
    f=m.fixture(lab,'small')
    row=m.request(lab,dict(operation='execute',sid=f['sid'],rid=f['rid'],key='bad'))
    final=m.sql_state(store,f['sid'])
    duplicate=deepcopy(final['state']['actions'][0])
    duplicate['action_id']='unacknowledged-duplicate'
    final['state']['actions'].append(duplicate)
    row['observed']='operational_error'
    row['action_id']=None
    row['action_audit'][0]['validity']['valid']=False
    result=m.reconcile([f],[row],{f['sid']:final})
    assert result['duplicate_actions']==1
    assert len(result['stale_actions'])==1
    assert result['missing_action_audit']==['unacknowledged-duplicate']
    assert not result['passed']
    m.clean(lab,f['sid'])
    store.engine.dispose()


def test_refusals_and_errors_remain_in_cost_denominator():
    m=harness()
    rows=[dict(operation='execute',observed=outcome,elapsed_ms=elapsed,row_acquisition_ms=[elapsed],error=error)
        for outcome,elapsed,error in [('committed',1,None),('rejected',10,dict(reason='source_changed')),
            ('operational_error',100,dict(reason='database_unavailable',sqlstate='55P03'))]]
    summary=m.summarize(rows,1,SimpleNamespace(samples=[],error=None))
    assert summary['execute_requests']==3
    assert summary['execute_p95_ms']==100
    assert summary['execute_per_second']==3
    assert summary['useful_new_actions_per_second']==1
    assert summary['lock_timeouts']==1


def test_failed_report_preserves_published_result(tmp_path):
    m=harness()
    target=tmp_path/'report.json'
    target.write_text('prior good evidence')
    with pytest.raises(SystemExit):
        m.save_report(dict(runs=[dict(parameters={},reconciliation=dict(passed=False))]),target)
    assert target.read_text()=='prior good evidence'
    assert target.with_suffix('.failed.json').exists()


def test_matrix_scheduling_and_final_sql_cover_both_session_shapes(tmp_path,monkeypatch):
    from contextlib import nullcontext
    m=harness()
    monkeypatch.setattr(m,'LockSampler',lambda *args:nullcontext(SimpleNamespace(samples=[],error=None)))
    store=m.MeasuredStore(m.Settings(database_url=f'sqlite:///{tmp_path}/matrix.db'))
    lab=m.AuditedEvidenceStore(store)
    try:
        for sharing,session_count,edit_count in [('shared',1,2),('distinct',2,4)]:
            row=m.run_cell(lab,sharing=sharing,workers=2,edit_every=2,profile='small')
            assert len(row['initial_states'])==session_count
            assert row['summary']['execute_requests']==8
            assert row['summary']['edit_requests']==edit_count
            assert row['summary']['outcomes']['rejected']>=4
            assert row['summary']['refusal_reasons']['source_changed']>=4
            assert row['reconciliation']['passed']
            assert row['reconciliation']['new_actions']>=2
    finally:
        store.engine.dispose()


def test_audit_does_not_share_production_validity_oracle(tmp_path,monkeypatch):
    m=harness()
    store=m.MeasuredStore(m.Settings(database_url=f'sqlite:///{tmp_path}/oracle.db'))
    lab=m.AuditedEvidenceStore(store)
    f=m.fixture(lab,'small')
    lab.event(f['sid'],m.SourceEvent(source_id='transfer',revision=2,text='하루 이체 한도는 변경되었습니다.'))
    monkeypatch.setattr(lab,'validity',lambda *args:dict(valid=True,reason='current'))
    row=m.request(lab,dict(operation='execute',sid=f['sid'],rid=f['rid'],key='bad-oracle'))
    result=m.reconcile([f],[row],{f['sid']:m.sql_state(store,f['sid'])})
    assert row['observed']=='committed'
    assert row['action_audit'][0]['validity']['problems']==['source_not_current']
    assert len(result['stale_actions'])==1
    assert not result['passed']
    m.clean(lab,f['sid'])
    store.engine.dispose()
