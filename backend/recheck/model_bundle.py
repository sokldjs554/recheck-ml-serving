"""Trusted, build-time model handoff. Checksums detect damage, not malicious pickle."""
from functools import lru_cache
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import sys

import joblib
import numpy as np

from .model import FEATURE_NAMES, TrainedModel, estimator_hash, train_model

PROBES = [[0., 0., 0., 0.], [0.2, 0., 1., 0.4], [1., 1., 1., 1.]]
VERSIONS = ('risk-v1', 'risk-v2')


class BundleError(ValueError):
    """An unusable release must fail startup instead of silently re-training."""


def runtime_versions():
    return {'python': f'{sys.version_info.major}.{sys.version_info.minor}',
            **{name: version(name) for name in ('scikit-learn', 'numpy', 'scipy', 'joblib')}}


def export_bundle(destination, workload='lightweight'):
    if workload not in ('lightweight', 'cpu-ensemble'):
        raise BundleError('workload_mismatch')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'workload': workload, 'features': FEATURE_NAMES,
                'input': {'dtype': 'float64', 'range': [0, 1], 'shape': [4]},
                'runtime': runtime_versions(), 'probes': PROBES, 'models': []}
    for name in VERSIONS:
        trained = train_model(name, workload)
        path = destination / f'{name}.joblib'
        joblib.dump(trained.estimator, path)
        manifest['models'].append({'version': name, 'file': path.name,
            'artifact_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'model_hash': trained.model_hash, 'report': trained.report,
            'probe_scores': [trained.score(features) for features in PROBES]})
    # Export is a build operation, never a hot update of a serving directory.
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def load_bundle(directory, workload):
    directory = Path(directory)
    try:
        raw_manifest = (directory / 'manifest.json').read_bytes()
    except OSError as exc:
        raise BundleError('manifest_missing') from exc
    try:
        manifest = json.loads(raw_manifest)
        if manifest['format'] != 1:
            raise BundleError('manifest_format')
        if manifest['workload'] != workload:
            raise BundleError('workload_mismatch')
        if (manifest['features'] != FEATURE_NAMES or manifest['probes'] != PROBES or
                manifest['input'] != {'dtype': 'float64', 'range': [0, 1], 'shape': [4]}):
            raise BundleError('feature_contract')
        if manifest['runtime'] != runtime_versions():
            raise BundleError('runtime_versions')
        if [entry['version'] for entry in manifest['models']] != list(VERSIONS):
            raise BundleError('model_versions')
        payloads = []
        # Validate EVERY artifact before ANY deserialization. Load the verified
        # bytes, not a reopened path that could change between check and load.
        for entry in manifest['models']:
            if entry['file'] != f"{entry['version']}.joblib":
                raise BundleError('artifact_path')
            path = directory / entry['file']
            if path.is_symlink():
                raise BundleError('artifact_path')
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise BundleError('artifact_missing') from exc
            if hashlib.sha256(payload).hexdigest() != entry['artifact_sha256']:
                raise BundleError('artifact_checksum')
            payloads.append(payload)
        models = {}
        for entry, payload in zip(manifest['models'], payloads):
            estimator = joblib.load(io.BytesIO(payload))
            if estimator_hash(estimator, entry['version']) != entry['model_hash']:
                raise BundleError('model_identity')
            report = {**entry['report'], 'source': 'bundle',
                      'artifact_sha256': entry['artifact_sha256'],
                      'bundle_sha256': hashlib.sha256(raw_manifest).hexdigest()}
            model = TrainedModel(estimator, entry['version'], entry['model_hash'], report)
            scores = np.asarray([model.score(features) for features in PROBES])
            expected = np.asarray(entry['probe_scores'], dtype=float)
            if (expected.shape != scores.shape or not np.isfinite(scores).all() or
                    not np.allclose(scores, expected, rtol=0, atol=1e-12)):
                raise BundleError('prediction_contract')
            models[entry['version']] = model
        return models
    except BundleError:
        raise
    except Exception as exc:
        raise BundleError('invalid_bundle') from exc


@lru_cache(maxsize=4)
def prepared_bundle(directory, workload):
    # A process pins a release for its lifetime. Redeploy to change a bundle.
    return load_bundle(directory, workload)
