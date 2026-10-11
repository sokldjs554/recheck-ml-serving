"""Derive the UI's small measured comparison from the committed raw evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
raw = json.loads((ROOT / 'docs/evidence/safety-evaluation.json').read_text())
summary = {k: raw[k] for k in ('measured_at', 'scope', 'limitations', 'source_sha256')}
summary['databases'] = [dict(database=d['database'], database_version=d['database_version'],
    results=[dict(strategy=r['strategy'], totals=r['totals']) for r in d['results']]) for d in raw['databases']]
text = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
target = ROOT / 'demo/src/safety-evidence.json'
if args.check:
    if not target.exists() or target.read_text() != text:
        raise SystemExit('UI safety summary differs from raw evidence; run scripts/build_safety_summary.py')
    print('PASS UI comparison is derived from raw evidence')
else:
    target.write_text(text)
