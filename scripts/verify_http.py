"""Acceptance proof across real gateway and model HTTP processes."""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid

import httpx


async def verify(base: str) -> dict:
    async with httpx.AsyncClient(base_url=base, timeout=10, trust_env=False) as client:
        health = await client.get("/health")
        health.raise_for_status()
        session = (await client.post("/api/sessions")).json()["session_id"]
        prefix = f"/api/sessions/{session}"
        body = dict(amount=150000, recipient="demo-recipient", idempotency_key=str(uuid.uuid4()), delay_ms=0, fault="none", protected=True)
        response = await client.post(prefix + "/decisions", json=body)
        response.raise_for_status()
        receipt = response.json()
        assert receipt["model_hash"], receipt
        assert receipt["trace_id"] and receipt["spans"], receipt
        replay = await client.post(prefix + "/decisions", json=body)
        replay.raise_for_status()
        assert replay.json()["id"] == receipt["id"], "Duplicate request created a new receipt"
        conflict = await client.post(prefix + "/decisions", json={**body, "amount":150001})
        assert conflict.status_code == 409, conflict.text
        changed = await client.post(prefix + "/mutations", json={"kind":"feature"})
        changed.raise_for_status()
        valid = await client.get(prefix + f"/decisions/{receipt['id']}/validate")
        valid.raise_for_status()
        assert valid.json()["valid"] is False, valid.text
        unavailable = await client.post(prefix + "/decisions", json={**body,"idempotency_key":str(uuid.uuid4()),"fault":"unavailable"})
        unavailable.raise_for_status()
        assert unavailable.json()["status"] == "review", unavailable.text
        other = (await client.post("/api/sessions")).json()
        assert other["feature_version"] == 1, "Session state leaked"
        unknown = await client.get(f"/api/sessions/{other['session_id']}/decisions/{receipt['id']}/validate")
        assert unknown.status_code == 404, "Cross-session receipt was visible"
        return {"health":health.json(),"receipt":receipt,"invalidation":valid.json(),"provider_failure":unavailable.json()["reason"],"checks_passed":7}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.base)), ensure_ascii=False, indent=2))
