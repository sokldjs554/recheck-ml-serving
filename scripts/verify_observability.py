#!/usr/bin/env python3
"""Exercise real local telemetry pipeline and alert recovery. Stops only this lab's model."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

import httpx


def now():
    return datetime.now(timezone.utc).isoformat()


def wait_until(probe, label, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            last = str(exc)
        time.sleep(1)
    raise AssertionError(f'{label} not observed within {timeout}s: {last}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='recheck-observe')
    parser.add_argument('--output', default='docs/evidence/observability-latest.json')
    args = parser.parse_args()
    started = now()
    evidence = {'started_at': started, 'environment': 'owned local Docker lab, one shared host',
                'project': args.project, 'versions': {'prometheus': '3.2.1', 'alertmanager': '0.28.1',
                'grafana': '11.6.0', 'collector': '0.123.0', 'jaeger': '1.66.0'}, 'checks': {}}
    compose = ['docker', 'compose', '-p', args.project, '-f', 'compose.observability.yaml']
    with httpx.Client(timeout=5, trust_env=False) as client:
        def get(url):
            response = client.get(url)
            response.raise_for_status()
            return response.json()

        def ready():
            return get('http://127.0.0.1:18100/ready')

        def targets():
            data = get('http://127.0.0.1:19090/api/v1/targets')['data']['activeTargets']
            return data if len(data) == 2 and all(x['health'] == 'up' for x in data) else None

        def alerts(status, name='RecheckTargetDown'):
            events = get('http://127.0.0.1:18090/events')
            return [event for event in events if event['received_at'] >= started and any(
                alert['labels']['alertname'] == name and alert['status'] == status
                for alert in event['payload'].get('alerts', []))]

        stopped = False
        try:
            wait_until(ready, 'API readiness')
            fingerprint = "import hashlib,json,pathlib; p=pathlib.Path('/app/backend/recheck'); print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.py')}))"
            evidence['runtime_backend_sha256'] = json.loads(subprocess.check_output(compose + ['exec', '-T', 'api', 'python', '-c', fingerprint], text=True))
            evidence['image_ids'] = json.loads(subprocess.check_output(compose + ['images', '--format', 'json'], text=True))
            evidence['checks']['scrape_targets'] = wait_until(targets, 'both Prometheus scrapes')
            evidence['checks']['grafana_health'] = wait_until(lambda: get('http://127.0.0.1:13000/api/health'), 'Grafana health')
            dashboard = wait_until(lambda: get('http://127.0.0.1:13000/api/dashboards/uid/recheck-operations')['dashboard'], 'Grafana provisioned dashboard')
            assert len(dashboard['panels']) >= 6
            evidence['checks']['grafana_dashboard'] = {'uid': dashboard['uid'], 'panels': len(dashboard['panels'])}
            session = client.post('http://127.0.0.1:18100/api/sessions').json()['session_id']
            response = client.post(f'http://127.0.0.1:18100/api/sessions/{session}/decisions', json={'idempotency_key': f'observe-{time.time_ns()}'})
            response.raise_for_status()
            receipt = response.json()
            assert receipt['status'] == 'clear', receipt
            trace_id = receipt['trace_id']
            def exported():
                records = get(f'http://127.0.0.1:16686/api/traces/{trace_id}')['data']
                if not records:
                    return None
                record = records[0]
                names = {p['serviceName'] for p in record['processes'].values()}
                spans = record['spans']
                if not {'recheck-api', 'recheck-worker'} <= names:
                    return None
                if not {'model.http', 'model.infer'} <= {s['operationName'] for s in spans}:
                    return None
                http = next(s for s in spans if s['operationName'] == 'model.http')
                worker = next(s for s in spans if s['operationName'] == 'model.infer')
                assert any(r['spanID'] == http['spanID'] for r in worker['references']), 'cross-service parent broken'
                return {'trace_id': trace_id, 'services': sorted(names), 'span_count': len(spans),
                        'client_span_id': http['spanID'], 'worker_parent': worker['references'],
                        'span_names': [s['operationName'] for s in spans]}
            evidence['checks']['exported_cross_service_trace'] = wait_until(exported, 'collector to Jaeger exported trace')
            for index in range(3):
                failed = client.post(f'http://127.0.0.1:18100/api/sessions/{session}/decisions', json={
                    'idempotency_key': f'fault-{time.time_ns()}', 'fault': 'unavailable'})
                assert failed.status_code == 200 and failed.json()['reason'] == 'model_unavailable'
                time.sleep(3)
            def outcome_query():
                data = client.get('http://127.0.0.1:19090/api/v1/query', params={
                    'query': 'sum by (service,outcome,reason)(recheck_business_outcomes_total)'}).json()['data']['result']
                return data if any(x['metric'].get('reason') == 'model_unavailable' for x in data) else None
            evidence['checks']['business_metrics'] = wait_until(outcome_query, 'degraded HTTP-200 outcomes scraped')
            evidence['checks']['business_alert_firing'] = wait_until(lambda: alerts('firing', 'RecheckDecisionFailures'), 'degraded decision firing webhook')
            subprocess.run(compose + ['stop', '-t', '3', 'model'], check=True)
            stopped = True
            evidence['checks']['alert_firing'] = wait_until(lambda: alerts('firing'), 'Alertmanager firing webhook')
            assert client.get('http://127.0.0.1:18100/live').status_code == 200
            assert client.get('http://127.0.0.1:18100/ready').status_code == 503
            evidence['checks']['dependency_failure_probes'] = {'live': 200, 'ready': 503}
            subprocess.run(compose + ['start', 'model'], check=True)
            stopped = False
            wait_until(ready, 'readiness recovery')
            evidence['checks']['alert_resolved'] = wait_until(lambda: alerts('resolved'), 'Alertmanager recovery webhook')
            evidence['checks']['business_alert_resolved'] = wait_until(lambda: alerts('resolved', 'RecheckDecisionFailures'), 'degraded decision recovery webhook')
            evidence['checks']['recovered_targets'] = wait_until(targets, 'scrape recovery')
            recovered_session = client.post('http://127.0.0.1:18100/api/sessions').json()['session_id']
            recovered = client.post(f'http://127.0.0.1:18100/api/sessions/{recovered_session}/decisions',
                                    json={'idempotency_key': f'recovered-{time.time_ns()}'}).json()
            assert recovered['status'] == 'clear', recovered
            assert recovered['model_version'] == 'risk-v1' and len(recovered['model_hash']) == 64
            assert len(recovered['trace_id']) == 32 and int(recovered['trace_id'], 16) > 0
            validation = get(f"http://127.0.0.1:18100/api/sessions/{recovered_session}/decisions/{recovered['id']}/validate")
            assert validation['valid'] is True
            evidence['checks']['recovered_inference'] = {'status': recovered['status'], 'trace_id': recovered['trace_id'], 'valid': validation['valid'], 'model_version': recovered['model_version'], 'model_hash': recovered['model_hash']}
            evidence['success'] = True
        except Exception as exc:
            evidence['success'] = False
            evidence['error'] = str(exc)
            raise
        finally:
            if stopped:
                subprocess.run(compose + ['start', 'model'], check=False)
            evidence['finished_at'] = now()
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'success': True, 'evidence': str(path), 'trace_id': trace_id}))


if __name__ == '__main__':
    main()
