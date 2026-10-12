#!/usr/bin/env python3
"""Continuous local HTTP -> CPU process pool -> PostgreSQL overload/recovery.

Requires a new, empty localhost database named fullpath_sustained_*. No public URL
option exists. Warmup, load, server drain and SQL reconciliation are distinct.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from benchmark_compute import percentile, port, resources
from benchmark_fullpath import ready

ROOT = Path(__file__).resolve().parents[1]
USEFUL = {'no_current_warning', 'risk_signal'}


def quantiles(values):
    return {name: percentile(values, p) for name, p in [('p50', .5), ('p95', .95), ('p99', .99)]}


def validate_database_url(value):
    url = make_url(value)
    if url.get_backend_name() != 'postgresql' or url.host not in {'127.0.0.1', 'localhost', '::1'} or not (url.database or '').startswith('fullpath_sustained_'):
        raise ValueError('requires dedicated localhost PostgreSQL database fullpath_sustained_*')
    return url


def category(row):
    status = row.get('http_status')
    if status == 200:
        if row.get('response', {}).get('reason') in USEFUL:
            return 'useful_on_time' if row['good'] else 'useful_late'
        return 'deferred'
    if status == 429:
        return 'refused'
    if status == 504:
        return 'server_timeout'
    if 'Timeout' in row.get('error', ''):
        return 'client_timeout'
    return 'error'


def summarize_phase(records, phase):
    start, duration = phase['start_seconds'], phase['duration_seconds']
    end = start + duration
    cohort = [r for r in records if r['phase'] == phase['index']]
    observed = max(duration, max((r['completed_seconds']-start for r in cohort), default=0))
    good = sum(r['good'] for r in cohort)
    window_completed = [r for r in records if start <= r['completed_seconds'] < end]
    return {**phase, 'attempted': len(cohort), 'good': good, 'good_fraction': good/len(cohort) if cohort else None,
            'cohort_observed_seconds': observed,
            'cohort_rates_rps': dict(sent=len(cohort)/observed, completed=len(cohort)/observed, good=good/observed),
            'wall_window_rates_rps': dict(sent=sum(start <= r['sent_seconds'] < end for r in records)/duration,
                                          completed=len(window_completed)/duration, good=sum(r['good'] for r in window_completed)/duration),
            'categories': dict(Counter(category(r) for r in cohort)),
            'http_outcomes': dict(Counter(str(r.get('http_status', r.get('error'))) for r in cohort)),
            'reasons': dict(Counter(str(r.get('response', {}).get('reason', r.get('response', {}).get('detail', r.get('error')))) for r in cohort)),
            'scheduled_latency_ms': quantiles([(r['completed_seconds']-r['due_seconds'])*1000 for r in cohort]),
            'sent_latency_ms': quantiles([(r['completed_seconds']-r['sent_seconds'])*1000 for r in cohort]),
            'useful_scheduled_latency_ms': quantiles([(r['completed_seconds']-r['due_seconds'])*1000 for r in cohort if r.get('response', {}).get('reason') in USEFUL]),
            'generator_lag_ms': quantiles([(r['sent_seconds']-r['due_seconds'])*1000 for r in cohort])}


def reconcile(records, sql_rows):
    attempts = {(r['session_id'],r['idempotency_key']):r for r in records}
    counts = Counter((r['session_id'],r['idempotency_key']) for r in sql_rows)
    saved = {(r['session_id'],r['idempotency_key']):r['payload'] for r in sql_rows}
    result = dict(attempts=len(records), sql_rows=len(sql_rows), delivered_equal_sql=0,
                  missing_delivered_keys=[], mismatched_delivered_keys=[], committed_without_200_keys=[],
                  pending_sql_keys=[], unexpected_sql_keys=[], duplicate_sql_keys=[], absent_without_200_keys=[])
    for key,row in attempts.items():
        if row.get('http_status') == 200:
            if key not in saved:
                result['missing_delivered_keys'].append(list(key))
            elif saved[key] != row['response']:
                result['mismatched_delivered_keys'].append(list(key))
            else:
                result['delivered_equal_sql'] += 1
        elif key in saved and saved[key] is not None:
            result['committed_without_200_keys'].append(list(key))
        elif key not in saved:
            result['absent_without_200_keys'].append(list(key))
    for key,payload in saved.items():
        if key not in attempts:
            result['unexpected_sql_keys'].append(list(key))
        if payload is None:
            result['pending_sql_keys'].append(list(key))
        if counts[key] > 1:
            result['duplicate_sql_keys'].append(list(key))
    result['passed'] = not any(result[k] for k in ('missing_delivered_keys','mismatched_delivered_keys','pending_sql_keys','unexpected_sql_keys','duplicate_sql_keys')) and len(attempts) == len(records)
    return result


def recovery(records, samples, phase, latency_limit_ms):
    start, duration = phase['start_seconds'], phase['duration_seconds']
    windows, streak = [], 0
    result = dict(stabilized_window_start_seconds=None, confirmed_after_seconds=None, windows=windows,
                  latency_limit_ms=latency_limit_ms, definition='Two consecutive complete 5s arrival windows: >=99% good, >=95% target sent, p95 scheduled latency <= limit, every sampled worker queue <=1; no probe errors.')
    for offset in range(0, int(duration)-4, 5):
        lo, hi = start+offset, start+offset+5
        rows = [r for r in records if lo <= r['due_seconds'] < hi]
        probes = [s for s in samples if lo <= s['offset_seconds'] < hi]
        p95 = percentile([(r['completed_seconds']-r['due_seconds'])*1000 for r in rows], .95)
        good_fraction = sum(r['good'] for r in rows)/len(rows) if rows else 0
        sent = sum(lo <= r['sent_seconds'] < hi for r in records)
        queue_ok = bool(probes) and all('probe_error' not in s and 'worker' in s and s['worker']['admitted']-s['worker']['active'] <= 1 for s in probes)
        passed = good_fraction >= .99 and sent >= phase['target_rps']*5*.95 and p95 is not None and p95 <= latency_limit_ms and queue_ok
        windows.append(dict(start_seconds=offset,good_fraction=good_fraction,sent=sent,p95_ms=p95,queue_ok=queue_ok,passed=passed))
        streak = streak+1 if passed else 0
        if streak >= 2 and result['confirmed_after_seconds'] is None:
            result.update(stabilized_window_start_seconds=offset-5,confirmed_after_seconds=offset+5)
    return result


async def run_schedule(client, observer, base, worker_base, sessions, processes, phases, deadline, sample_interval, partial=None):
    records, samples = [], []
    partial = {} if partial is None else partial
    partial.update(records=records,resource_samples=samples,interrupted=True)
    started = time.monotonic()
    stop = asyncio.Event()
    initial = resources([p.pid for p in processes])

    async def sample():
        while not stop.is_set():
            row = dict(offset_seconds=time.monotonic()-started, **resources([p.pid for p in processes]))
            probe_started = time.monotonic()
            try:
                response = await observer.get(worker_base+'/health', timeout=1)
                response.raise_for_status()
                row['worker'] = response.json()
                metrics = await observer.get(base+'/metrics', timeout=1)
                metrics.raise_for_status()
                row['api_http_inflight'] = next(float(line.split()[-1]) for line in metrics.text.splitlines() if line.startswith('recheck_http_inflight{'))
            except (httpx.HTTPError, ValueError, StopIteration) as exc:
                row['probe_error'] = type(exc).__name__
            row['probe_latency_ms'] = (time.monotonic()-probe_started)*1000
            samples.append(row)
            try:
                await asyncio.wait_for(stop.wait(), sample_interval)
            except TimeoutError:
                pass

    async def attempt(index, phase, due):
        sent = time.monotonic()-started
        sid = sessions[index % len(sessions)]
        row = dict(index=index,phase=phase['index'],due_seconds=due,sent_seconds=sent,
                   session_id=sid,idempotency_key=str(uuid.uuid4()))
        try:
            response = await client.post(base+f'/api/sessions/{sid}/decisions',json={'idempotency_key':row['idempotency_key']},timeout=5)
            row['http_status'] = response.status_code
            row['response'] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            row['error'] = type(exc).__name__
        row['completed_seconds'] = time.monotonic()-started
        row['good'] = row.get('http_status') == 200 and row.get('response',{}).get('reason') in USEFUL and (row['completed_seconds']-due)*1000 <= deadline
        records.append(row)

    task = asyncio.create_task(sample())
    pending, index = set(), 0
    try:
        for phase in phases:
            print(json.dumps(dict(event='phase',**phase)),flush=True)
            for i in range(int(phase['target_rps']*phase['duration_seconds'])):
                due = phase['start_seconds']+i/phase['target_rps']
                await asyncio.sleep(max(0, started+due-time.monotonic()))
                request = asyncio.create_task(attempt(index,phase,due))
                pending.add(request)
                request.add_done_callback(pending.discard)
                index += 1
        end = phases[-1]['start_seconds']+phases[-1]['duration_seconds']
        await asyncio.sleep(max(0,started+end-time.monotonic()))
        if pending:
            await asyncio.gather(*pending)
        response_drain = time.monotonic()-started
        until = time.monotonic()+10
        while True:
            health = (await observer.get(worker_base+'/health')).json()
            if health['admitted'] == 0:
                break
            if time.monotonic() > until:
                raise TimeoutError('worker drain')
            await asyncio.sleep(.05)
        final = resources([p.pid for p in processes])
        partial.update(records=sorted(records,key=lambda r:r['index']),resource_samples=samples,interrupted=False,
                    response_drain_seconds=response_drain,worker_drain_seconds=time.monotonic()-started,
                    cpu_seconds=final['cpu_seconds']-initial['cpu_seconds'], initial_resources=initial,final_resources=final,final_worker=health)
        return partial
    finally:
        stop.set()
        await task


async def main(args):
    db_url = os.environ[args.database_url_env]
    url = validate_database_url(db_url)
    engine = create_engine(db_url)
    if inspect(engine).get_table_names():
        raise ValueError('database must be new and empty; existing tables found')
    work = ROOT/'work/fullpath-sustained'
    work.mkdir(parents=True,exist_ok=True)
    worker_port,api_port = port(),port()
    base,worker_base = f'http://127.0.0.1:{api_port}',f'http://127.0.0.1:{worker_port}'
    total_duration = args.phase_seconds*3*args.cycles
    ttl = math.ceil(total_duration+args.warmup_seconds+300)
    env = dict(os.environ,DATABASE_URL=db_url,MODEL_SERVICE_URL=worker_base,PYTHONPATH=str(ROOT/'backend'),
               RECHECK_WORKLOAD='cpu-ensemble',RECHECK_EXECUTION_MODE='process',RECHECK_WORKER_CONCURRENCY='2',
               RECHECK_WORKER_QUEUE='4',RECHECK_GATEWAY_CONCURRENCY='8',RECHECK_GATEWAY_QUEUE='8',
               RECHECK_DEADLINE_MS=str(args.deadline),RECHECK_FEATURE_TTL_MS=str(ttl*1000),
               RECHECK_SESSION_TTL_SECONDS=str(ttl),RECHECK_MAX_RECEIPTS='1000',RECHECK_MAX_SESSIONS='1000',RECHECK_OBSERVE='0',
               OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    for name in ('OTEL_EXPORTER_OTLP_ENDPOINT','OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'):
        env.pop(name,None)
    report = dict(schema_version=1,measured_at=datetime.now(timezone.utc).isoformat(),
        boundary='real HTTP API -> HTTP CPU model/process pool -> local PostgreSQL; /decisions only, not consultation evidence execution',
        environment='shared local Linux host; no public load; measurement coordinated against other agents',
        platform=platform.platform(),cpu_affinity=sorted(os.sched_getaffinity(0)),database_name=url.database,
        command=sys.argv, settings=dict(deadline_ms=args.deadline,worker_processes=2,worker_queue=4,gateway_concurrency=8,gateway_queue=8,
        database_pool_size=4,sessions=32,max_receipts_per_session=1000,session_ttl_seconds=ttl,feature_ttl_ms=ttl*1000,sample_interval_seconds=args.sample_interval),
        accounting='good requires HTTP200 useful reason and scheduled-arrival-to-response <= deadline; every dispatched attempt retained; wall windows count actual send/completion times; cohort denominator includes response tail',
        resource_scope='owned API/model process trees only; PostgreSQL and generator excluded; summed RSS double-counts shared pages; API inflight includes all non-metrics requests and is not gateway queue',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'backend/recheck').glob('*.py')),Path(__file__)]},validation_passed=False)
    processes,logs = [],[]
    def launch(module,selected_port):
        log = (work/(module.replace('.','-')+'.log')).open('w')
        logs.append(log)
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn',module+':app','--host','127.0.0.1','--port',str(selected_port),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=log))
    try:
        launch('recheck.worker',worker_port)
        async with httpx.AsyncClient(trust_env=False,limits=httpx.Limits(max_connections=256,max_keepalive_connections=64)) as client, httpx.AsyncClient(trust_env=False,timeout=3) as observer:
            await ready(observer,worker_base,processes)
            launch('recheck.api',api_port)
            await ready(observer,base,processes)
            report['owned_pids'] = [p.pid for p in processes]
            report['model_hashes'] = (await observer.get(worker_base+'/health')).json()['models']
            sessions = []
            for _ in range(32):
                response = await client.post(base+'/api/sessions')
                response.raise_for_status()
                sessions.append(response.json()['session_id'])
            warmup_phase = dict(index=0,name='warmup',start_seconds=0,duration_seconds=args.warmup_seconds,target_rps=args.normal_rps)
            report['warmup'] = await run_schedule(client,observer,base,worker_base,sessions,processes,[warmup_phase],args.deadline,args.sample_interval,partial=report.setdefault('warmup',{}))
            report['warmup']['summary'] = summarize_phase(report['warmup']['records'],warmup_phase)
            phases = []
            for cycle in range(1,args.cycles+1):
                for name,rate in [('normal',args.normal_rps),('overload',args.overload_rps),('recovery',args.normal_rps)]:
                    phases.append(dict(index=len(phases),cycle=cycle,name=name,start_seconds=len(phases)*args.phase_seconds,duration_seconds=args.phase_seconds,target_rps=rate))
            report['measurement'] = await run_schedule(client,observer,base,worker_base,sessions,processes,phases,args.deadline,args.sample_interval,partial=report.setdefault('measurement',{}))
            measurement = report['measurement']
            report['phases'] = [summarize_phase(measurement['records'],p) for p in phases]
            baseline_p95 = report['phases'][0]['scheduled_latency_ms']['p95']
            limit = min(args.deadline,max(150,baseline_p95*1.5))
            for phase in report['phases']:
                probes = [s for s in measurement['resource_samples'] if phase['start_seconds'] <= s['offset_seconds'] <= phase['start_seconds']+phase['duration_seconds']]
                phase['resources'] = dict(samples=len(probes),peak_rss_bytes=max((s['rss_bytes'] for s in probes),default=0),
                    peak_worker_queue=max((s.get('worker',{}).get('admitted',0)-s.get('worker',{}).get('active',0) for s in probes),default=0),
                    cpu_seconds_between_samples=probes[-1]['cpu_seconds']-probes[0]['cpu_seconds'] if probes else None,
                    probe_errors=sum('probe_error' in s for s in probes))
                if phase['name'] == 'recovery':
                    phase['recovery'] = recovery(measurement['records'],measurement['resource_samples'],phase,limit)
            # No automatic retries: reconcile uncertain non-200 outcomes without changing SQL.
            await asyncio.sleep(1)
            with engine.connect() as db:
                sql_rows = [dict(r) for r in db.execute(text('select session_id,idempotency_key,payload from decisions')).mappings()]
                report['database_version'] = db.execute(text('select version()')).scalar()
                report['retention'] = dict(session_rows=db.execute(text('select count(*) from demo_sessions')).scalar(),
                    max_receipts_in_any_session=db.execute(text('select max(n) from (select count(*) n from decisions group by session_id) t')).scalar(),
                    oldest_session_age_seconds=db.execute(text('select extract(epoch from now())-min(created_at) from demo_sessions')).scalar())
            all_records = report['warmup']['records']+measurement['records']
            report['reconciliation'] = reconcile(all_records,sql_rows)
            # Store every final SQL row (including non-200 commits), not only delivered rows.
            report['sql_rows'] = sql_rows
            expected = sum(int(p['target_rps']*p['duration_seconds']) for p in phases)
            report['validation_passed'] = report['reconciliation']['passed'] and len(measurement['records']) == expected and measurement['final_worker']['admitted'] == 0
            report['cost'] = dict(cpu_ms_per_good_response=measurement['cpu_seconds']*1000/sum(r['good'] for r in measurement['records']),
                mean_owned_cpu_cores=measurement['cpu_seconds']/measurement['worker_drain_seconds'],
                peak_rss_bytes=max(s['rss_bytes'] for s in measurement['resource_samples']),paid_resources_added=False)
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        for log in logs:
            log.close()
        engine.dispose()
        dest = Path(args.output)
        dest.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(dest,'wt',encoding='utf-8') as file:
            json.dump(report,file,separators=(',',':'))
        summary = {k:v for k,v in report.items() if k not in {'sql_rows','measurement','warmup'}}
        for name in ('warmup','measurement'):
            if name in report:
                summary[name] = {k:v for k,v in report[name].items() if k not in {'records','resource_samples'}}
                summary[name]['attempts'] = len(report[name]['records'])
                summary[name]['resource_samples_count'] = len(report[name]['resource_samples'])
        if 'reconciliation' in summary:
            summary['reconciliation'] = {k:(len(v) if isinstance(v,list) else v) for k,v in summary['reconciliation'].items()}
        summary['raw_file'] = dest.name
        summary['raw_sha256'] = hashlib.sha256(dest.read_bytes()).hexdigest()
        dest.with_name(dest.name.replace('.json.gz','-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(dict(event='finished',validation_passed=report['validation_passed'],output=str(dest))),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-env',required=True)
    parser.add_argument('--phase-seconds',type=float,default=30)
    parser.add_argument('--cycles',type=int,default=2)
    parser.add_argument('--normal-rps',type=int,default=10)
    parser.add_argument('--overload-rps',type=int,default=120)
    parser.add_argument('--warmup-seconds',type=float,default=5)
    parser.add_argument('--deadline',type=int,default=300)
    parser.add_argument('--sample-interval',type=float,default=.5)
    parser.add_argument('--output',default='docs/evidence/fullpath-sustained.json.gz')
    args = parser.parse_args()
    attempts = args.cycles*args.phase_seconds*(2*args.normal_rps+args.overload_rps)+args.warmup_seconds*args.normal_rps
    if not (0 < args.phase_seconds <= 60 and 1 <= args.cycles <= 3 and 1 <= args.normal_rps < args.overload_rps <= 200 and 0 < args.warmup_seconds <= 30 and 1 <= args.deadline <= 2000 and .1 <= args.sample_interval <= 2 and attempts < 30000):
        parser.error('positive bounded schedule (<=30,000 attempts), rates, deadline and sampling required')
    asyncio.run(main(args))
