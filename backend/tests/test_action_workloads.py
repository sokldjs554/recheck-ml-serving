"""Workload evidence must distinguish new stale writes from historical replays."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException


def evaluator():
    path = Path(__file__).resolve().parents[2] / 'scripts/evaluate_action_workloads.py'
    assert path.exists(), 'matched action workload evaluator is missing'
    spec = importlib.util.spec_from_file_location('action_workloads', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contended_writes_and_historical_replays_are_counted_from_sql(tmp_path):
    module = evaluator()
    report = module.evaluate_database(f'sqlite:///{tmp_path}/workloads.db', rounds=2, workers=3, samples=3, warmups=1)
    by_strategy = {row['strategy']: row for row in report['strategies']}
    for row in by_strategy.values():
        assert row['latency']['requests'] == 3
        assert len(row['latency']['samples_ms']) == 3
        assert row['latency']['commits'] == 3
        assert row['latency']['p95_ms'] >= row['latency']['p50_ms'] > 0
        workloads = {w['name']: w for w in row['workloads']}
        assert workloads['same_key']['totals']['new_actions'] == 2
        assert workloads['same_key']['totals']['replays'] == 4
        assert workloads['unique_keys']['totals']['new_actions'] == 6
        assert all(w['totals']['duplicate_commits'] == 0 for w in workloads.values())
        assert all(w['totals']['operational_errors'] == 0 for w in workloads.values() if w['name'] != 'lock_timeout_retry')
        for workload in workloads.values():
            assert len(workload['runs']) == 2
            assert all(len(run['attempts']) == 3 for run in workload['runs'])
    guarded = {w['name']: w['totals'] for w in by_strategy['atomic_guard']['workloads']}
    assert guarded['edit_after_check']['stale_commits'] == 0
    assert guarded['edit_after_check']['rejections'] == 6
    assert guarded['replay_after_edit']['replays'] == 6
    assert guarded['replay_after_edit']['new_actions'] == 0
    for strategy in ('trust_at_creation', 'check_then_act'):
        workloads = {w['name']: w['totals'] for w in by_strategy[strategy]['workloads']}
        assert workloads['edit_after_check']['stale_commits'] == 2
    # A point-in-time check before dedup also prevents returning a historical
    # success after the source changes; do not silently count that as a replay.
    split = {w['name']: w['totals'] for w in by_strategy['check_then_act']['workloads']}
    assert split['replay_after_edit']['rejections'] == 6
    assert split['replay_after_edit']['missing_replays'] == 6
    module.assert_guarded_safe(report)


def test_removing_guard_is_detected_in_concurrent_workload(tmp_path, monkeypatch):
    module = evaluator()
    monkeypatch.setattr(module.EvidenceStore, 'execute', module.unsafe_record)
    report = module.evaluate_database(f'sqlite:///{tmp_path}/unsafe.db', rounds=1, workers=2, samples=1, warmups=0)
    with pytest.raises(AssertionError, match='stale_commits'):
        module.assert_guarded_safe(report)


def test_failed_requests_stay_in_latency_denominator(tmp_path, monkeypatch):
    module = evaluator()
    def reject(*args):
        raise HTTPException(409, 'mutant_reject_all')
    monkeypatch.setattr(module.EvidenceStore, 'execute', reject)
    report = module.evaluate_database(f'sqlite:///{tmp_path}/reject.db', rounds=1, workers=2, samples=3, warmups=0)
    guarded = next(row for row in report['strategies'] if row['strategy'] == 'atomic_guard')
    assert guarded['latency']['requests'] == 3
    assert guarded['latency']['commits'] == 0
    assert guarded['latency']['rejections'] == 3
    assert len(guarded['latency']['samples_ms']) == 3
    with pytest.raises(AssertionError, match='normal requests'):
        module.assert_guarded_safe(report)


def test_removed_deduplication_is_detected_from_persisted_ids(tmp_path, monkeypatch):
    import uuid
    module = evaluator()
    original = module.EvidenceStore.execute
    def new_key(lab, sid, rid, body):
        if body.idempotency_key == 'new':
            return original(lab, sid, rid, body)
        return original(lab, sid, rid, module.Execute(idempotency_key=str(uuid.uuid4())))
    monkeypatch.setattr(module.EvidenceStore, 'execute', new_key)
    report = module.evaluate_database(f'sqlite:///{tmp_path}/duplicates.db', rounds=1, workers=3, samples=1, warmups=0)
    with pytest.raises(AssertionError, match='duplicate_commits'):
        module.assert_guarded_safe(report)


def test_duplicate_and_missing_distinct_keys_cannot_cancel_in_totals(tmp_path, monkeypatch):
    import threading
    module = evaluator()
    original = module.EvidenceStore.execute
    recorded = threading.Barrier(3, timeout=10)
    def corrupt_key(lab, sid, rid, body):
        response = original(lab, sid, rid, body)
        if body.idempotency_key.startswith('key-'):
            recorded.wait()  # all three distinct records exist before corruption
            if body.idempotency_key == 'key-1':
                with lab.locked(sid) as state:
                    action = next(a for a in state['actions'] if a['action_id'] == response['action_id'])
                    action['idempotency_key'] = 'key-0'
        return response
    monkeypatch.setattr(module.EvidenceStore, 'execute', corrupt_key)
    report = module.evaluate_database(f'sqlite:///{tmp_path}/cancelling-errors.db', rounds=1, workers=3, samples=1, warmups=0)
    guarded = next(row for row in report['strategies'] if row['strategy'] == 'atomic_guard')
    unique = next(w for w in guarded['workloads'] if w['name'] == 'unique_keys')
    assert unique['totals']['new_actions'] == 3  # aggregate alone looks correct
    with pytest.raises(AssertionError, match='duplicate_commits'):
        module.assert_guarded_safe(report)


def test_real_lock_timeout_is_kept_and_same_key_recovery_is_separate(tmp_path):
    module = evaluator()
    report = module.evaluate_database(f'sqlite:///{tmp_path}/busy.db', rounds=1, workers=2, samples=1, warmups=0)
    for strategy in report['strategies']:
        workloads = {w['name']: w for w in strategy['workloads']}
        assert 'lock_timeout_retry' in workloads, 'real lock-timeout recovery experiment is missing'
        row = workloads['lock_timeout_retry']
        assert row['totals']['operational_errors'] == 2
        assert row['totals']['recovered_requests'] == 2
        assert row['totals']['unresolved_errors'] == 0
        run = row['runs'][0]
        assert run['first_wave_actions'] == []
        assert len(run['persisted_actions']) == 1
        assert all(a['observed'] == 'operational_error' for a in run['attempts'])
        assert {a['key'] for a in run['recovery_attempts']} == {'shared'}
        assert len({a['action_id'] for a in run['recovery_attempts']}) == 1
    module.assert_guarded_safe(report)


def test_failed_report_is_preserved_without_overwriting_published_evidence(tmp_path):
    module = evaluator()
    assert hasattr(module, 'save_report'), 'failed-run evidence writer is missing'
    target = tmp_path / 'report.json'
    target.write_text('previous successful evidence')
    failed = dict(databases=[dict(database='sqlite', strategies=[dict(strategy='atomic_guard',
        latency=dict(commits=0, requests=1), workloads=[])])])
    with pytest.raises(SystemExit):
        module.save_report(failed, target)
    assert target.read_text() == 'previous successful evidence'
    import json
    diagnostic = json.loads((tmp_path / 'report.failed.json').read_text())
    assert diagnostic['validation']['passed'] is False
    assert 'normal requests' in diagnostic['validation']['failures'][0]


def test_pool_timeout_without_dbapi_origin_is_recorded():
    from sqlalchemy.exc import TimeoutError
    module = evaluator()
    def exhausted():
        raise TimeoutError('pool exhausted')
    result = module.attempt(exhausted)
    assert result['observed'] == 'operational_error'
    assert result['error']['status'] == 503
    assert result['error']['sqlstate'] is None


def test_success_without_sql_record_survives_collection_for_failed_report(tmp_path, monkeypatch):
    module = evaluator()
    monkeypatch.setattr(module.EvidenceStore, 'execute',
        lambda *args: dict(action_id='missing-sql-record', replayed=False))
    report = module.evaluate_database(f'sqlite:///{tmp_path}/missing.db', rounds=1, workers=2, samples=1, warmups=0)
    guarded = next(s for s in report['strategies'] if s['strategy'] == 'atomic_guard')
    assert guarded['latency']['persistence_mismatches'] == 1
    assert all(w['totals']['response_mismatches'] == 2 for w in guarded['workloads'])
    with pytest.raises(SystemExit):
        module.save_report(dict(databases=[report]), tmp_path / 'missing.json')
    assert (tmp_path / 'missing.failed.json').exists()
