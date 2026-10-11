"""The offline oracle must expose removed validation, deduplication, and overblocking."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException


def load_evaluation():
    path = Path(__file__).resolve().parents[2] / 'scripts/evaluate_safety.py'
    assert path.exists(), 'reproducible SQL safety evaluation is missing'
    spec = importlib.util.spec_from_file_location('evaluate_safety', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_same_schedules_reveal_stale_commits_and_preserve_valid_actions(tmp_path):
    evaluation = load_evaluation()
    report = evaluation.evaluate_database(f'sqlite:///{tmp_path}/evaluation.db')
    results = {row['strategy']: row for row in report['results']}
    assert len(results) == 3
    schedules = [[(c['case'], c['schedule'], c['expected_reason']) for c in r['cases']]
                 for r in results.values()]
    assert schedules[0] == schedules[1] == schedules[2]
    for result in results.values():
        counts = result['totals']
        assert counts['cases'] == 9 and counts['submissions'] == 10
        assert counts['stale_opportunities'] == 6 and counts['valid_first_action_opportunities'] == 3
        assert counts['false_rejects'] == 0 and counts['duplicate_commits'] == 0
        assert counts['retry_opportunities'] == 1
    assert results['trust_at_creation']['totals']['stale_accepts'] == 6
    assert results['check_then_act']['totals']['stale_accepts'] == 5
    assert results['atomic_guard']['totals']['stale_accepts'] == 0
    assert results['atomic_guard']['totals']['commits'] == 3
    assert results['atomic_guard']['totals']['replays'] == 1
    evaluation.assert_guarded_safe(report)
    aba = next(c for c in results['atomic_guard']['cases'] if c['case'] == 'revision_aba')
    assert aba['state_at_submit']['cited_text_equals_receipt'] is True
    assert aba['state_at_submit']['source_revision'] == 3
    assert aba['state_at_submit']['receipt_revision'] == 1


def test_removed_production_guard_is_detected_from_committed_sql_state(tmp_path, monkeypatch):
    evaluation = load_evaluation()
    # Mutation: replacing execute's validate+append with a blind SQL append must fail.
    monkeypatch.setattr(evaluation.EvidenceStore, 'execute',
        lambda lab, sid, rid, body: evaluation.unsafe_record(lab, sid, rid, body))
    report = evaluation.evaluate_database(f'sqlite:///{tmp_path}/unguarded.db')
    guarded = next(r for r in report['results'] if r['strategy'] == 'atomic_guard')
    assert guarded['totals']['stale_accepts'] == 6
    with pytest.raises(AssertionError, match='stale_accepts'):
        evaluation.assert_guarded_safe(report)


def test_false_rejection_is_counted_and_fails_the_guardrail(tmp_path, monkeypatch):
    evaluation = load_evaluation()
    # Mutation: execute rejects every current receipt, including unrelated edits.
    def reject(*args):
        raise HTTPException(409, 'mutant_reject_all')
    monkeypatch.setattr(evaluation.EvidenceStore, 'execute', reject)
    report = evaluation.evaluate_database(f'sqlite:///{tmp_path}/reject-all.db')
    guarded = next(r for r in report['results'] if r['strategy'] == 'atomic_guard')
    assert guarded['totals']['false_rejects'] == 3
    with pytest.raises(AssertionError, match='false_rejects'):
        evaluation.assert_guarded_safe(report)


def test_missing_idempotency_is_counted_using_persisted_action_ids(tmp_path, monkeypatch):
    evaluation = load_evaluation()
    # Mutation: a caller retries the same key but execute creates a second action.
    original = evaluation.EvidenceStore.execute
    def no_dedup(lab, sid, rid, body):
        changed = evaluation.Execute(idempotency_key=body.idempotency_key + str(len(lab.actions(sid)['actions'])))
        return original(lab, sid, rid, changed)
    monkeypatch.setattr(evaluation.EvidenceStore, 'execute', no_dedup)
    report = evaluation.evaluate_database(f'sqlite:///{tmp_path}/duplicates.db')
    guarded = next(r for r in report['results'] if r['strategy'] == 'atomic_guard')
    assert guarded['totals']['duplicate_commits'] == 1
    with pytest.raises(AssertionError, match='duplicate_commits'):
        evaluation.assert_guarded_safe(report)
