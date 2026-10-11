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
            before=baseline.json()['samples'][-1]
            response=client.post('/api/sessions');response.raise_for_status()
            sid=response.json()['session_id']
            prefix='/api/sessions/'+sid+'/decisions'
            fault=client.post(prefix,json={'idempotency_key':str(uuid.uuid4()),'fault':'unavailable'})
            fault.raise_for_status()
            assert fault.json()['status']=='review' and fault.json()['reason']=='model_unavailable'
            recovered=client.post(prefix,json={'idempotency_key':str(uuid.uuid4())})
            recovered.raise_for_status()
            assert recovered.json()['status']=='clear'
            proof.update(failure=fault.json(),recovered=recovered.json())
            until=time.monotonic()+100
            while time.monotonic()<until:
                response=client.get('/api/operations');response.raise_for_status()
                journal=response.json()
                latest=journal['samples'][-1]
                if latest['boot_id']==before['boot_id'] and failures(latest)>failures(before):
                    proof.update(storage=journal['storage'],before=before,after=latest,passed=True)
                    break
                time.sleep(5)
            assert proof['passed'],'injected business failure never reached persistent public counters'
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in proof.items() if k not in ('before','after','failure','recovered')}))


if __name__=='__main__':
    main()
