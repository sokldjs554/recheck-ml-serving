"""Build the demo's measured serving view from committed experiment records."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def trace_view(spans):
    # Subtract integer nanoseconds before JSON reaches JS (where epoch ns exceed
    # Number.MAX_SAFE_INTEGER). These are recorded spans, not reconstructed SQL.
    start = min(span['start_ns'] for span in spans)
    by_id = {span['span_id']: span for span in spans}
    def depth(span):
        return 1 + depth(by_id[span['parent_span_id']]) if span['parent_span_id'] in by_id else 0
    return [dict(span, start_ms=(span['start_ns']-start)/1_000_000,
                 duration_ms=(span['end_ns']-span['start_ns'])/1_000_000,
                 depth=depth(span)) for span in spans]

def build():
    def read(name):
        return json.loads((ROOT / 'docs/evidence' / name).read_text())
    samples = []
    for name in ('compute-capacity-summary.json', 'compute-sustained-summary.json'):
        report = read(name)
        config = report['configurations'][0]
        case = config['cases'][0]
        outcomes = case['outcomes']
        assert sum(outcomes.values()) == case['requested']
        assert 0 <= case['good'] <= outcomes['200']
        samples.append(dict(source=name, measuredAt=report['timestamp'], deadline=report['deadline_ms'],
            replicas=config['service_replicas'], duration=case['duration_seconds'], rate=case['rate_rps'],
            requested=case['requested'], good=case['good'], late=outcomes['200']-case['good'],
            rejected=outcomes['429'], timeout=outcomes['504'],
            p95=case['all_outcome_latency_ms']['p95'], healthP95=case['health_latency_p95_ms'],
            rssBytes=case['peak_process_tree_rss_bytes'], cpuPerGood=case['cpu_ms_per_good_response']))
    observe = read('observability-latest.json')
    checks = observe['checks']
    k8s = read('kubernetes-proof.json')
    sustained = read('fullpath-sustained-summary.json')
    failure = read('failure-trace-proof.json')
    assert sustained['validation_passed'] and sustained['reconciliation']['passed']
    assert failure['success']
    consistency = read('consistency-costs-summary.json')
    assert all(cell['sql_reconciled'] for cell in consistency['cells'])
    return dict(consistency=consistency,
        sustained={key: sustained[key] for key in ('measured_at', 'phases', 'settings', 'reconciliation', 'retention', 'cost', 'raw_file', 'raw_sha256')},
        failure={**{key: failure[key] for key in ('started_at', 'failed', 'recovered')},
                 'trace_views': {key: trace_view(failure[key]['exported_spans']) for key in ('failed','recovered')}},
        samples=samples, public=read('public-monitor-2026-10-11.json'), observability=dict(start=observe['started_at'], end=observe['finished_at'],
        trace=checks['exported_cross_service_trace'], probes=checks['dependency_failure_probes'],
        recovered=checks['recovered_inference'],
        firingAt=checks['alert_firing'][0]['received_at'], resolvedAt=checks['alert_resolved'][0]['received_at']),
        kubernetes=dict(start=k8s['started_at'], end=k8s['finished_at'], events=k8s['events'], phases=k8s['phase_summary']))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    target = ROOT / 'demo/src/serving-evidence.json'
    if args.check:
        if not target.exists() or target.read_text() != text:
            raise SystemExit('Serving UI differs from stored evidence; run scripts/build_serving_summary.py')
        print('PASS serving view matches source evidence')
    else:
        target.write_text(text)
