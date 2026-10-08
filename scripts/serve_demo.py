"""Run two real processes in one small demo host, draining both on shutdown."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env.setdefault("MODEL_SERVICE_URL", "http://127.0.0.1:8001")
    env.setdefault("DATABASE_URL", "sqlite:////tmp/recheck-demo.db")
    children: list[subprocess.Popen] = []
    stopping = False

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
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "recheck.worker:app", "--host", "127.0.0.1", "--port", "8001"],
            cwd=ROOT / "backend", env=env,
        ))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready = False
        for _ in range(120):
            if stopping or children[0].poll() is not None:
                break
            try:
                with opener.open("http://127.0.0.1:8001/health", timeout=1) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (OSError, TimeoutError):
                time.sleep(0.25)
        if not ready:
            print("Model server did not become ready", file=sys.stderr)
            return 1
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "scripts.hosted_app:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000")],
            cwd=ROOT, env=env,
        ))
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(0.25)
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
