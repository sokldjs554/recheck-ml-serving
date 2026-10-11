#!/usr/bin/env python3
"""Open-loop HTTP API -> CPU process pool -> PostgreSQL; retain every attempt.

Use a disposable PostgreSQL database. Never accepts the production URL on CLI.
No injected delays in load cases. Failure/disconnect checks are separate.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import httpx
from sqlalchemy import create_engine, text
from benchmark_compute import percentile, port, resources

ROOT = Path(__file__).resolve().parents[1]


async def ready(client, base, processes):
    until = time.monotonic() + 60
    while time.monotonic() < until:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('owned process exited; inspect work/fullpath logs')
        try:
            if (await client.get(base + '/ready', timeout=2)).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(.1)
    raise TimeoutError('readiness')


async def measure(client, base, sessions, processes, rate, duration, deadline, repeat):
    records = []
    start = time.monotonic()
    initial = resources([p.pid for p in processes])
    samples = []
    stop = asyncio.Event()

    async def sample():
        while not stop.is_set():
            samples.append(resources([p.pid for p in processes]))
            try:
                await asyncio.wait_for(stop.wait(), .1)
            except TimeoutError:
                pass

    async def attempt(i):
        due = start + i / rate
        await asyncio.sleep(max(0, due - time.monotonic()))
        sent = time.monotonic()
        sid = sessions[i % len(sessions)]
        key = str(uuid.uuid4())
        row = dict(index=i, session_id=sid, idempotency_key=key, scheduling_lag_ms=(sent-due)*1000)
        try:
            response = await client.post(base + f'/api/sessions/{sid}/decisions', json=dict(idempotency_key=key), timeout=5)
            row.update(http_status=response.status_code, response=response.json())
        except (httpx.HTTPError, ValueError) as exc:
            row['error'] = type(exc).__name__
        row['scheduled_latency_ms'] = (time.monotonic()-due)*1000
        row['latency_ms'] = (time.monotonic()-sent)*1000
        row['good'] = row.get('http_status') == 200 and row.get('response', {}).get('reason') in ('no_current_warning', 'risk_signal') and row['scheduled_latency_ms'] <= deadline
        records.append(row)

    task = asyncio.create_task(sample())
    await asyncio.gather(*(attempt(i) for i in range(int(rate*duration))))
    stop.set()
    await task
    elapsed = max(duration, time.monotonic()-start)
    final = resources([p.pid for p in processes])
    return dict(rate_rps=rate, repeat=repeat, duration_seconds=duration, observed_seconds=elapsed,
                requested=len(records), good=sum(r['good'] for r in records),
                goodput_rps=sum(r['good'] for r in records)/elapsed,
                outcomes=dict(Counter(str(r.get('http_status', r.get('error'))) for r in records)),
                reasons=dict(Counter(r.get('response', {}).get('reason', r.get('response', {}).get('detail', r.get('error', 'unknown'))) for r in records)),
                p95_ms=percentile([r['scheduled_latency_ms'] for r in records], .95),
                cpu_seconds=final['cpu_seconds']-initial['cpu_seconds'],
                peak_api_model_rss_bytes=max(s['rss_bytes'] for s in samples),
                records=sorted(records, key=lambda r:r['index']))


async def main(args):
    db_url = os.environ[args.database_url_env]
    if not db_url.startswith('postgresql'):
        raise ValueError('requires PostgreSQL')
    engine = create_engine(db_url)
    work = ROOT/'work/fullpath'
    work.mkdir(parents=True, exist_ok=True)
    worker_port, api_port = port(), port()
    base = f'http://127.0.0.1:{api_port}'
    worker_base = f'http://127.0.0.1:{worker_port}'
    env = dict(os.environ, DATABASE_URL=db_url, MODEL_SERVICE_URL=worker_base,
               PYTHONPATH=str(ROOT/'backend'), RECHECK_WORKLOAD='cpu-ensemble',
               RECHECK_EXECUTION_MODE='process', RECHECK_WORKER_CONCURRENCY='2',
               RECHECK_WORKER_QUEUE='4', RECHECK_GATEWAY_CONCURRENCY='8', RECHECK_GATEWAY_QUEUE='8',
               RECHECK_DEADLINE_MS=str(args.deadline), RECHECK_FEATURE_TTL_MS='300000',
               RECHECK_MAX_RECEIPTS='1000', RECHECK_OBSERVE='0',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for name in ('OTEL_EXPORTER_OTLP_ENDPOINT', 'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'):
        env.pop(name, None)
    processes, logs = [], []
    def launch(module, selected_port):
        log = (work/(module.replace('.', '-') + '.log')).open('a')
        logs.append(log)
        p = subprocess.Popen([sys.executable, '-m', 'uvicorn', module+':app', '--host', '127.0.0.1', '--port', str(selected_port), '--no-access-log'], cwd=ROOT, env=env, stdout=log, stderr=log)
        processes.append(p)
        return p
    report = dict(measured_at=datetime.now(timezone.utc).isoformat(),
                  boundary='real HTTP API -> HTTP CPU model/process pool -> PostgreSQL transactions',
                  environment='single shared local Linux host; PostgreSQL Docker container; not public Render capacity',
                  deadline_ms=args.deadline, worker_processes=2, database_pool_size=4,
                  resource_scope='API/model process trees only; summed RSS can double-count shared pages; DB resources excluded',
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/recheck').glob('*.py')},
                  cases=[], checks={})
    try:
        launch('recheck.worker', worker_port)
        async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=100), timeout=10) as client:
            await ready(client, worker_base, processes)
            api_process = launch('recheck.api', api_port)
            await ready(client, base, processes)
            with engine.connect() as db:
                report['database_version'] = db.execute(text('select version()')).scalar()
            sessions = []
            for _ in range(32):
                response = await client.post(base+'/api/sessions')
                response.raise_for_status()
                sessions.append(response.json()['session_id'])
            report['model_hashes'] = (await client.get(worker_base+'/health')).json()['models']
            for rate in args.rates:
                for repeat in range(1, args.repeats+1):
                    case = await measure(client, base, sessions, processes, rate, args.duration, args.deadline, repeat)
                    report['cases'].append(case)
                    print(json.dumps({k:v for k,v in case.items() if k != 'records'}), flush=True)
            # Client disconnect does not imply ASGI cancellation: let admitted work
            # finish, then retry the exact key and verify the single SQL record.
            sid = sessions[0]
            path = base+f'/api/sessions/{sid}/decisions'
            for fault in ('unavailable', 'timeout'):
                response = await client.post(path, json={'idempotency_key':str(uuid.uuid4()),'fault':fault})
                assert response.status_code == 200 and response.json()['status'] != 'clear', response.text
                report['checks'][fault] = response.json()['reason']
            key = str(uuid.uuid4())
            payload = {'idempotency_key':key, 'delay_ms':150}
            try:
                await client.post(path, json=payload, timeout=.025)
                raise AssertionError('expected client disconnect timeout')
            except httpx.TimeoutException:
                pass
            await asyncio.sleep(.7)
            replay = await client.post(path, json=payload)
            replay.raise_for_status()
            original = replay.json()
            assert original['id']
            with engine.connect() as db:
                count = db.execute(text('select count(*) from decisions where session_id=:sid and idempotency_key=:key'),dict(sid=sid,key=key)).scalar()
            assert count == 1
            report['checks']['disconnect_retry_single_sql_row'] = True
            api_process.terminate()
            api_process.wait(timeout=10)
            processes.remove(api_process)
            launch('recheck.api', api_port)
            await ready(client, base, processes)
            after = await client.post(path, json=payload)
            assert after.status_code == 200 and after.json() == original
            report['checks']['api_restart_immutable_replay'] = True
            conflict = await client.post(path, json={**payload,'amount':150001})
            assert conflict.status_code == 409
            report['checks']['conflicting_replay_rejected'] = True
            delivered = [r for c in report['cases'] for r in c['records'] if r.get('http_status') == 200]
            with engine.connect() as db:
                for row in delivered:
                    saved = db.execute(text('select payload from decisions where id=:id'), {'id':row['response']['id']}).scalar()
                    assert saved == row['response']
                duplicates = db.execute(text('select count(*) from (select session_id,idempotency_key from decisions group by session_id,idempotency_key having count(*) > 1) d')).scalar()
            assert duplicates == 0
            report['checks']['all_delivered_receipts_equal_sql'] = len(delivered)
            report['checks']['duplicate_rows'] = duplicates
            report['validation_passed'] = True
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
        for log in logs:
            log.close()
        engine.dispose()
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-env', required=True)
    parser.add_argument('--rates', nargs='+', type=int, default=[5,15,30])
    parser.add_argument('--duration', type=float, default=5)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--deadline', type=int, default=500)
    parser.add_argument('--output', default='docs/evidence/fullpath-load.json')
    args = parser.parse_args()
    if not 1 <= args.deadline <= 2000 or args.duration <= 0 or args.repeats < 1 or any(r <= 0 or r*args.duration > 16000 for r in args.rates):
        parser.error('positive bounded rates/duration/repeats and deadline 1..2000 required')
    asyncio.run(main(args))
