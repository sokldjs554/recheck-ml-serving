"""Keep demo results reproducible from the full-path raw measurements."""
import argparse
import json
import gzip
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
raw = json.loads((ROOT/'docs/evidence/fullpath-load.json').read_text())
assert raw['validation_passed'] is True
summary = {k:raw[k] for k in ('measured_at','boundary','environment','deadline_ms','checks','database_version','resource_scope')}
summary['cases'] = [{k:v for k,v in c.items() if k != 'records'} for c in raw['cases']]
stress = json.loads(gzip.decompress((ROOT/'docs/evidence/fullpath-saturation.json.gz').read_bytes()))
assert stress['validation_passed'] is True
summary['saturation'] = {k:stress[k] for k in ('measured_at','checks')}
summary['saturation']['cases'] = [{k:v for k,v in c.items() if k != 'records'} for c in stress['cases']]
summary['limitations'] = ['Short shared-host experiment, not public hosting capacity or SLA.', 'One 503 is retained; a concurrent local SQL evaluator shared this database during this run.']
path = ROOT/'demo/src/fullpath-evidence.json'
content = json.dumps(summary,ensure_ascii=False,indent=2)+'\n'
if args.check:
    assert path.read_text() == content, 'regenerate full-path summary'
else:
    path.write_text(content)
