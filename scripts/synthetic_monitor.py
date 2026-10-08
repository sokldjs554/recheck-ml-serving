#!/usr/bin/env python3
"""A sampled correctness/latency probe of an owned RECHECK deployment.

One sample includes health, real inference, and stale-result rejection. Every
attempt is retained, including cold starts and failures. Scheduled samples are
not continuous availability observations and do not establish a production SLA.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import httpx


def summarize(rows: list[dict], target: float = .99, budget_ms: float = 5000) -> dict:
    if not 0 < target < 1 or budget_ms <= 0:
        raise ValueError('target must be between 0 and 1, and budget_ms positive')
    total = len(rows)
    good = sum(row.get('ok') is True and 0 <= row.get('duration_ms', float('inf')) <= budget_ms for row in rows)
    bad = total - good
    allowed = total * (1 - target)
    return {'total': total, 'good': good, 'bad': bad,
            'availability': good / total if total else None,
            'target': target, 'latency_budget_ms': budget_ms,
            'allowed_bad_samples': allowed,
            'budget_consumed_ratio': bad / allowed if total else None,
            'scope': 'sampled synthetic workflow, not continuous production uptime'}


async def probe(client: httpx.AsyncClient) -> dict:
    row = {'at': datetime.now(timezone.utc).isoformat(), 'ok': False, 'steps': []}
    started = time.perf_counter()
    step = 'health'
    try:
        health = await client.get('/health')
        health.raise_for_status()
        info = health.json()
        if not isinstance(info, dict) or any(info.get(k) != v for k,v in {'status':'ok','service':'recheck-api','mode':'live'}.items()):
            raise ValueError('unexpected health identity')
        row['steps'].append(step)
        step = 'session'
        session = await client.post('/api/sessions', json={})
        session.raise_for_status()
        prefix = '/api/sessions/' + session.json()['session_id']
        row['steps'].append(step)
        step = 'inference'
        result = await client.post(prefix + '/decisions', json={
            'amount': 150000, 'recipient': 'synthetic-monitor',
            'idempotency_key': str(uuid.uuid4()), 'protected': True,
            'delay_ms': 0, 'fault': 'none'})
        result.raise_for_status()
        receipt = result.json()
        if not isinstance(receipt, dict) or receipt.get('status') != 'clear' or not receipt.get('model_hash') or not receipt.get('trace_id'):
            raise ValueError('inference did not produce usable identified result')
        row['trace_id'] = receipt['trace_id']
        row['steps'].append(step)
        original_versions = {key: receipt[key] for key in ('feature_version', 'policy_version', 'model_version')}
        step = 'current_validation'
        validation_path = prefix + '/decisions/' + receipt['id'] + '/validate'
        current = await client.get(validation_path)
        current.raise_for_status()
        if current.json() != {'valid': True, 'reason': 'current', 'current_versions': original_versions}:
            raise ValueError('new receipt is not currently valid')
        row['steps'].append(step)
        step = 'mutation'
        changed = await client.post(prefix + '/mutations', json={'kind':'feature'})
        changed.raise_for_status()
        expected_versions = {**original_versions, 'feature_version': original_versions['feature_version'] + 1}
        if changed.json() != expected_versions:
            raise ValueError('mutation did not increment feature version')
        row['steps'].append(step)
        step = 'stale_rejection'
        checked = await client.get(validation_path)
        checked.raise_for_status()
        validation = checked.json()
        if validation != {'valid': False, 'reason': 'versions_changed', 'current_versions': expected_versions}:
            raise ValueError('stale result incorrectly accepted')
        row['steps'].append(step)
        row['ok'] = True
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        row['failed_step'] = step
        # Exclude URLs, credentials, body contents and user data from logs.
        row['error_type'] = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            row['http_status'] = exc.response.status_code
    row['duration_ms'] = round((time.perf_counter() - started) * 1000, 3)
    return row


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--budget-ms', type=float, default=5000)
    parser.add_argument('--target', type=float, default=.99)
    parser.add_argument('--output', type=Path, default=Path('work/operations/synthetic.jsonl'))
    parser.add_argument('--summary', type=Path, default=Path('work/operations/synthetic-summary.json'))
    args = parser.parse_args()
    if args.count < 1 or args.interval < 0 or args.timeout <= 0:
        parser.error('count >= 1, interval >= 0 and timeout > 0 required')
    summarize([], args.target, args.budget_ms)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    async with httpx.AsyncClient(base_url=args.base.rstrip('/'), timeout=args.timeout) as client:
        for i in range(args.count):
            row = await probe(client)
            rows.append(row)
            with args.output.open('a') as f:
                f.write(json.dumps(row) + '\n')
            print(json.dumps(row), flush=True)
            if i + 1 < args.count:
                await asyncio.sleep(args.interval)
    result = summarize(rows, args.target, args.budget_ms)
    result['window_start'] = rows[0]['at']
    result['window_end'] = datetime.now(timezone.utc).isoformat()
    result['interval_seconds'] = args.interval
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return 0 if result['bad'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
