#!/usr/bin/env python3
"""Two local HTTP decisions, OTLP capture, structured logs and PostgreSQL reconciliation.

Requires an owned disposable local PostgreSQL database in DATABASE_URL. Starts only
its own API/model processes; never stops another service or runs a load generator.
The receiver decodes actual SDK OTLP exports, not receipt display-span summaries.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import httpx
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def wait_for(probe, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except (httpx.HTTPError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError('focused verification timed out')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port', type=int, default=18310)
    parser.add_argument('--model-port', type=int, default=18311)
    parser.add_argument('--otlp-port', type=int, default=18312)
    parser.add_argument('--output', default='docs/evidence/failure-trace-proof.json')
    args = parser.parse_args()
    url = make_url(os.environ['DATABASE_URL'])
    assert url.get_backend_name() in ('postgres', 'postgresql')
    assert url.host in ('localhost', '127.0.0.1', '::1'), 'local PostgreSQL only'
    assert url.database.startswith('recheck_failure_'), 'use a dedicated recheck_failure_* database'
    sql_url = url.set(drivername='postgresql+psycopg')
    engine = create_engine(sql_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.decisions')")).scalar() is None, 'database must be fresh'
    for port in (args.api_port, args.model_port, args.otlp_port):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
    spans = []
    lock = threading.Lock()

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            data = ExportTraceServiceRequest()
            data.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
            batch = []
            for resource in data.resource_spans:
                service = next(a.value.string_value for a in resource.resource.attributes if a.key == 'service.name')
                for scope in resource.scope_spans:
                    for span in scope.spans:
                        batch.append({
                            'service': service, 'trace_id': span.trace_id.hex(),
                            'span_id': span.span_id.hex(), 'parent_span_id': span.parent_span_id.hex(),
                            'name': span.name, 'status_code': span.status.code,
                            'status_message': span.status.message,
                            'start_ns': span.start_time_unix_nano, 'end_ns': span.end_time_unix_nano,
                            'events': [{'name': event.name, 'time_ns': event.time_unix_nano,
                                        'attributes': {a.key: a.value.string_value for a in event.attributes}}
                                       for event in span.events]})
            with lock:
                spans.extend(batch)
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-protobuf')
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', args.otlp_port), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    work = ROOT / 'work' / ('failure-trace-' + str(time.time_ns()))
    work.mkdir(parents=True)
    evidence = {'started_at': now(), 'success': False,
                'scope': 'owned loopback API/model processes and dedicated local PostgreSQL; two decisions; no public traffic',
                'capture': 'actual SDK OTLP HTTP protobuf exports to a focused local receiver; not Jaeger',
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT / 'backend/recheck').glob('*.py'))},
                'conditions': {'workload': 'lightweight', 'execution': 'inline', 'deadline_ms': 300,
                               'ports': [args.api_port, args.model_port, args.otlp_port],
                               'database': url.database}}
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'backend'),
               MODEL_SERVICE_URL=f'http://127.0.0.1:{args.model_port}', RECHECK_OBSERVE='0',
               RECHECK_WORKLOAD='lightweight', RECHECK_EXECUTION_MODE='inline', RECHECK_DEADLINE_MS='300',
               OTEL_EXPORTER_OTLP_ENDPOINT=f'http://127.0.0.1:{args.otlp_port}',
               OTEL_BSP_SCHEDULE_DELAY='100', OTEL_TRACES_EXPORTER='none', OTEL_METRICS_EXPORTER='none',
               OTEL_LOGS_EXPORTER='none', NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
    processes, handles = [], []
    try:
        for name, module, port in [('model', 'recheck.worker:app', args.model_port),
                                   ('api', 'recheck.api:app', args.api_port)]:
            handle = (work / f'{name}.log').open('w')
            handles.append(handle)
            # Enable the existing receipt logger; no application instrumentation is patched.
            code = ('import logging,uvicorn; logging.basicConfig(level=logging.INFO); '
                    f'uvicorn.run({module!r},host="127.0.0.1",port={port},log_level="info")')
            processes.append(subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, env=env,
                                               stdout=handle, stderr=subprocess.STDOUT))
        with httpx.Client(base_url=f'http://127.0.0.1:{args.api_port}', timeout=5, trust_env=False) as client:
            wait_for(lambda: client.get('/ready').status_code == 200)
            sid = client.post('/api/sessions').json()['session_id']
            evidence['session_id'] = sid
            for label, fault in [('failed', 'unavailable'), ('recovered', 'none')]:
                request = {'idempotency_key': f'failure-walkthrough-{label}'}
                if fault != 'none':
                    request['fault'] = fault
                at = now()
                response = client.post(f'/api/sessions/{sid}/decisions', json=request)
                assert response.status_code == 200, response.text
                receipt = response.json()
                expected = 'review' if label == 'failed' else 'clear'
                assert receipt['status'] == expected, receipt
                assert receipt['reason'] == ('model_unavailable' if label == 'failed' else 'no_current_warning')
                validation = client.get(f"/api/sessions/{sid}/decisions/{receipt['id']}/validate").json()
                assert validation['valid'] is (label == 'recovered')
                with engine.connect() as conn:
                    row = conn.execute(text('SELECT id, session_id, idempotency_key, payload FROM decisions WHERE id = :id'),
                                       {'id': receipt['id']}).mappings().one()
                    row = dict(row)
                assert row['payload'] == receipt, 'separate SQL connection must read the exact committed HTTP receipt'
                evidence[label] = {'at': at, 'request': request, 'http_status': response.status_code,
                                   'receipt': receipt, 'validation': validation, 'sql_row': row}
            evidence['metrics'] = client.get('/metrics').text.splitlines()
            evidence['metrics'] = [line for line in evidence['metrics']
                                   if line.startswith('recheck_business_outcomes_total')]
            for label in ('failed', 'recovered'):
                trace_id = evidence[label]['receipt']['trace_id']
                def captured():
                    with lock:
                        found = [s for s in spans if s['trace_id'] == trace_id]
                    names = {s['name'] for s in found}
                    return found if {'decision', 'snapshot', 'model.http', 'model.infer', 'fence.commit'} <= names else None
                captured_spans = wait_for(captured)
                by_name = {s['name']: s for s in captured_spans}
                assert by_name['model.infer']['parent_span_id'] == by_name['model.http']['span_id']
                assert by_name['model.http']['parent_span_id'] == by_name['decision']['span_id']
                assert by_name['fence.commit']['parent_span_id'] == by_name['decision']['span_id']
                if label == 'failed':
                    assert 'model.predict' not in by_name
                    assert by_name['model.http']['status_code'] == 2
                    assert by_name['model.infer']['status_code'] == 2
                    assert by_name['decision']['status_code'] == 2
                    assert any('model_unavailable' in event['attributes'].get('exception.message', '')
                               for event in by_name['model.infer']['events'])
                else:
                    assert 'model.predict' in by_name
                    assert by_name['model.predict']['parent_span_id'] == by_name['model.infer']['span_id']
                evidence[label]['exported_spans'] = sorted(captured_spans, key=lambda s: s['start_ns'])
            evidence['success'] = True
    except Exception as exc:
        evidence['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()
        server.shutdown()
        engine.dispose()
        evidence['logs'] = {name: (work / f'{name}.log').read_text().splitlines()
                            for name in ('api', 'model') if (work / f'{name}.log').exists()}
        if evidence['success']:
            for label in ('failed', 'recovered'):
                receipt = evidence[label]['receipt']
                matches = [line for line in evidence['logs']['api']
                           if receipt['trace_id'] in line and receipt['id'] in line]
                if len(matches) != 1:
                    evidence.update(success=False, error='missing unique trace-linked API receipt log')
                evidence[label]['structured_log'] = matches
        evidence['finished_at'] = now()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + '\n')
    assert evidence['success'], evidence.get('error')
    print(json.dumps({'success': True, 'output': str(output),
                      'failed_trace': evidence['failed']['receipt']['trace_id']}))


if __name__ == '__main__':
    main()
