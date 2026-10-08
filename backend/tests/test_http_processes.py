"""Opt-in real socket/process integration; regular unit tests need no sockets."""
import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RECHECK_NETWORK_TESTS") != "1", reason="Set RECHECK_NETWORK_TESTS=1 to exercise real HTTP processes")


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def servers(tmp_path):
    worker_port, api_port = unused_port(), unused_port()
    env = dict(os.environ, MODEL_SERVICE_URL=f"http://127.0.0.1:{worker_port}",
               DATABASE_URL=f"sqlite:///{tmp_path / 'http.db'}", RECHECK_DEADLINE_MS="100")
    processes = []
    logs = []
    try:
        for name, port in (("worker", worker_port), ("api", api_port)):
            log = (tmp_path / f"{name}.log").open("w")
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", f"recheck.{name}:app", "--host", "127.0.0.1", "--port", str(port)], cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=log))
        with httpx.Client(trust_env=False) as client:
            until = time.monotonic() + 15
            while time.monotonic() < until:
                try:
                    if client.get(f"http://127.0.0.1:{api_port}/health", timeout=0.2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if any(p.poll() is not None for p in processes):
                    pytest.fail("HTTP process exited: " + "\n".join(p.read_text() for p in tmp_path.glob("*.log")))
                time.sleep(0.02)
            else:
                pytest.fail("HTTP processes did not become healthy")
        yield f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{worker_port}"
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for log in logs:
            log.close()


async def test_separate_http_processes_preserve_freshness_trace_and_deadlines(tmp_path):
    with servers(tmp_path) as (api_url, worker_url):
        async with httpx.AsyncClient(base_url=api_url, trust_env=False) as client:
            sid = (await client.post("/api/sessions")).json()["session_id"]
            base = dict(amount=150000, recipient="demo-recipient", idempotency_key="first", delay_ms=0, fault="none", protected=True)
            trace_id = "1234567890abcdef1234567890abcdef"
            first = (await client.post(f"/api/sessions/{sid}/decisions", json=base, headers={"traceparent": f"00-{trace_id}-1234567890abcdef-01"})).json()
            assert first["status"] == "clear"
            assert first["trace_id"] == trace_id
            assert "model.predict" in {s["name"] for s in first["spans"]}
            delayed = dict(base, idempotency_key="race", delay_ms=50)
            pending = asyncio.create_task(client.post(f"/api/sessions/{sid}/decisions", json=delayed))
            async with httpx.AsyncClient(base_url=worker_url, trust_env=False) as monitor:
                for _ in range(100):
                    if (await monitor.get("/health")).json()["active"]:
                        break
                    await asyncio.sleep(0.001)
                await client.post(f"/api/sessions/{sid}/mutations", json={"kind": "feature"})
                assert (await pending).json()["status"] == "invalidated"
                timed_out = (await client.post(f"/api/sessions/{sid}/decisions", json=dict(base, idempotency_key="timeout", fault="timeout"))).json()
                assert timed_out["status"] == "review"
                assert timed_out["reason"] == "deadline_exceeded"
                # Disconnect does not assume immediate remote cancellation. The worker's
                # own propagated deadline must end its bounded work independently.
                await asyncio.sleep(0.06)
                health = (await monitor.get("/health")).json()
                assert health["active"] == health["admitted"] == 0
