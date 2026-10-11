#!/usr/bin/env python3
"""Verify durable public counters with an explicitly injected model failure.

This is a model fault response test, not a claim of a real provider outage.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
import httpx


def failures(sample):
    return sum(r['value'] for r in sample['api'] if r['name']=='recheck_business_outcomes_total' and r['labels'].get('reason')=='model_unavailable')


def increased_failure(before, after, since):
    baseline = {}
    for sample in before:
        baseline[sample['boot_id']] = max(baseline.get(sample['boot_id'], 0), failures(sample))
    # A rolling deployment can still serve a request on the old instance after
    # the new instance has emitted its first sample. Inspect every boot's delta.
    return next((s for s in reversed(after) if s['at'] >= since and
                 failures(s) > baseline.get(s['boot_id'], 0)), None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    proof=dict(at=datetime.now(timezone.utc).isoformat(), passed=False,
               scope='public API injected model-unavailable response then normal inference; durable boot-scoped counters, not a real provider outage')
    try:
        with httpx.Client(base_url=args.base,timeout=90) as client:
            client.get('/health').raise_for_status()
            baseline=client.get('/api/operations');baseline.raise_for_status()
            before=baseline.json()['samples']
            proof['before_samples']=before
            response=client.post('/api/sessions');response.raise_for_status()
            sid=response.json()['session_id']
            prefix='/api/sessions/'+sid+'/decisions'
            injected_at=time.time()
            fault=client.post(prefix,json={'idempotency_key':str(uuid.uuid4()),'fault':'unavailable'})
            fault.raise_for_status()
            assert fault.json()['status']=='review' and fault.json()['reason']=='model_unavailable'
            recovered=client.post(prefix,json={'idempotency_key':str(uuid.uuid4())})
            recovered.raise_for_status()
            assert recovered.json()['status']=='clear'
            proof.update(failure=fault.json(),recovered=recovered.json())
            saved=client.get(prefix);saved.raise_for_status()
            assert fault.json() in saved.json()['receipts'] and recovered.json() in saved.json()['receipts']
            proof['both_receipts_persisted']=True
            until=time.monotonic()+100
            while time.monotonic()<until:
                response=client.get('/api/operations');response.raise_for_status()
                journal=response.json()
                proof['last_observed_samples']=journal['samples']
                observed=increased_failure(before,journal['samples'],injected_at)
                if observed:
                    proof.update(storage=journal['storage'],after=observed,passed=True)
                    break
                time.sleep(5)
            assert proof['passed'],'injected business failure never reached persistent public counters'
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in proof.items() if k not in ('before_samples','last_observed_samples','after','failure','recovered')}))


if __name__=='__main__':
    main()
