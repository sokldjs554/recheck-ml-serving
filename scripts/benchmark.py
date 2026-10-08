"""Open-arrival synthetic load; retain ALL outcomes, not only fast successes."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import time
import uuid

import httpx


def percentile(values: list[float], q: float) -> float | None:
    return round(sorted(values)[max(0, math.ceil(q * len(values)) - 1)], 3) if values else None


async def run_case(client: httpx.AsyncClient, count: int, rate: float, delay: int, protected: bool) -> dict:
    s = await client.post("/api/sessions")
    s.raise_for_status()
    session = s.json()["session_id"]
    rows = []
    start = time.perf_counter()

    async def request(index: int):
        scheduled = start + index / rate
        await asyncio.sleep(max(0, scheduled-time.perf_counter()))
        began = time.perf_counter()
        row = {"index":index,"dispatch_lag_ms":round((began-scheduled)*1000,3)}
        try:
            r = await client.post(f"/api/sessions/{session}/decisions", json={"amount":150000,"recipient":"demo-recipient","idempotency_key":str(uuid.uuid4()),"delay_ms":delay,"fault":"none","protected":protected})
            row["http_status"] = r.status_code
            if r.status_code == 200:
                receipt = r.json()
                row.update(status=receipt["status"], reason=receipt["reason"], server_latency_ms=receipt["latency_ms"], model_hash=receipt["model_hash"])
            else:
                row.update(status="http_error",reason=str(r.status_code))
        except httpx.HTTPError as error:
            row.update(status="transport_error",reason=type(error).__name__)
        row["latency_ms"] = round((time.perf_counter()-began)*1000,3)
        rows.append(row)

    await asyncio.gather(*(request(i) for i in range(count)))
    elapsed = time.perf_counter()-start
    latencies = [r["latency_ms"] for r in rows]
    clear = [r["latency_ms"] for r in rows if r["status"] == "clear"]
    return {"protected":protected,"offered_count":count,"offered_rate_rps":rate,"injected_delay_ms":delay,
            "completed_count":len(rows),"elapsed_s":round(elapsed,3),"completion_rate_rps":round(len(rows)/elapsed,2),
            "outcomes":dict(Counter(r["status"] for r in rows)),"reasons":dict(Counter(r["reason"] for r in rows)),
            "all_p50_ms":percentile(latencies,.5),"all_p95_ms":percentile(latencies,.95),"all_p99_ms":percentile(latencies,.99),
            "clear_p95_ms":percentile(clear,.95),"max_dispatch_lag_ms":max(r["dispatch_lag_ms"] for r in rows),
            "rows":sorted(rows,key=lambda r:r["index"])}


async def main(args) -> dict:
    async with httpx.AsyncClient(base_url=args.base,timeout=5,trust_env=False,limits=httpx.Limits(max_connections=200,max_keepalive_connections=100)) as client:
        health = await client.get("/health")
        health.raise_for_status()
        # Warmup includes gateway, SQL schema path, worker and model.
        await run_case(client, 5, 5, 0, True)
        cases=[]
        for repeat in range(args.repeats):
            for protected in ([False,True] if repeat%2 == 0 else [True,False]):
                result=await run_case(client,args.count,args.rate,args.delay,protected)
                result["repeat"]=repeat+1
                cases.append(result)
        return {"measured_at":datetime.now(timezone.utc).isoformat(),"environment":{"python":platform.python_version(),"platform":platform.platform(),"cpu_count":os.cpu_count()},
                "scope":"Local HTTP gateway + separate Python model process. Synthetic fixed transaction. Optional explicit delay injection is NOT model compute time. Baseline disables version fencing only; not monolith-vs-MSA.",
                "health":health.json(),"warmup_requests":5,"cases":cases}


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",default="http://127.0.0.1:8000")
    p.add_argument("--count",type=int,default=60)
    p.add_argument("--rate",type=float,default=80)
    p.add_argument("--delay",type=int,default=80)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--output",default="docs/evidence/load.json")
    args=p.parse_args()
    if not 1 <= args.count <= 80 or not 0 < args.rate <= 200 or not 0 <= args.delay <= 2000 or not 1 <= args.repeats <= 5:
        p.error("Use count 1..80, rate (0,200], delay 0..2000, repeats 1..5")
    result=asyncio.run(main(args))
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"output":str(dest),"cases":[{k:v for k,v in c.items() if k!='rows'} for c in result['cases']]},indent=2))
