"""Offline, fixed-schedule SQL counterexamples. Never import this from the API.

Unsafe modes differ only in validation timing; all three deduplicate retries.
The oracle is declared by the schedule, independent of the guard's response.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from fastapi import HTTPException
from sqlalchemy import delete
from recheck import evidence
from recheck.config import Settings
from recheck.evidence import EvidenceStore
from recheck.evidence_routes import Execute, Prepare, SourceEvent
from recheck.store import DemoSession, Store

STRATEGIES = ('trust_at_creation', 'check_then_act', 'atomic_guard')
# Each mutation occurs at an explicit boundary; no thread timing or sleeps.
CASES = (
    ('current', None, None, 'current', 1),
    ('cited_edit_before_check', 'edit', None, 'source_changed', 1),
    ('cited_edit_after_check', None, 'edit', 'source_changed', 1),
    ('unrelated_edit', None, 'unrelated', 'current', 1),
    ('deletion', None, 'delete', 'source_deleted', 1),
    ('ttl_expiry', None, 'expire', 'receipt_expired', 1),
    ('release_change', None, 'release', 'release_changed', 1),
    ('revision_aba', None, 'aba', 'source_changed', 1),
    ('duplicate_submission', None, None, 'current', 2),
)


def unsafe_record(lab, sid, rid, body):
    """Offline negative control: real SQL append with dedup but NO validation."""
    with lab.locked(sid) as state:
        actions = state.setdefault('actions', [])
        previous = next((a for a in actions if a['idempotency_key'] == body.idempotency_key), None)
        if previous:
            if previous['receipt_id'] != rid:
                raise HTTPException(409, 'action_idempotency_conflict')
            return dict(previous, replayed=True)
        receipt = next(r for r in state['receipts'] if r['id'] == rid)
        action = dict(action_id=str(uuid.uuid4()), receipt_id=rid, output=receipt['output'],
                      committed_at=evidence.now(), release_epoch=receipt['release_epoch'],
                      references=deepcopy(receipt['references']),
                      scope='offline unsafe comparison: owned synthetic SQL task only',
                      idempotency_key=body.idempotency_key)
        actions.insert(0, action)
        return dict(action, replayed=False)


def mutate(lab, sid, name, receipt, clock):
    if name == 'expire':
        clock[0] = receipt['expires_at']  # exact >= boundary, without sleeping
        return
    if name == 'release':
        report = lab.evaluate(sid, 'paired')
        assert report['passed'], 'release fixture must pass the real paired gate'
        lab.promote(sid, report['id'])
        return
    source_id = 'card' if name == 'unrelated' else receipt['references'][0]['source_id']
    original = lab.snapshot(sid)['sources'][source_id]
    lab.event(sid, SourceEvent(source_id=source_id, revision=original['revision'] + 1,
        text='' if name == 'delete' else original['text'] + ' 최신 적용 내용입니다.', deleted=name == 'delete'))
    if name == 'aba':
        lab.event(sid, SourceEvent(source_id=source_id, revision=original['revision'] + 2,
                                  text=original['text']))


def run_case(store, strategy, case):
    name, before, after, reason, submissions = case
    sid = store.create_session()['session_id']
    lab = EvidenceStore(store)
    # Only evidence time is controlled; session lifetime remains real time.
    clock = [1_800_000_000.0]
    schedule = ['prepare'] + ([before] if before else []) + ['check_opportunity'] + ([after] if after else []) + ['submit']
    if submissions == 2:
        schedule += ['retry_same_key']
    try:
        with patch.object(evidence, 'now', lambda: clock[0]):
            receipt = lab.prepare(sid, Prepare(query='하루 이체 한도', product='checklist', idempotency_key='prepare'))
            assert receipt['references'][0]['source_id'] == 'transfer', 'fixture changed: review scope'
            if before:
                mutate(lab, sid, before, receipt, clock)
            check = lab.use(sid, receipt['id']) if strategy == 'check_then_act' else None
            if after:
                mutate(lab, sid, after, receipt, clock)
            state = lab.snapshot(sid)
            ref = receipt['references'][0]
            source = state['sources'][ref['source_id']]
            facts = dict(source_id=ref['source_id'], source_revision=source['revision'],
                receipt_revision=ref['revision'], deleted=source['deleted'],
                cited_text_equals_receipt=source['text'] == ref['text'],
                active_release_epoch=state['active']['epoch'], receipt_release_epoch=receipt['release_epoch'],
                clock=clock[0], expires_at=receipt['expires_at'])
            attempts = []
            for attempt in range(submissions):
                existing_ids = {a['action_id'] for a in lab.actions(sid)['actions']}
                response = None
                error = None
                try:
                    if strategy == 'check_then_act' and not check['valid']:
                        raise HTTPException(409, check['reason'])
                    response = (lab.execute if strategy == 'atomic_guard' else
                                lambda sid, rid, body: unsafe_record(lab, sid, rid, body))(
                                    sid, receipt['id'], Execute(idempotency_key='same-action'))
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
                    error = dict(status=exc.status_code, reason=exc.detail)
                persisted = lab.actions(sid)['actions']
                new_actions = [a for a in persisted if a['action_id'] not in existing_ids]
                replay = bool(response and response['replayed'])
                # A claimed success without a stored action is an evaluator failure.
                if response:
                    assert any(a['action_id'] == response['action_id'] for a in persisted)
                attempts.append(dict(attempt=attempt + 1, expected='reject' if reason != 'current' else
                    'commit' if attempt == 0 else 'replay',
                    observed='rejected' if error else 'replayed' if replay else 'committed',
                    error=error, response=response, new_actions=new_actions,
                    persisted_action_count=len(persisted), stale_accepts=len(new_actions) if reason != 'current' else 0,
                    false_rejects=int(reason == 'current' and attempt == 0 and len(new_actions) == 0),
                    duplicate_commits=len(new_actions) if attempt > 0 else 0))
            return dict(case=name, schedule=schedule, expected_reason=reason,
                        receipt=receipt, state_at_submit=facts, separate_check=check, attempts=attempts)
    finally:
        # Clean up only this run's fresh session, including its cascaded SQL records.
        with store.transaction(write=True) as db:
            db.execute(delete(DemoSession).where(DemoSession.id == sid))


def totals(cases):
    attempts = [a for c in cases for a in c['attempts']]
    return dict(cases=len(cases), submissions=len(attempts),
        stale_opportunities=sum(c['expected_reason'] != 'current' for c in cases),
        valid_first_action_opportunities=sum(c['expected_reason'] == 'current' for c in cases),
        retry_opportunities=sum(len(c['attempts']) - 1 for c in cases),
        commits=sum(len(a['new_actions']) for a in attempts),
        rejections=sum(a['observed'] == 'rejected' for a in attempts),
        replays=sum(a['observed'] == 'replayed' for a in attempts),
        **{key: sum(a[key] for a in attempts) for key in ('stale_accepts', 'false_rejects', 'duplicate_commits')})


def evaluate_database(database_url):
    store = Store(Settings(database_url=database_url))
    try:
        with store.engine.connect() as db:
            version = db.exec_driver_sql('select sqlite_version()' if store.sqlite else 'select version()').scalar_one()
        results = []
        for strategy in STRATEGIES:
            cases = [run_case(store, strategy, case) for case in CASES]
            results.append(dict(strategy=strategy, cases=cases, totals=totals(cases)))
        return dict(database=store.engine.dialect.name, database_version=version, results=results)
    finally:
        store.engine.dispose()


def assert_guarded_safe(report):
    guarded = next(r for r in report['results'] if r['strategy'] == 'atomic_guard')
    counts = guarded['totals']
    for metric in ('stale_accepts', 'false_rejects', 'duplicate_commits'):
        assert counts[metric] == 0, f'atomic_guard {metric}={counts[metric]}'
    assert counts['replays'] == counts['retry_opportunities'], 'atomic_guard missing expected retry replay'
    for case in guarded['cases']:
        for attempt in case['attempts']:
            if attempt['expected'] == 'reject':
                assert attempt['error'] and attempt['error']['reason'] == case['expected_reason'], case['case']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-url-env', help='Environment variable containing a disposable PostgreSQL database URL; URL is never saved')
    parser.add_argument('--output', default='docs/evidence/safety-evaluation.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='recheck-safety-') as directory:
        databases = [evaluate_database(f'sqlite:///{directory}/safety.db')]
    if args.postgres_url_env:
        databases.append(evaluate_database(os.environ[args.postgres_url_env]))
    for database in databases:
        assert_guarded_safe(database)
    paths = ['scripts/evaluate_safety.py', 'backend/recheck/evidence.py', 'backend/recheck/retrieval.py', 'backend/recheck/store.py']
    report = dict(schema_version=1, measured_at=datetime.now(timezone.utc).isoformat(),
        environment=dict(python=platform.python_version(), platform=platform.platform()),
        scope='Nine deterministic ordered schedules per strategy, real SQL + production retrieval and guard. '
              'Owned synthetic task recording only; no external side effect, randomized load, general retrieval accuracy, or production SLA claim.',
        oracle='Expected validity declared per schedule independently of production use/execute. '
               'Stale and duplicate acceptance counted from new SQL action IDs; valid first actions must create a record.',
        matching='Same schedules, source/query, initial state and same-key idempotency for every strategy. '
                 'Only validation timing differs. Each case uses an isolated fresh session.',
        clock='Offline patch of evidence.now: fixed issuance at 1800000000; expiry case advances to exact expires_at. No sleep or production testing hook.',
        limitations=['Ordered boundary counterexamples, not concurrent stress; see backend/tests/test_evidence_actions.py for real race tests.',
                     'Six stale opportunities, three valid first-action opportunities and one retry per strategy per database; repeated engines are not independent random trials.',
                     'No measured latency/throughput, retrieval quality, user study, deployed reliability or external atomicity claim.'],
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        postgres_status='measured' if args.postgres_url_env else 'not run: no --postgres-url-env provided',
        databases=databases)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(output=str(destination), databases=[dict(database=d['database'],
        strategies=[dict(strategy=r['strategy'], **r['totals']) for r in d['results']]) for d in databases]), indent=2))


if __name__ == '__main__':
    main()
