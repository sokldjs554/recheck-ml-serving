"""Export once, start fresh workers without fitting, then inject broken releases."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from recheck.model_bundle import export_bundle, runtime_versions

CHILD = '''
import asyncio, json
import httpx
from recheck import model

def forbidden(*args, **kwargs):
    raise AssertionError('training attempted in serving process')
model.train_model = forbidden
try:
    from recheck.worker import app
except ValueError as exc:
    print(json.dumps({'state': 'blocked', 'reason': str(exc)}))
    raise SystemExit(2)
async def run():
    rows = []
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://worker') as client:
            health = (await client.get('/health')).json()
            for epoch in ('risk-v1', 'risk-v2', 'risk-v3'):
                for features in ([0.,0.,0.,0.], [0.2,0.,1.,0.4], [1.,1.,1.,1.]):
                    response = await client.post('/infer', json={'model_version': epoch, 'features': features, 'deadline_ms': 2000})
                    assert response.status_code == 200, response.text
                    result = response.json()
                    rows.append({key: result[key] for key in ('model_version', 'model_hash', 'risk_score')})
    print(json.dumps({'state': 'served', 'training_disabled': True, 'health': health, 'predictions': rows}))
asyncio.run(run())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/model-handoff.json')
    parser.add_argument('--demo-output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='recheck-handoff-') as temp:
        root = Path(temp)
        good = root / 'trained'
        manifest = export_bundle(good)
        rows = []
        for damage in ('none', 'checksum', 'feature_order', 'runtime', 'missing', 'prediction'):
            bundle = root / damage
            shutil.copytree(good, bundle)
            path = bundle / 'manifest.json'
            contents = json.loads(path.read_text())
            if damage == 'checksum':
                artifact = bundle / 'risk-v2.joblib'
                artifact.write_bytes(artifact.read_bytes() + b'damage')
            elif damage == 'feature_order':
                contents['features'].reverse()
            elif damage == 'runtime':
                contents['runtime']['scikit-learn'] = 'incompatible'
            elif damage == 'missing':
                (bundle / 'risk-v2.joblib').unlink()
            elif damage == 'prediction':
                contents['models'][0]['probe_scores'][0] = 0.99999
            path.write_text(json.dumps(contents, indent=2) + '\n')
            env = {**os.environ, 'PYTHONPATH': str(ROOT / 'backend'), 'RECHECK_MODEL_BUNDLE': str(bundle),
                   'RECHECK_WORKLOAD': 'lightweight', 'RECHECK_EXECUTION_MODE': 'inline'}
            result = subprocess.run([sys.executable, '-c', CHILD], env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode == (0 if damage == 'none' else 2), result.stderr
            actual = json.loads(result.stdout.strip())
            expected_reason = {'checksum': 'artifact_checksum', 'feature_order': 'feature_contract',
                'runtime': 'runtime_versions', 'missing': 'artifact_missing', 'prediction': 'prediction_contract'}
            if damage == 'none':
                assert actual['health']['model_source'] == 'bundle'
                for index, prediction in enumerate(actual['predictions']):
                    expected = manifest['models'][(index // 3) % 2]['probe_scores'][index % 3]
                    assert abs(prediction['risk_score'] - expected) <= 1e-12
                assert actual['predictions'][0]['model_hash'] != actual['predictions'][6]['model_hash']
            else:
                assert actual['reason'] == expected_reason[damage], actual
            rows.append({'case': damage, 'exit_code': result.returncode, **actual})
    report = {'measured_at': datetime.now(timezone.utc).isoformat(), 'runtime': runtime_versions(),
        'scope': 'Synthetic logistic models; fresh Python worker per case, in-process ASGI HTTP transport. Not a public server benchmark.',
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ('backend/recheck/model.py', 'backend/recheck/model_bundle.py', 'scripts/verify_model_handoff.py')},
        'manifest': manifest, 'cases': rows}
    for path in (args.output, args.demo_output):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': len(rows), 'predictions_matched': len(rows[0]['predictions']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
