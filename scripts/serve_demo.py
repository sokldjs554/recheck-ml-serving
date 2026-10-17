"""Run two real processes in one small demo host, draining both on shutdown."""
from __future__ import annotations

import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
# Process initialization allowance, NOT the public workflow's 5-second budget.
MODEL_STARTUP_TIMEOUT_SECONDS = 90.0


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env.setdefault("RECHECK_MODEL_BUNDLE", str(ROOT / "backend" / "model_artifacts"))
    env.setdefault("MODEL_SERVICE_URL", "http://127.0.0.1:8001")
    if env.get('RENDER') == 'true' and not env.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        print('Public Render deployment requires a PostgreSQL DATABASE_URL; refusing ephemeral fallback', file=sys.stderr)
        return 1
    env.setdefault("DATABASE_URL", "sqlite:////tmp/recheck-demo.db")
    children: list[subprocess.Popen] = []
    stopping = False
    started = time.monotonic()

    def event(name, **fields):
        print(json.dumps({'event': name, 'elapsed_ms': round((time.monotonic() - started) * 1000, 3),
                          **fields}), file=sys.stderr, flush=True)

    def stop(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True
        # Stop admission at the gateway first, then drain model work.
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        event('model_process_starting', startup_budget_seconds=MODEL_STARTUP_TIMEOUT_SECONDS)
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "recheck.worker:app", "--host", "127.0.0.1", "--port", "8001"],
            cwd=ROOT / "backend", env=env,
        ))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready = False
        deadline = time.monotonic() + MODEL_STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if stopping:
                return 0
            exit_code = children[0].poll()
            if exit_code is not None:
                event('model_process_exited', exit_code=exit_code)
                return 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                with opener.open("http://127.0.0.1:8001/health", timeout=min(1, remaining)) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        if not ready:
            event('model_startup_timeout', startup_budget_seconds=MODEL_STARTUP_TIMEOUT_SECONDS)
            return 1
        event('model_ready')
        event('api_process_starting')
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "scripts.hosted_app:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000")],
            cwd=ROOT, env=env,
        ))
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(0.25)
        if not stopping:
            event('child_process_exited', exit_codes=[child.poll() for child in children])
        return 0 if stopping else 1
    finally:
        stop()
        for child in reversed(children):
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
