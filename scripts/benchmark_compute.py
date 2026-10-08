#!/usr/bin/env python3
"""Open-loop, real-HTTP CPU experiment. No injected model delays; keeps every outcome."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import importlib.metadata
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * p))] if values else None


def resources(pids):
    """Linux process-tree CPU and summed RSS; shared pages may be counted twice."""
    rows = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            rows[int(path.parent.name)] = (int(fields[1]), (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK'), int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
        except (OSError, ValueError, IndexError):
            pass
    owned = set(pids)
    while True:
        children = {pid for pid, (ppid, _, _) in rows.items() if ppid in owned}
        if children <= owned:
            break
        owned |= children
    return dict(cpu_seconds=sum(rows[p][1] for p in owned if p in rows),
                rss_bytes=sum(rows[p][2] for p in owned if p in rows), processes=len(owned))


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def run_case(client, urls, processes, rate, duration, deadline, repeat):
    records, health, samples = [], [], []
    count = int(rate * duration)
    started = time.monotonic()
    baseline = resources([p.pid for p in processes])
    stop = asyncio.Event()

    async def probe():
        while not stop.is_set():
            for url in urls:
                start = time.monotonic()
                try:
                    response = await client.get(url + '/health', timeout=1)
                    health.append(dict(latency_ms=1000 * (time.monotonic() - start), status=response.status_code))
                except httpx.HTTPError as exc:
                    health.append(dict(latency_ms=1000 * (time.monotonic() - start), error=type(exc).__name__))
            samples.append(resources([p.pid for p in processes]))
            try:
                await asyncio.wait_for(stop.wait(), 0.1)
            except TimeoutError:
                pass

    async def request(index):
        scheduled = started + index / rate
        await asyncio.sleep(max(0, scheduled - time.monotonic()))
        sent = time.monotonic()
        record = dict(index=index, replica=index % len(urls), scheduled_offset_ms=1000 * index / rate,
                      scheduling_lag_ms=1000 * (sent - scheduled))
        try:
            response = await client.post(urls[index % len(urls)] + '/infer', json=dict(
                features=[0.4, 1, 0, 0.3], model_version='risk-v1',
                delay_ms=0, fault='none', deadline_ms=deadline), timeout=2)
            record.update(status=response.status_code, body=response.json())
        except (httpx.HTTPError, ValueError) as exc:
            record.update(error=type(exc).__name__)
        record['latency_ms'] = 1000 * (time.monotonic() - sent)
        record['scheduled_latency_ms'] = 1000 * (time.monotonic() - scheduled)
        record['good'] = record.get('status') == 200 and record['scheduled_latency_ms'] <= deadline
        records.append(record)

    probe_task = asyncio.create_task(probe())
    await asyncio.gather(*(request(i) for i in range(count)))
    drain_elapsed = time.monotonic() - started
    elapsed = max(duration, drain_elapsed)
    # Drain the actual occupied executor, then sample final CPU use.
    final_health = []
    for url in urls:
        while True:
            result = (await client.get(url + '/health', timeout=2)).json()
            if result['admitted'] == 0:
                final_health.append(result)
                break
            await asyncio.sleep(0.01)
    stop.set()
    await probe_task
    final = resources([p.pid for p in processes])
    latencies = [r['scheduled_latency_ms'] for r in records]
    successes = sum(r.get('status') == 200 for r in records)
    good = sum(r['good'] for r in records)
    statuses = Counter(str(r.get('status', r.get('error'))) for r in records)
    return dict(rate_rps=rate, repeat=repeat, duration_seconds=duration, observed_seconds=elapsed,
        response_drain_seconds=drain_elapsed, requested=count, outcomes=dict(statuses), success=successes, good=good,
        success_throughput_rps=successes / elapsed, goodput_rps=good / elapsed,
        good_fraction=good / count, reject_fraction=statuses['429'] / count,
        error_fraction=sum(r.get('status') not in (200, 429, 504) for r in records) / count,
        late_success_fraction=sum(r.get('status') == 200 and not r['good'] for r in records) / count,
        deadline_fraction=(statuses['504'] + sum(r.get('status') == 200 and not r['good'] for r in records)) / count,
        all_outcome_latency_ms={name: percentile(latencies, p) for name, p in [('p50', .5), ('p95', .95), ('p99', .99)]},
        health_latency_p95_ms=percentile([h['latency_ms'] for h in health], .95), health_errors=sum(h.get('status') != 200 for h in health),
        cpu_seconds=final['cpu_seconds'] - baseline['cpu_seconds'],
        peak_process_tree_rss_bytes=max([baseline['rss_bytes'], final['rss_bytes']] + [s['rss_bytes'] for s in samples]),
        final_health=final_health, health_probes=health, resource_samples=samples,
        records=sorted(records, key=lambda r: r['index']))


async def main(args):
    evidence = dict(timestamp=datetime.now(timezone.utc).isoformat(), boundary='direct model worker HTTP; excludes gateway/database',
        workload='cpu-ensemble: trained 128-tree ExtraTrees plus 4096 contributing uncertainty scenarios; no injected delay',
        platform=platform.platform(), python=sys.version, cpu_count=os.cpu_count(),
        packages={name: importlib.metadata.version(name) for name in ('scikit-learn', 'numpy', 'fastapi', 'uvicorn')},
        cpu_affinity=sorted(os.sched_getaffinity(0)), deadline_ms=args.deadline,
        resource_note='CPU seconds and summed RSS of owned uvicorn/process-pool trees; RSS can double-count shared pages; same host shared with other tasks',
        configurations=[])
    for mode in args.modes:
        for replicas in args.replicas:
            processes, logs, urls = [], [], []
            work = ROOT / 'work' / 'compute-benchmark'
            work.mkdir(parents=True, exist_ok=True)
            try:
                for replica in range(replicas):
                    selected_port = port()
                    urls.append(f'http://127.0.0.1:{selected_port}')
                    env = dict(os.environ, RECHECK_WORKLOAD='cpu-ensemble', RECHECK_EXECUTION_MODE=mode,
                        RECHECK_WORKER_CONCURRENCY='1', RECHECK_WORKER_QUEUE='2', RECHECK_DEADLINE_MS=str(args.deadline),
                        OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
                    for name in ('OTEL_EXPORTER_OTLP_ENDPOINT', 'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'):
                        env.pop(name, None)
                    log = (work / f'{mode}-{replicas}-{replica}.log').open('w')
                    logs.append(log)
                    processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'recheck.worker:app', '--host', '127.0.0.1', '--port', str(selected_port), '--no-access-log'], cwd=ROOT / 'backend', env=env, stdout=log, stderr=log))
                async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=200)) as client:
                    for url in urls:
                        until = time.monotonic() + 40
                        while True:
                            if any(p.poll() is not None for p in processes):
                                raise RuntimeError(f'worker exited; inspect {work}')
                            try:
                                if (await client.get(url + '/ready', timeout=.5)).status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                            if time.monotonic() > until:
                                raise TimeoutError('worker readiness')
                            await asyncio.sleep(.05)
                    identities = [(await client.get(url + '/health')).json()['models'] for url in urls]
                    assert all(identity == identities[0] for identity in identities)
                    cases = []
                    for rate in args.rates:
                        for repeat in range(args.repeats):
                            case = await run_case(client, urls, processes, rate, args.duration, args.deadline, repeat + 1)
                            cases.append(case)
                            print(json.dumps(dict(mode=mode, replicas=replicas, rate=rate, repeat=repeat + 1,
                                goodput=round(case['goodput_rps'], 2), p95=round(case['all_outcome_latency_ms']['p95'], 1),
                                outcomes=case['outcomes'])), flush=True)
                    evidence['configurations'].append(dict(execution_mode=mode, service_replicas=replicas,
                        process_pool_per_replica=1 if mode == 'process' else 0, concurrency_per_replica=1,
                        queue_per_replica=2, model_hashes=identities[0], cases=cases))
                    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                    Path(args.output).write_text(json.dumps(evidence, indent=2) + '\n')
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for log in logs:
                    log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modes', nargs='+', choices=['inline', 'process'], default=['inline', 'process'])
    parser.add_argument('--replicas', nargs='+', type=int, default=[1, 2])
    parser.add_argument('--rates', nargs='+', type=int, default=[10, 30, 60])
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--duration', type=float, default=3)
    parser.add_argument('--deadline', type=int, default=200)
    parser.add_argument('--output', default='docs/evidence/compute-load.json')
    asyncio.run(main(parser.parse_args()))
