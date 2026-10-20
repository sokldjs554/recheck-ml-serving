#!/usr/bin/env python3
"""Warm sequential ASGI + real SQLite overhead; not service capacity or SLA.

Run the same script with --backend pointing to each revision's backend directory.
Thread environment and hardware must match; retain both invocation orders.
"""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.backend.resolve()))
    import httpx
    from recheck.config import Settings
    from recheck.api import create_app
    from recheck.worker import create_app as create_worker

    async def measure():
        rounds = []
        with tempfile.TemporaryDirectory() as temp:
            for round_id in range(3):
                settings = Settings(database_url=f'sqlite:///{temp}/{round_id}.db', deadline_ms=2000)
                worker = create_worker(settings)
                model = httpx.AsyncClient(transport=httpx.ASGITransport(app=worker), base_url='http://worker')
                app = create_app(settings, model_client=model)
                async with model, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://api') as client:
                    sid = (await client.post('/api/sessions')).json()['session_id']
                    samples = {'health': [], 'decision': []}
                    for index in range(35):
                        for kind in samples:
                            started = time.perf_counter()
                            if kind == 'health':
                                response = await client.get('/health')
                            else:
                                response = await client.post(f'/api/sessions/{sid}/decisions', json=dict(
                                    amount=150000, recipient='demo-recipient', idempotency_key=str(index),
                                    delay_ms=0, fault='none', protected=True))
                            elapsed = (time.perf_counter() - started) * 1000
                            assert response.status_code == 200, response.text
                            if kind == 'decision':
                                assert response.json()['status'] == 'clear'
                            if index >= 5:
                                samples[kind].append(elapsed)
                    saved = (await client.get(f'/api/sessions/{sid}/decisions')).json()['receipts']
                    assert len(saved) == 35 and len({row['id'] for row in saved}) == 35
                    rounds.append({'samples_ms': samples, 'stored': len(saved), 'model_completed': worker.state.completed})
                app.state.store.engine.dispose()
        result = {
            'scope': 'local sequential warm ASGI + real SQLite, lightweight model; not throughput or network latency',
            'warmups_per_round': 5, 'measured_per_round': 30, 'rounds': rounds,
        }
        result['summary'] = {}
        for kind in ('health', 'decision'):
            values = sorted(value for row in rounds for value in row['samples_ms'][kind])
            result['summary'][kind] = {'median_ms': statistics.median(values), 'p95_ms': values[85]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')

    asyncio.run(measure())


if __name__ == '__main__':
    main()
