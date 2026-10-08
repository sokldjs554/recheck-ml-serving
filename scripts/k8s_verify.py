"""Destructive acceptance exercises restricted to the disposable recheck-ops cluster."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18080")
    parser.add_argument("--output", default="docs/evidence/kubernetes-proof.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    os.environ["KUBECONFIG"] = str(root / "work/kubernetes/kubeconfig")
    os.environ["PATH"] = str(root / "work/tools") + os.pathsep + os.environ["PATH"]
    log = []

    def kubectl(*argv, check=True):
        command = ["kubectl", "--context", "kind-recheck-ops", "-n", "recheck", *argv]
        result = subprocess.run(command, text=True, capture_output=True, timeout=240)
        log.append({"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if check and result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result

    def get(resource, *extra):
        return json.loads(kubectl("get", resource, *extra, "-o", "json").stdout)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, body=None):
        raw = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(args.base + path, raw, {"Content-Type": "application/json"})
        with opener.open(req, timeout=3) as response:
            return json.load(response)

    def receipt(sid, body=None):
        return request(f"/api/sessions/{sid}/decisions", body or {"amount": 150000, "recipient": "kubernetes-lab", "idempotency_key": str(uuid.uuid4()), "protected": True})

    def assert_clear_current():
        fresh_sid = request("/api/sessions", {})["session_id"]
        result = receipt(fresh_sid)
        assert result["status"] == "clear", result
        validation = request(f"/api/sessions/{fresh_sid}/decisions/{result['id']}/validate")
        assert validation["valid"] is True, validation
        return {"receipt_id": result["id"], "status": result["status"], "valid": validation["valid"]}

    def ready(deployment):
        kubectl("rollout", "status", "deployment/" + deployment, "--timeout=180s")
        assert get("deployment/" + deployment)["status"]["availableReplicas"] >= 2

    context = kubectl("config", "current-context").stdout.strip()
    assert context == "kind-recheck-ops", context
    started = datetime.now(timezone.utc).isoformat()
    deployment_before = get("deployments")
    nodes = get("nodes")
    sid = request("/api/sessions", {})["session_id"]
    original_body = {"amount": 150000, "recipient": "kubernetes-lab", "idempotency_key": str(uuid.uuid4()), "protected": True}
    original = receipt(sid, original_body)
    assert original["status"] == "clear", original
    assert original["model_hash"] and original["trace_id"], original
    replicas = get("pods", "-l", "app=api")["items"]
    assert len(replicas) == 2
    replica_replays = []
    for pod in replicas:
        replay_code = "import json,urllib.request; r=urllib.request.Request(" + repr(f"http://127.0.0.1:8000/api/sessions/{sid}/decisions") + ",data=" + repr(json.dumps(original_body).encode()) + ",headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(r,timeout=5).read().decode())"
        replay = json.loads(kubectl("exec", pod["metadata"]["name"], "--", "python", "-c", replay_code).stdout)
        assert replay["id"] == original["id"] and replay["model_hash"] == original["model_hash"], replay
        replica_replays.append({"pod": pod["metadata"]["name"], "receipt_id": replay["id"]})
    pvc_before = get("pvc/data-postgres-0")
    phase = "baseline"
    samples = []
    events = []
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            t0 = time.monotonic()
            sample = {"at": datetime.now(timezone.utc).isoformat(), "phase": phase}
            try:
                monitor_sid = request("/api/sessions", {})["session_id"]
                result = receipt(monitor_sid)
                sample.update(http_status=200, receipt_status=result["status"], reason=result["reason"], model_hash=result["model_hash"])
            except urllib.error.HTTPError as exc:
                sample.update(http_status=exc.code, error=exc.read().decode()[:250])
            except Exception as exc:
                sample.update(http_status=0, error=type(exc).__name__ + ": " + str(exc)[:200])
            sample["latency_ms"] = round((time.monotonic() - t0) * 1000, 3)
            samples.append(sample)
            stop.wait(max(0, 0.5 - (time.monotonic() - t0)))

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()

    def action(name, function):
        nonlocal phase
        phase = name
        t0 = time.monotonic()
        event = {"name": name, "started_at": datetime.now(timezone.utc).isoformat()}
        events.append(event)
        function()
        deadline = time.monotonic() + 30
        while True:
            try:
                event["recovered_inference"] = assert_clear_current()
                break
            except urllib.error.URLError:
                if time.monotonic() >= deadline:
                    raise
                stop.wait(0.5)
        event["duration_seconds"] = round(time.monotonic() - t0, 3)
        event["passed"] = True
        # Observe the recovered steady state as well as the disruption.
        stop.wait(3)

    def replace(app):
        old = get("pods", "-l", "app=" + app)["items"][0]
        kubectl("delete", "pod", old["metadata"]["name"], "--wait=true", "--timeout=90s")
        ready(app)
        assert old["metadata"]["uid"] not in [p["metadata"]["uid"] for p in get("pods", "-l", "app=" + app)["items"]]

    def rollout():
        for app in ("api", "model"):
            kubectl("rollout", "restart", "deployment/" + app)
            ready(app)

    def bad_rollout():
        patch = [{"op": "replace", "path": "/spec/template/spec/containers/0/readinessProbe/httpGet/path", "value": "/deliberately-not-ready"}]
        kubectl("patch", "deployment/model", "--type=json", "-p", json.dumps(patch))
        failed = kubectl("rollout", "status", "deployment/model", "--timeout=20s", check=False)
        assert failed.returncode != 0, "The intentionally unready rollout unexpectedly succeeded"
        deployment = get("deployment/model")
        assert deployment["status"]["availableReplicas"] >= 2, deployment["status"]
        unhealthy = [p for p in get("pods", "-l", "app=model")["items"] if not all(s["ready"] for s in p["status"].get("containerStatuses", []))]
        assert unhealthy, "The new revision should stay unready"
        events[-1]["available_replicas_during_failed_rollout"] = deployment["status"]["availableReplicas"]
        events[-1]["unready_pod_count"] = len(unhealthy)

    def rollback():
        kubectl("rollout", "undo", "deployment/model")
        ready("model")

    def persistence():
        old = get("pod/postgres-0")
        kubectl("delete", "pod", "postgres-0", "--wait=true", "--timeout=90s")
        kubectl("rollout", "status", "statefulset/postgres", "--timeout=180s")
        assert old["metadata"]["uid"] != get("pod/postgres-0")["metadata"]["uid"]
        assert pvc_before["metadata"]["uid"] == get("pvc/data-postgres-0")["metadata"]["uid"]
        deadline = time.monotonic() + 60
        while True:
            try:
                records = request(f"/api/sessions/{sid}/decisions")["receipts"]
                assert any(r["id"] == original["id"] and r["model_hash"] == original["model_hash"] for r in records), records
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise
                stop.wait(0.5)
        events[-1]["receipt_survived"] = original["id"]
        events[-1]["pvc_uid_unchanged"] = pvc_before["metadata"]["uid"]

    try:
        stop.wait(5)
        action("api_pod_replacement", lambda: replace("api"))
        action("model_pod_replacement", lambda: replace("model"))
        action("rolling_restart", rollout)
        action("bad_model_rollout", bad_rollout)
        action("rollback", rollback)
        action("postgres_pod_replacement", persistence)
        phase = "recovered"
        stop.wait(5)
        ready("api")
        ready("model")
    finally:
        stop.set()
        thread.join(timeout=10)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".log").write_text("\n".join(json.dumps(row) for row in log) + "\n")
        summaries = {}
        for name in dict.fromkeys(s["phase"] for s in samples):
            rows = [s for s in samples if s["phase"] == name]
            failures = [s for s in rows if s["http_status"] != 200]
            summaries[name] = {"attempts": len(rows), "http_errors": len(failures), "http_error_fraction": len(failures) / len(rows), "receipt_outcomes": dict(Counter(s.get("receipt_status", "http_error") + ":" + str(s.get("reason", "")) for s in rows)), "error_timestamps": [s["at"] for s in failures]}
        outages = []
        outage = None
        for sample in samples:
            if sample["http_status"] != 200:
                if outage is None:
                    outage = {"first_failed_sample": sample["at"], "phase": sample["phase"], "failed_samples": 0}
                outage["failed_samples"] += 1
            elif outage is not None:
                outage["first_recovered_sample"] = sample["at"]
                outage["observed_recovery_seconds"] = (datetime.fromisoformat(sample["at"]) - datetime.fromisoformat(outage["first_failed_sample"])).total_seconds()
                outages.append(outage)
                outage = None
        if outage is not None:
            outages.append(outage)
        proof = {"started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(), "environment": "single-node kind v0.27.0 / Kubernetes v1.32.2 on shared local Docker host", "scope": "synthetic operational acceptance; not production HA or long-term availability", "sampling": "sequential create-session + real inference every 0.5s; 3s HTTP timeout; raw outcomes retained; brief unobserved gaps are possible", "events": events, "phase_summary": summaries, "samples": samples, "initial_receipt": original, "deployments_before": deployment_before, "nodes": nodes, "checks_passed": sum(e.get("passed", False) for e in events)}
        proof["observed_http_outages"] = outages
        proof["same_idempotency_key_replayed_on_each_api_replica"] = replica_replays
        proof["outage_interpretation"] = "Time between first failed and first recovered sample, not exact downtime; sampling and request duration bound temporal resolution. HTTP-200 review outcomes are reported separately."
        output.write_text(json.dumps(proof, indent=2) + "\n")
    assert proof["checks_passed"] == 6, proof["events"]
    print(json.dumps({"output": str(output), "checks_passed": proof["checks_passed"], "phase_summary": summaries}, indent=2))


if __name__ == "__main__":
    main()
