"""Derive the UI's small measured comparison from the committed raw evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
raw = json.loads((ROOT / 'docs/evidence/safety-evaluation.json').read_text())
workloads = json.loads((ROOT / 'docs/evidence/action-workloads.json').read_text())
if not workloads.get('validation', {}).get('passed'):
    raise SystemExit('Workload evidence did not pass its SQL and outcome checks')
if args.check:
    import hashlib
    for report in (raw, workloads):
        for path, expected in report['source_sha256'].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise SystemExit(f'Stored comparison evidence predates {path}; rerun its evaluator')
summary = {k: raw[k] for k in ('measured_at', 'scope', 'limitations', 'source_sha256')}
summary['databases'] = [dict(database=d['database'], database_version=d['database_version'],
    results=[dict(strategy=r['strategy'], totals=r['totals'], cases=[dict(
        case=c['case'], schedule=c['schedule'], expected_reason=c['expected_reason'],
        receipt=dict(id=c['receipt']['id'], output=c['receipt']['output'], references=c['receipt']['references']),
        state_at_submit=c['state_at_submit'], separate_check=c['separate_check'],
        attempts=[{k: a[k] for k in ('attempt', 'observed', 'error', 'persisted_action_count',
                                      'stale_accepts', 'false_rejects', 'duplicate_commits')} |
                  dict(action_id=a['response']['action_id'] if a['response'] else None)
                  for a in c['attempts']]) for c in r['cases']]) for r in d['results']]) for d in raw['databases']]
summary['workloads'] = {k: workloads[k] for k in ('measured_at', 'parameters', 'timing', 'concurrency', 'limitations', 'environment')}
summary['workloads']['databases'] = [dict(database=d['database'], strategies=[dict(
    strategy=r['strategy'], latency={k: v for k, v in r['latency'].items() if k not in ('samples', 'samples_ms')},
    workloads=[dict(name=w['name'], totals=w['totals'], example=w['runs'][0]) for w in r['workloads']])
    for r in d['strategies']]) for d in workloads['databases']]
text = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
target = ROOT / 'demo/src/safety-evidence.json'
if args.check:
    if not target.exists() or target.read_text() != text:
        raise SystemExit('UI safety summary differs from raw evidence; run scripts/build_safety_summary.py')
    print('PASS UI comparison is derived from raw evidence')
else:
    target.write_text(text)
