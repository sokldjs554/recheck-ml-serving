"""Bounded local SQL contention/state-size matrix; not HTTP or model serving."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]
from sqlalchemy import select, text
from evaluate_action_workloads import attempt, clean
from recheck.config import Settings
from recheck.evidence import EvidenceState, EvidenceStore
from recheck.evidence_routes import Execute, Prepare, SourceEvent
from recheck.store import Store

PROFILES = {'small': (1, 0, 0), 'medium': (20, 10, 4), 'near_cap': (40, 20, 8)}
LOCAL = threading.local()


def percentile(values, quantile):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * quantile) - 1] if ordered else None


class MeasuredStore(Store):
    def row(self, db, sid, lock=False):
        start = time.perf_counter_ns()
        try:
            return super().row(db, sid, lock)
        finally:
            if lock and getattr(LOCAL, 'timings', None) is not None:
                LOCAL.timings.append((time.perf_counter_ns() - start) / 1e6)


class AuditedEvidenceStore(EvidenceStore):
    """Read-only audit while the production lock is held; no guard replacement."""
    @contextmanager
    def locked(self, sid):
        with super().locked(sid) as state:
            before = {a['action_id'] for a in state.get('actions', [])}
            yield state
            if getattr(LOCAL, 'audit', None) is not None:
                for action in state.get('actions', []):
                    if action['action_id'] not in before:
                        receipt = self.receipt(state, action['receipt_id'])
                        problems=[]
                        for ref in action['references']:
                            current=state['sources'][ref['source_id']]
                            if current['deleted'] or current['revision'] != ref['revision']:
                                problems.append('source_not_current')
                        if action['references'] != receipt['references']:
                            problems.append('receipt_reference_mismatch')
                        if action['release_epoch'] != state['active']['epoch']:
                            problems.append('release_not_current')
                        if action['committed_at'] >= receipt['expires_at']:
                            problems.append('expired')
                        LOCAL.audit.append(dict(session_id=sid, action_id=action['action_id'],
                            key=action['idempotency_key'],
                            validity=dict(valid=not problems,problems=problems)))


def fixture(lab, profile):
    """Only supported operations build fixtures; no arbitrary JSON padding."""
    sid = lab.store.create_session()['session_id']
    receipts, reports, actions = PROFILES[profile]
    try:
        first = None
        for index in range(receipts):
            receipt = lab.prepare(sid, Prepare(query='하루 이체 한도', product='checklist',
                idempotency_key=f'fixture-receipt-{index}'))
            first = first or receipt
        for _ in range(reports):
            lab.evaluate(sid, 'paired')
        for index in range(actions):
            lab.execute(sid, first['id'], Execute(idempotency_key=f'fixture-action-{index}'))
        return dict(sid=sid, rid=first['id'], initial=sql_state(lab.store, sid))
    except BaseException:
        clean(lab, sid)
        raise


def sql_state(store, sid):
    # Read SQL directly: snapshot() takes a write lock and rewrites JSON.
    with store.engine.connect() as db:
        state = db.execute(select(EvidenceState.payload).where(EvidenceState.session_id == sid)).scalar_one()
        stored = db.execute(text('SELECT length(CAST(payload AS TEXT)) FROM evidence_states WHERE session_id=:sid'
            if store.sqlite else 'SELECT octet_length(payload::text) FROM evidence_states WHERE session_id=:sid'), {'sid': sid}).scalar_one()
    canonical = json.dumps(state, ensure_ascii=False, separators=(',', ':')).encode()
    # Persist identities/versions and size/hash, not repeated document outputs.
    projection = dict(sources={key: dict(revision=value['revision'], deleted=value['deleted'])
        for key, value in state['sources'].items()},
        receipts=[{key: receipt[key] for key in ('id', 'expires_at', 'release_epoch')}
            for receipt in state['receipts']], reports=[dict(id=report['id'], passed=report['passed'])
            for report in state['reports']],
        actions=[{key: value for key, value in action.items() if key not in ('output', 'scope')}
            for action in state['actions']])
    return dict(state=projection, stored_json_bytes=stored,
        canonical_utf8_bytes=len(canonical), canonical_sha256=hashlib.sha256(canonical).hexdigest())


def request(lab, item):
    LOCAL.timings, LOCAL.audit = [], []
    start = time.perf_counter_ns()
    try:
        if item['operation'] == 'execute':
            outcome = attempt(lambda: lab.execute(item['sid'], item['rid'], Execute(idempotency_key=item['key'])))
        else:
            def edit():
                result = lab.event(item['sid'], SourceEvent(source_id='transfer', revision=item['revision'],
                    text=f"하루 이체 한도는 {item['revision']}00만 원입니다. 송금 본인 인증이 필요합니다."))
                return dict(action_id=None, replayed=False, **result)
            outcome = attempt(edit)
            if outcome['observed'] == 'committed':
                outcome['observed'] = 'edited'
        finished=time.perf_counter_ns()
        queued_ms=(start-item.get('submitted_ns',start))/1e6
        return dict(**item, **outcome, elapsed_ms=(finished-start)/1e6+queued_ms,
            service_ms=(finished-start)/1e6, executor_queue_ms=queued_ms,
            row_acquisition_ms=list(LOCAL.timings), action_audit=list(LOCAL.audit))
    finally:
        LOCAL.timings = LOCAL.audit = None


def reconcile(fixtures, requests, final_states):
    initial_ids = {a['action_id'] for f in fixtures for a in f['initial']['state']['actions']}
    actions = [(sid, a) for sid, state in final_states.items() for a in state['state']['actions']
               if a['action_id'] not in initial_ids]
    by_key = Counter((sid, a['idempotency_key']) for sid, a in actions)
    submitted = {(r['sid'], r['key']) for r in requests if r['operation'] == 'execute'}
    audit = {a['action_id']: a for r in requests for a in r['action_audit']}
    successes = [r for r in requests if r['operation'] == 'execute' and r['observed'] in ('committed', 'replayed')]
    missing = [r['key'] for r in successes if not any(sid == r['sid'] and a['action_id'] == r['action_id']
        and a['idempotency_key'] == r['key'] and a['receipt_id'] == r['rid'] for sid, a in actions)]
    unresolved = []
    persisted_after_error = []
    refused_with_action = []
    for r in requests:
        if r['operation'] != 'execute':
            continue
        matching = [a for sid, a in actions if sid == r['sid'] and a['idempotency_key'] == r['key']]
        if r['observed'] == 'operational_error':
            (persisted_after_error if matching else unresolved).append(r['key'])
        if r['observed'] == 'rejected' and matching:
            refused_with_action.append(r['key'])
    unacknowledged = [a['action_id'] for sid, a in actions if not any(
        r['sid'] == sid and r['action_id'] == a['action_id'] for r in successes)]
    missing_audit = [a['action_id'] for _, a in actions if a['action_id'] not in audit]
    stale = [a['action_id'] for _, a in actions if a['action_id'] in audit and not audit[a['action_id']]['validity']['valid']]
    result = dict(new_actions=len(actions), duplicate_actions=sum(max(0, n-1) for n in by_key.values()),
        missing_acknowledged_actions=missing, stale_actions=stale, missing_action_audit=missing_audit,
        unexpected_actions=[a['action_id'] for sid, a in actions if (sid, a['idempotency_key']) not in submitted],
        persisted_after_error=persisted_after_error, operational_errors_without_action=unresolved,
        refused_with_action=refused_with_action, unacknowledged_actions=unacknowledged,
        per_key_counts=[dict(sid=sid, key=key, count=count) for (sid, key), count in by_key.items()])
    result['passed'] = not any(result[k] for k in ('duplicate_actions', 'missing_acknowledged_actions',
        'stale_actions', 'missing_action_audit', 'unexpected_actions', 'refused_with_action'))
    return result


class LockSampler:
    """Sample server lock waits, separate from the four-connection request pool."""
    def __init__(self, store, application_name):
        self.store, self.application_name = store, application_name
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.samples = []
        self.error = None

    def run(self):
        import psycopg
        try:
            url = self.store.engine.url
            with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password,
                                dbname=url.database, autocommit=True) as db:
                self.ready.set()
                while not self.stop.is_set():
                    rows = db.execute("SELECT wait_event_type, wait_event, count(*) FROM pg_stat_activity "
                        "WHERE application_name=%s GROUP BY 1,2", (self.application_name,)).fetchall()
                    self.samples.append(dict(at=time.time(), groups=[dict(type=t, event=e, count=n) for t,e,n in rows]))
                    self.stop.wait(.005)
        except Exception as exc:
            self.error = type(exc).__name__
            self.ready.set()

    def __enter__(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()
        if not self.ready.wait(5):
            self.stop.set()
            raise TimeoutError("local lock sampler did not connect")
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(5)


def summarize(rows, duration, sampler):
    executions = [r for r in rows if r['operation'] == 'execute']
    waits = [value for r in rows for value in r['row_acquisition_ms']]
    outcomes = Counter(r['observed'] for r in executions)
    lock_samples = [sum(g['count'] for g in sample['groups'] if g['type'] == 'Lock') for sample in sampler.samples]
    return dict(duration_seconds=duration, operations=len(rows), offered_operations=len(rows), sent_operations=len(rows),
        completed_operations=len(rows), execute_requests=len(executions),
        edit_requests=len(rows)-len(executions), outcomes=dict(outcomes),
        edit_outcomes=dict(Counter(r['observed'] for r in rows if r['operation']=='edit')),
        operations_per_second=len(rows)/duration, execute_per_second=len(executions)/duration,
        useful_new_actions_per_second=outcomes['committed']/duration,
        executor_queue_p95_ms=percentile([r.get('executor_queue_ms',0) for r in rows], .95),
        execute_p50_ms=percentile([r['elapsed_ms'] for r in executions], .5),
        execute_p95_ms=percentile([r['elapsed_ms'] for r in executions], .95),
        all_operations_p95_ms=percentile([r['elapsed_ms'] for r in rows], .95),
        row_acquisition_p50_ms=percentile(waits,.5), row_acquisition_p95_ms=percentile(waits,.95),
        lock_timeouts=sum(r['error'] is not None and r['error'].get('sqlstate')=='55P03' for r in rows),
        statement_timeouts=sum(r['error'] is not None and r['error'].get('sqlstate')=='57014' for r in rows),
        refusal_reasons=dict(Counter(r['error']['reason'] for r in rows if r['observed']=='rejected')),
        lock_wait_sample_count=sum(n>0 for n in lock_samples), lock_sampler_samples=len(lock_samples),
        max_sampled_lock_waiters=max(lock_samples,default=0), lock_sampler_error=sampler.error)


def run_cell(lab, *, sharing, workers, edit_every, profile, waves=4, repeat=0, application_name=''):
    if sharing not in ('shared', 'distinct') or not 1 <= workers <= 8 or not 1 <= waves <= 4:
        raise ValueError('bounded local workload required')
    if edit_every not in (0, 2, 4):
        raise ValueError('edit_every must be 0, 2 or 4 waves')
    fixtures = []
    try:
        for _ in range(1 if sharing=='shared' else workers):
            fixtures.append(fixture(lab, profile))
        rows = []
        with LockSampler(lab.store, application_name) as sampler, ThreadPoolExecutor(max_workers=workers) as pool:
            start = time.perf_counter()
            for wave in range(waves):
                jobs = []
                # Edit at waves 1/3 (50%) or wave 3 (25%). Round-robin insertion
                # rotates ordering; SQL decides whether simultaneous actions precede edits.
                edits = edit_every and (wave+1) % edit_every == 0
                for index in range(workers):
                    f = fixtures[0 if sharing=='shared' else index]
                    jobs.append(dict(operation='execute', sid=f['sid'], rid=f['rid'],
                        key=f'matrix-{wave}-{index}', wave=wave, worker=index))
                    if edits and (sharing=='distinct' or index==0):
                        jobs.append(dict(operation='edit', sid=f['sid'], revision=2+wave,
                            wave=wave, worker=index))
                # Reversing alternates edit-first and execute-first placement.
                if (wave+repeat) % 2:
                    jobs.reverse()
                submitted_ns=time.perf_counter_ns()
                for job in jobs:
                    job['submitted_ns']=submitted_ns
                rows.extend(pool.map(lambda item: request(lab, item), jobs))
            duration = time.perf_counter()-start
        final = {f['sid']: sql_state(lab.store, f['sid']) for f in fixtures}
        return dict(parameters=dict(sharing=sharing, workers=workers, edit_every=edit_every,
                profile=profile, waves=waves, repeat=repeat),
            summary=summarize(rows,duration,sampler), requests=rows,
            initial_states={f['sid']: f['initial'] for f in fixtures}, final_states=final,
            lock_wait_samples=sampler.samples, reconciliation=reconcile(fixtures,rows,final))
    finally:
        for f in fixtures:
            clean(lab, f['sid'])



def probe_caps(lab):
    from fastapi import HTTPException
    from pydantic import ValidationError
    f=fixture(lab, 'near_cap')
    results={}
    try:
        for index in range(32):
            lab.execute(f['sid'], f['rid'], Execute(idempotency_key=f'cap-{index}'))
        for name,operation in (
            ('action_41',lambda:lab.execute(f['sid'],f['rid'],Execute(idempotency_key='cap-overflow'))),
            ('receipt_41',lambda:lab.prepare(f['sid'],Prepare(query='하루 이체 한도',product='answer',idempotency_key='cap-overflow'))),
            ('report_21',lambda:lab.evaluate(f['sid'],'paired'))):
            try:
                operation()
                results[name]=dict(unexpected_success=True)
            except HTTPException as exc:
                results[name]=dict(status=exc.status_code,reason=exc.detail)
        try:
            SourceEvent(source_id='transfer',revision=2,text='x'*601)
            results['source_601_characters']=dict(unexpected_success=True)
        except ValidationError:
            results['source_601_characters']=dict(validation_rejected=True)
        results['final_sql']=sql_state(lab.store,f['sid'])
        return results
    finally:
        clean(lab,f['sid'])


def save_report(report, destination):
    failures = [dict(parameters=r['parameters'],reason='sql_reconciliation')
        for r in report['runs'] if not r['reconciliation']['passed']]
    failures.extend(dict(parameters=r['parameters'],reason='lock_sampler_failed') for r in report['runs']
        if r.get('summary',{}).get('lock_sampler_error'))
    if 'cap_probe' in report:
        expected={'action_41':'evidence_action_capacity','receipt_41':'evidence_receipt_capacity',
            'report_21':'release_report_capacity'}
        for name,reason in expected.items():
            if report['cap_probe'][name] != dict(status=429,reason=reason):
                failures.append(dict(reason='cap_probe_mismatch',probe=name))
        if report['cap_probe']['source_601_characters'] != dict(validation_rejected=True):
            failures.append(dict(reason='source_length_cap_mismatch'))
    report['validation'] = dict(passed=not failures, failures=failures)
    target = destination.with_suffix('.failed.json') if failures else destination
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if failures:
        raise SystemExit(f'Failed SQL reconciliation preserved at {target}')



def matrix_summary(report):
    groups={}
    for run in report['runs']:
        key=tuple(run['parameters'][name] for name in ('sharing','workers','edit_every','profile'))
        groups.setdefault(key,[]).append(run)
    cells=[]
    for key,runs in groups.items():
        rows=[row for run in runs for row in run['requests']]
        sampler=type('Sampler',(),dict(samples=[sample for run in runs for sample in run['lock_wait_samples']],
            error=next((run['summary']['lock_sampler_error'] for run in runs if run['summary']['lock_sampler_error']),None)))()
        sizes=[state['stored_json_bytes'] for run in runs for state in run['initial_states'].values()]
        final_sizes=[state['stored_json_bytes'] for run in runs for state in run['final_states'].values()]
        cells.append(dict(parameters=dict(zip(('sharing','workers','edit_every','profile'),key)),
            repeats=len(runs), **summarize(rows,sum(run['summary']['duration_seconds'] for run in runs),sampler),
            initial_json_bytes_min=min(sizes),initial_json_bytes_max=max(sizes),
            final_json_bytes_min=min(final_sizes),final_json_bytes_max=max(final_sizes),
            sql_new_actions=sum(run['reconciliation']['new_actions'] for run in runs),
            sql_reconciled=all(run['reconciliation']['passed'] for run in runs),
            persisted_after_error=sum(len(run['reconciliation']['persisted_after_error']) for run in runs),
            operational_errors_without_action=sum(len(run['reconciliation']['operational_errors_without_action']) for run in runs)))
    return dict(schema_version=1,measured_at=report['measured_at'],scope=report['scope'],
        environment=report['environment'],supported_caps=report['supported_caps'],
        aggregation='Pooled nearest-rank per-request percentiles; throughput=sum(requests)/sum(measured seconds), '
                    'not mean of per-run throughput. No confidence interval from three short repeats.',cells=cells)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-env', default='CONSISTENCY_DATABASE_URL')
    parser.add_argument('--output', default='docs/evidence/consistency-costs.json')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--profiles', nargs='+', choices=PROFILES, default=list(PROFILES))
    parser.add_argument('--workers', nargs='+', type=int, default=[1,4,8])
    args=parser.parse_args()
    url=os.environ[args.database_url_env]
    parsed=urlsplit(url)
    if parsed.hostname not in ('localhost','127.0.0.1','::1') or not parsed.path.startswith('/recheck_consistency'):
        raise SystemExit('Use dedicated recheck_consistency* database on loopback only')
    if not 1 <= args.repeats <= 5 or any(w not in (1,2,4,8) for w in args.workers):
        raise SystemExit('Workload bounds exceeded')
    application_name='recheck_consistency_'+uuid.uuid4().hex[:8]
    url += ('&' if '?' in url else '?')+'application_name='+application_name
    store=MeasuredStore(Settings(database_url=url))
    lab=AuditedEvidenceStore(store)
    try:
        with store.engine.connect() as db:
            version=db.exec_driver_sql('select version()').scalar_one()
        # Populate the existing four-connection pool outside measured work.
        connections=[store.engine.connect() for _ in range(4)]
        for connection in connections:
            connection.close()
        # Warm fixture and real execute paths separately; no warmup sample retained.
        warm=fixture(lab,'small')
        lab.execute(warm['sid'],warm['rid'],Execute(idempotency_key='warmup'))
        clean(lab,warm['sid'])
        cap_probe=probe_caps(lab)
        runs=[]
        combinations=[dict(sharing=s,workers=w,edit_every=e,profile=p) for s in ('shared','distinct')
            for w in args.workers for e in (0,4,2) for p in args.profiles]
        for repeat in range(args.repeats):
            order=combinations[repeat:]+combinations[:repeat]
            for parameters in order:
                run=run_cell(lab,**parameters,repeat=repeat,application_name=application_name)
                runs.append(run)
                print(json.dumps(dict(**parameters,repeat=repeat,**run['summary'],
                    reconciled=run['reconciliation']['passed'])),flush=True)
        paths=['scripts/benchmark_consistency_costs.py','backend/recheck/store.py','backend/recheck/evidence.py']
        report=dict(schema_version=1,measured_at=datetime.now(timezone.utc).isoformat(),
            cap_probe=cap_probe,
            environment=dict(python=platform.python_version(),platform=platform.platform(),cpu_count=os.cpu_count(),
                database_version=version), repeats=args.repeats, profiles=PROFILES,
            scope='Bounded direct SQL evidence execution; local synthetic state, not HTTP or CPU model serving.',
            timing='Thread pool object created before timer; lazy worker startup included. Request latency includes executor queue. '
                'Four synchronized waves; next wave waits for all previous operations. '
                'Fixture creation, warmup, final SQL inspection and cleanup excluded. Audit and 5ms server polling included. '
                'All execute outcomes included in latency denominator; nearest-rank percentiles.',
            lock_measurement='row_acquisition includes pool checkout, SELECT FOR UPDATE execution and lock wait, '
                'not pure lock wait. pg_stat_activity Lock samples observe waits at 5ms intervals, may miss short waits.',
            supported_caps=dict(receipts=40,actions=40,reports=20,event_history=20,source_text_characters=600,
                receipt_ttl_seconds=120,pool_connections=4,pool_timeout_ms=300,lock_timeout_ms=100,statement_timeout_ms=150),
            source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},runs=runs)
        save_report(report,Path(args.output))
        summary_path=Path(args.output).with_name(Path(args.output).stem+'-summary.json')
        summary_path.write_text(json.dumps(matrix_summary(report),ensure_ascii=False,indent=2)+'\n')
    finally:
        store.engine.dispose()

if __name__=='__main__':
    main()
