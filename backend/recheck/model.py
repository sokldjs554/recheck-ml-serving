"""Deterministic synthetic classifier; its AUC is not real fraud performance."""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
import re
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 660065
FEATURE_NAMES = ["amount_ratio", "recipient_unfamiliar", "recent_changes", "velocity_ratio"]


@dataclass
class TrainedModel:
    estimator: object
    model_version: str
    model_hash: str
    report: dict

    def score(self, features):
        return float(self.estimator.predict_proba(np.array([features], dtype=float))[0, 1])


class ScenarioEnsemble:
    """Expected risk over a deterministic neighborhood of uncertain input features.

    All 4096 scenario predictions contribute to the returned score. This is an
    intentionally expensive synthetic robustness workload, not a claim that a
    production fraud model needs this computation.
    """
    def __init__(self, estimator):
        self.estimator = estimator
        self.offsets = np.random.default_rng(SEED + 1).normal(0, 0.08, (4096, 4))

    def predict_proba(self, x):
        results = []
        for row in x:
            scenarios = np.clip(row + self.offsets, 0, 1)
            expected = self.estimator.predict_proba(scenarios)[:, 1].mean()
            point = self.estimator.predict_proba(row.reshape(1, -1))[0, 1]
            score = 0.5 * point + 0.5 * expected
            results.append([1 - score, score])
        return np.asarray(results)


def train_model(version="risk-v1", workload="lightweight"):
    if version not in ("risk-v1", "risk-v2"):
        raise ValueError("unsupported model version")
    rng = np.random.default_rng(SEED)
    x = rng.random((4000, 4))
    x[:, 1:3] = (x[:, 1:3] > 0.6).astype(float)
    logits = 2.8 * x[:, 0] + 2.3 * x[:, 1] + 2 * x[:, 2] + 2.4 * x[:, 3] - 5.2
    y = (rng.random(len(x)) < 1 / (1 + np.exp(-logits))).astype(int)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, random_state=SEED, stratify=y)
    estimator = make_pipeline(StandardScaler(), LogisticRegression(random_state=SEED, C=1.0 if version == "risk-v1" else 0.4, max_iter=300))
    if workload == "cpu-ensemble":
        estimator = ExtraTreesClassifier(n_estimators=128, max_depth=12,
            min_samples_leaf=2 if version == "risk-v1" else 4, random_state=SEED, n_jobs=1)
    estimator.fit(x_train, y_train)
    auc = float(roc_auc_score(y_test, estimator.predict_proba(x_test)[:, 1]))
    if workload == "cpu-ensemble":
        estimator = ScenarioEnsemble(estimator)
    digest = estimator_hash(estimator, version)
    return TrainedModel(estimator, version, digest, {
        "seed": SEED, "rows": 4000, "train_rows": 3000, "test_rows": 1000,
        "features": FEATURE_NAMES, "test_auc": auc,
        "auc_scope": "point predictions on synthetic holdout, before scenario aggregation",
        "workload": workload, "scenario_rows": 4096 if workload == "cpu-ensemble" else 1,
        "scope": "synthetic data only; not real fraud detection accuracy",
    })


def estimator_hash(estimator, version):
    digest = hashlib.sha256(version.encode() + str(SEED).encode())
    if isinstance(estimator, ScenarioEnsemble):
        digest.update(b"scenario-ensemble-v1:point=0.5:expected=0.5")
        digest.update(estimator.offsets.astype("<f8").tobytes())
        for tree in estimator.estimator.estimators_:
            state = tree.tree_.__getstate__()
            for field in state["nodes"].dtype.names:
                digest.update(state["nodes"][field].tobytes())
            digest.update(state["values"].astype("<f8").tobytes())
        return digest.hexdigest()
    for step, attr in [(0, "mean_"), (0, "scale_"), (1, "coef_"), (1, "intercept_")]:
        digest.update(np.asarray(getattr(estimator.steps[step][1], attr), dtype="<f8").tobytes())
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _base_model(version, workload):
    return train_model(version, workload)


def get_model(version="risk-v1", workload=None):
    workload = workload or os.getenv("RECHECK_WORKLOAD", "lightweight")
    if workload not in ("lightweight", "cpu-ensemble"):
        raise ValueError("unknown workload")
    if not re.fullmatch(r"risk-v[1-9][0-9]{0,5}", version):
        raise ValueError("unsupported model version")
    epoch = int(version.split("v")[1])
    base = _base_model("risk-v1" if epoch % 2 else "risk-v2", workload)
    # Two pre-trained artifacts rotate under monotonic deployment epochs. Version
    # identity includes the epoch, preventing an old receipt surviving an ABA switch.
    return base if epoch <= 2 else TrainedModel(base.estimator, version, estimator_hash(base.estimator, version), base.report)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts")
    args = parser.parse_args()
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    manifests = []
    for version in ("risk-v1", "risk-v2"):
        model = train_model(version)
        artifact = destination / f"{version}.joblib"
        joblib.dump(model.estimator, artifact)
        manifests.append(dict(model_version=version, model_hash=model.model_hash,
                              artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(), **model.report))
    (destination / "manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")
    print(json.dumps(manifests, indent=2))
