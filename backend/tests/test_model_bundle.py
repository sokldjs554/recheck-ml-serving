"""A training output must survive a process boundary without fitting again."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from recheck import model


def export(tmp_path, workload='lightweight'):
    from recheck.model_bundle import export_bundle
    return export_bundle(tmp_path / 'bundle', workload)


@pytest.mark.parametrize('workload', ['lightweight', 'cpu-ensemble'])
def test_fresh_process_scores_export_without_training(tmp_path, workload):
    export(tmp_path, workload)
    source = '''
import json
from recheck import model

def forbidden(*a, **kw):
    raise AssertionError('serving must not fit a model')
model.train_model = forbidden
first = model.get_model('risk-v1')
next_epoch = model.get_model('risk-v3')
assert first.score([0.2, 0, 1, 0.4]) == next_epoch.score([0.2, 0, 1, 0.4])
assert first.model_hash != next_epoch.model_hash
print(json.dumps({'score': first.score([0.2, 0, 1, 0.4]), 'hash': first.model_hash}))
'''
    env = {**os.environ, 'RECHECK_MODEL_BUNDLE': str(tmp_path / 'bundle'), 'RECHECK_WORKLOAD': workload}
    result = subprocess.run([sys.executable, '-c', source], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = model.train_model('risk-v1', workload)
    assert actual['hash'] == expected.model_hash
    assert actual['score'] == expected.score([0.2, 0, 1, 0.4])


@pytest.mark.parametrize('damage,reason', [
    ('bytes', 'artifact_checksum'), ('features', 'feature_contract'),
    ('dependency', 'runtime_versions'), ('missing', 'artifact_missing'),
    ('workload', 'workload_mismatch'), ('path', 'artifact_path'),
])
def test_bad_bundle_rejected_before_deserialization(tmp_path, monkeypatch, damage, reason):
    from recheck.model_bundle import load_bundle, BundleError
    export(tmp_path)
    directory = tmp_path / 'bundle'
    manifest = json.loads((directory / 'manifest.json').read_text())
    artifact = directory / manifest['models'][1]['file']
    if damage == 'bytes':
        artifact.write_bytes(artifact.read_bytes() + b'corrupt')
    elif damage == 'features':
        manifest['features'].reverse()
    elif damage == 'dependency':
        manifest['runtime']['scikit-learn'] = 'incompatible'
    elif damage == 'missing':
        artifact.unlink()
    elif damage == 'workload':
        manifest['workload'] = 'cpu-ensemble'
    else:
        manifest['models'][1]['file'] = '../outside.joblib'
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid bundle reached joblib.load')
    monkeypatch.setattr('joblib.load', forbidden)
    with pytest.raises(BundleError, match=reason):
        load_bundle(directory, 'lightweight')


def test_prediction_contract_rejects_wrong_output(tmp_path):
    from recheck.model_bundle import load_bundle, BundleError
    export(tmp_path)
    path = tmp_path / 'bundle' / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['models'][0]['probe_scores'][0] = 0.99999
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match='prediction_contract'):
        load_bundle(path.parent, 'lightweight')


def test_configured_missing_bundle_does_not_fall_back_to_training(tmp_path, monkeypatch):
    monkeypatch.setenv('RECHECK_MODEL_BUNDLE', str(tmp_path / 'missing'))
    with pytest.raises(ValueError, match='manifest_missing'):
        model.get_model('risk-v1')


def test_cli_cpu_bundle_loads_in_different_process(tmp_path):
    env = {**os.environ, 'RECHECK_MODEL_BUNDLE': str(tmp_path / 'cli'), 'RECHECK_WORKLOAD': 'cpu-ensemble'}
    command = [sys.executable, '-m', 'recheck.model', '--output', str(tmp_path / 'cli'), '--workload', 'cpu-ensemble']
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, '-c', "from recheck.model import get_model; print(get_model().score([0,0,0,0]))"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_exported_model_served_by_isolated_worker(tmp_path, monkeypatch):
    from dataclasses import replace
    import httpx
    from recheck.config import Settings
    from recheck.worker import create_app
    manifest = export(tmp_path)
    monkeypatch.setenv('RECHECK_MODEL_BUNDLE', str(tmp_path / 'bundle'))
    def forbidden(*args, **kwargs):
        pytest.fail('worker must not train')
    monkeypatch.setattr(model, 'train_model', forbidden)
    app = create_app(replace(Settings(), execution_mode='process', worker_concurrency=1))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://worker') as client:
            response = await client.post('/infer', json={'features': [0.2, 0, 1, 0.4], 'model_version': 'risk-v1', 'deadline_ms': 2000})
            assert response.status_code == 200, response.text
            assert response.json()['risk_score'] == manifest['models'][0]['probe_scores'][1]
            assert response.json()['model_hash'] == manifest['models'][0]['model_hash']
