"""Offline SQL comparison: contended correctness and separate normal-path cost.

Unsafe controls stay in scripts, never in public routes. No fake clock, load
generator, network latency or synchronization wait is included in cost samples.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from evaluate_safety import STRATEGIES, unsafe_record
from recheck.config import Settings
from recheck.evidence import EvidenceStore
from recheck.evidence_routes import Execute, Prepare, SourceEvent
from recheck.store import DemoSession, Store

WORKLOADS = ('same_key', 'unique_keys', 'edit_after_check', 'replay_after_edit', 'lock_timeout_retry')
METRICS = ('requests', 'committed_responses', 'replays', 'rejections',
           'operational_errors', 'new_actions', 'stale_commits',
           'duplicate_commits', 'missing_actions', 'missing_replays', 'response_mismatches',
           'recovery_requests', 'recovered_requests', 'recovery_replays', 'unresolved_errors',
           'first_wave_new_actions', 'recovery_new_actions')


def fresh(lab):
    sid = lab.store.create_session()['session_id']
    try:
        receipt = lab.prepare(sid, Prepare(query='하루 이체 한도', product='answer', idempotency_key='prepare'))
        assert receipt['references'][0]['source_id'] == 'transfer'
        return sid, receipt
    except BaseException:
        clean(lab, sid)
        raise


def clean(lab, sid):
    with lab.store.transaction(write=True) as db:
        db.execute(delete(DemoSession).where(DemoSession.id == sid))


def edit(lab, sid):
    return lab.event(sid, SourceEvent(source_id='transfer', revision=2,
        text='하루 이체 한도는 100만 원입니다. 송금 본인 인증이 필요합니다.'))


def checked(lab, strategy, sid, rid):
    return lab.use(sid, rid) if strategy == 'check_then_act' else None


def record(lab, strategy, sid, rid, key, check):
    if check and not check['valid']:
        raise HTTPException(409, check['reason'])
    return (lab.execute if strategy == 'atomic_guard' else
            lambda sid, rid, body: unsafe_record(lab, sid, rid, body))(
                sid, rid, Execute(idempotency_key=key))


def attempt(operation):
    try:
        response = operation()
        return dict(observed='replayed' if response['replayed'] else 'committed',
                    action_id=response['action_id'], error=None)
    except HTTPException as exc:
        return dict(observed='rejected', action_id=None,
                    error=dict(status=exc.status_code, reason=exc.detail))
    except SQLAlchemyError as exc:
        # Matches the API's 503 classification, without leaking connection data.
        origin = getattr(exc, 'orig', None)
        return dict(observed='operational_error', action_id=None,
                    error=dict(status=503, reason='database_unavailable', type=type(exc).__name__,
                               sqlstate=getattr(origin, 'sqlstate', None),
                               sqlite_errorname=getattr(origin, 'sqlite_errorname', None)))


def contended(lab, strategy, name, workers):
    sid, receipt = fresh(lab)
    rid = receipt['id']
    ready = threading.Barrier(workers + 1, timeout=15)
    proceed = threading.Event()
    try:
        before = []
        if name == 'replay_after_edit':
            # A known valid historical record, identical for all strategies.
            unsafe_record(lab, sid, rid, Execute(idempotency_key='shared'))
            before = lab.snapshot(sid)['actions']
            edit(lab, sid)

        def worker(index):
            check = None
            error = None
            try:
                check = checked(lab, strategy, sid, rid)
            except (HTTPException, SQLAlchemyError) as exc:
                error = exc
            ready.wait()
            if not proceed.wait(15):
                raise TimeoutError('workload release was not signalled')
            key = f'key-{index}' if name == 'unique_keys' else 'shared'
            def submit():
                if error:
                    raise error
                return record(lab, strategy, sid, rid, key, check)
            return dict(worker=index, key=key, separate_check=check, **attempt(submit))

        # Deliberately retain the real SQL lock until the bounded requests time
        # out. No sleep or synthetic exception: the DB enforces its own limit.
        held = lab.locked(sid) if name == 'lock_timeout_retry' else nullcontext()
        with held, ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(worker, i) for i in range(workers)]
            try:
                ready.wait()
                # All separate checks have completed, but no write has started.
                # This is a controlled interleaving, not a random race rate.
                if name == 'edit_after_check':
                    edit(lab, sid)
            finally:
                proceed.set()
            attempts = [future.result(timeout=15) for future in futures]
        first_wave = lab.snapshot(sid)['actions']
        # A separate, bounded recovery phase. Never retry a validation rejection
        # and never erase the first-wave error. The whole strategy is rerun.
        recovery = []
        terminal = []
        for response in attempts:
            if response['observed'] == 'operational_error':
                key = response['key']
                retried = dict(worker=response['worker'], key=key, **attempt(
                    lambda: record(lab, strategy, sid, rid, key, checked(lab, strategy, sid, rid))))
                recovery.append(retried)
                terminal.append(retried)
            else:
                terminal.append(response)
        # Offline inspection retains the private synthetic idempotency key.
        # Aggregate record count cannot detect a duplicate hiding a missing key.
        after = lab.snapshot(sid)['actions']
        before_ids = {a['action_id'] for a in before}
        new = [a for a in after if a['action_id'] not in before_ids]
        first_new = [a for a in first_wave if a['action_id'] not in before_ids]
        response_mismatches = 0
        for responses, snapshot in ((attempts, first_wave), (recovery, after)):
            for response in responses:
                if response['action_id']:
                    action = next((a for a in snapshot if a['action_id'] == response['action_id']), None)
                    response_mismatches += int(action is None or
                        action['idempotency_key'] != response['key'] or action['receipt_id'] != rid)
        by_key = Counter(action['idempotency_key'] for action in after)
        first_by_key = Counter(action['idempotency_key'] for action in first_wave)
        expected_keys = {f'key-{i}' for i in range(workers)} if name == 'unique_keys' else {'shared'} if name in ('same_key', 'lock_timeout_retry') else set()
        allowed_by_key = workers if name == 'unique_keys' else 0 if before else 1
        totals = dict(requests=workers,
            committed_responses=sum(a['observed'] == 'committed' for a in attempts),
            replays=sum(a['observed'] == 'replayed' for a in attempts),
            rejections=sum(a['observed'] == 'rejected' for a in attempts),
            operational_errors=sum(a['observed'] == 'operational_error' for a in attempts),
            new_actions=len(new),
            stale_commits=max(len(new), len(first_new)) if name in ('edit_after_check', 'replay_after_edit') else 0,
            duplicate_commits=max(sum(max(0, count - 1) for count in by_key.values()),
                sum(max(0, count - 1) for count in first_by_key.values()), len(new) - allowed_by_key, len(first_new) - allowed_by_key, 0),
            missing_actions=sum(by_key[key] == 0 for key in expected_keys),
            missing_replays=sum(a['observed'] != 'replayed' for a in terminal) if before else 0,
            response_mismatches=response_mismatches,
            recovery_requests=len(recovery), recovered_requests=sum(a['observed'] != 'operational_error' for a in recovery),
            recovery_replays=sum(a['observed'] == 'replayed' for a in recovery),
            unresolved_errors=sum(a['observed'] == 'operational_error' for a in terminal),
            first_wave_new_actions=len(first_new), recovery_new_actions=len(new) - len(first_new))
        return dict(receipt_id=rid, attempts=attempts, initial_actions=before,
                    first_wave_actions=first_wave, recovery_attempts=recovery, terminal_attempts=terminal,
                    persisted_actions=after, per_key_counts=dict(by_key), totals=totals)
    finally:
        proceed.set()
        clean(lab, sid)


def normal_sample(lab, strategy):
    sid, receipt = fresh(lab)
    try:
        start = time.perf_counter_ns()
        response = attempt(lambda: record(lab, strategy, sid, receipt['id'], 'new',
                                           checked(lab, strategy, sid, receipt['id'])))
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        # Persistence verification and fixture cleanup are outside the timer.
        actions = lab.snapshot(sid)['actions']
        expected = response['observed'] == 'committed'
        matches = (len(actions) == 1 and actions[0]['action_id'] == response['action_id']
                   and actions[0]['receipt_id'] == receipt['id'] and actions[0]['idempotency_key'] == 'new')
        mismatch = not matches if expected else bool(actions)
        return dict(elapsed_ms=elapsed, persisted_count=len(actions), persisted_actions=actions,
                    persistence_mismatch=mismatch, **response)
    finally:
        clean(lab, sid)


def latency(rows):
    values = sorted(r['elapsed_ms'] for r in rows)
    return dict(requests=len(rows), commits=sum(r['observed'] == 'committed' for r in rows),
        rejections=sum(r['observed'] == 'rejected' for r in rows),
        operational_errors=sum(r['observed'] == 'operational_error' for r in rows),
        persistence_mismatches=sum(r['persistence_mismatch'] for r in rows),
        p50_ms=values[math.ceil(len(values)*.5)-1], p95_ms=values[math.ceil(len(values)*.95)-1],
        samples_ms=[r['elapsed_ms'] for r in rows], samples=rows)


def evaluate_database(database_url, *, rounds=12, workers=6, samples=90, warmups=9):
    if not (1 <= rounds <= 50 and 2 <= workers <= 12 and 1 <= samples <= 1000 and 0 <= warmups <= 100):
        raise ValueError('workload bounds exceeded')
    store = Store(Settings(database_url=database_url))
    lab = EvidenceStore(store)
    try:
        with store.engine.connect() as db:
            version = db.exec_driver_sql('select sqlite_version()' if store.sqlite else 'select version()').scalar_one()
        measured = {strategy: [] for strategy in STRATEGIES}
        # Rotate first/middle/last position to reduce fixed ordering bias.
        # Pool warmups and fixtures use the same call paths, outside samples.
        for index in range(warmups + samples):
            order = STRATEGIES[index % 3:] + STRATEGIES[:index % 3]
            for strategy in order:
                sample = normal_sample(lab, strategy)
                if index >= warmups:
                    measured[strategy].append(sample)
        runs = {s: {name: [] for name in WORKLOADS} for s in STRATEGIES}
        for index in range(rounds):
            for name in WORKLOADS:
                order = STRATEGIES[index % 3:] + STRATEGIES[:index % 3]
                for strategy in order:
                    runs[strategy][name].append(contended(lab, strategy, name, workers))
        return dict(database=store.engine.dialect.name, database_version=version,
            strategies=[dict(strategy=strategy, latency=latency(measured[strategy]),
                workloads=[dict(name=name, runs=rows,
                    totals={metric: sum(row['totals'][metric] for row in rows) for metric in METRICS})
                    for name, rows in runs[strategy].items()]) for strategy in STRATEGIES])
    finally:
        store.engine.dispose()


def assert_guarded_safe(database):
    guarded = next(row for row in database['strategies'] if row['strategy'] == 'atomic_guard')
    assert guarded['latency']['commits'] == guarded['latency']['requests'], 'guard rejected normal requests'
    assert guarded['latency'].get('persistence_mismatches', 0) == 0, 'normal response differs from SQL record'
    for workload in guarded['workloads']:
        for key in ('stale_commits', 'duplicate_commits', 'missing_actions', 'missing_replays', 'unresolved_errors', 'response_mismatches'):
            assert workload['totals'][key] == 0, f"{workload['name']} {key}={workload['totals'][key]}"
        if workload['name'] == 'edit_after_check':
            assert all(a['observed'] == 'rejected' and a['error']['reason'] == 'source_changed'
                       for run in workload['runs'] for a in run['terminal_attempts'])
        if workload['name'] in ('same_key', 'unique_keys', 'lock_timeout_retry'):
            assert all(a['observed'] in ('committed', 'replayed')
                       for run in workload['runs'] for a in run['terminal_attempts'])


def save_report(report, destination):
    failures = []
    for database in report['databases']:
        try:
            assert_guarded_safe(database)
        except AssertionError as exc:
            failures.append(f"{database['database']}: {exc}")
    report['validation'] = dict(passed=not failures, failures=failures)
    target = destination.with_suffix('.failed.json') if failures else destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if failures:
        raise SystemExit(f"Failed run preserved at {target}: {'; '.join(failures)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-url-env')
    parser.add_argument('--output', default='docs/evidence/action-workloads.json')
    parser.add_argument('--rounds', type=int, default=12)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--samples', type=int, default=90)
    parser.add_argument('--warmups', type=int, default=9)
    args = parser.parse_args()
    options = {key: getattr(args, key) for key in ('rounds', 'workers', 'samples', 'warmups')}
    with tempfile.TemporaryDirectory(prefix='recheck-actions-') as directory:
        databases = [evaluate_database(f'sqlite:///{directory}/actions.db', **options)]
    if args.postgres_url_env:
        databases.append(evaluate_database(os.environ[args.postgres_url_env], **options))
    paths = ['scripts/evaluate_action_workloads.py', 'scripts/evaluate_safety.py',
             'backend/recheck/evidence.py', 'backend/recheck/store.py', 'backend/recheck/retrieval.py']
    report = dict(schema_version=1, measured_at=datetime.now(timezone.utc).isoformat(),
        environment=dict(python=platform.python_version(), platform=platform.platform(), cpu_count=os.cpu_count()),
        parameters=options, scope='Owned synthetic SQL records; offline comparison, not a production SLA.',
        timing='perf_counter_ns around direct store check + recording through SQL commit. '
               'Warmups, session/receipt creation, SQL inspection, cleanup, HTTP and controlled interleaving waits excluded. '
               'All outcomes retained in sample denominator; nearest-rank percentiles. '
               'Strategy order rotates each round; fresh identical state for each normal request.',
        concurrency='Independent connections in threads, synchronized after the separate-check opportunity. '
                    'Source edit is committed before simultaneous writes in edit_after_check. '
                    'All strategies deduplicate the same key. check_then_act checks before its deduplication. '
                    'One separately recorded same-key retry after the wave for SQL operational failures only. '
                    'The lock_timeout_retry workload deliberately holds a real SQL lock until first-wave timeouts.',
        limitations=['Five controlled workloads, not arbitrary schedule exploration or sustained load.',
                     'Normal request samples share a host and database pool; they are not independent production trials.',
                     'Historical replay is not a new stale write. It does not revalidate the old answer.',
                     'No external side effects, multi-host guarantee, model quality or applicant authorship claim.'],
        source_sha256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
        postgres_status='measured' if args.postgres_url_env else 'not run', databases=databases)
    destination = Path(args.output)
    save_report(report, destination)
    print(json.dumps(dict(output=str(destination), databases=[dict(database=db['database'],
        strategies=[dict(strategy=s['strategy'], p50_ms=s['latency']['p50_ms'], p95_ms=s['latency']['p95_ms'],
            workloads=[dict(name=w['name'], **w['totals']) for w in s['workloads']]) for s in db['strategies']])
        for db in databases]), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
