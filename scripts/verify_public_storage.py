#!/usr/bin/env python3
"""Capture a synthetic action, then verify the exact record after deployment.

The fixture contains only this script's synthetic session, never credentials.
Run capture before redeploy; verify after a different observer boot is visible.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--mode', choices=['capture','verify'], required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = dict(at=datetime.now(timezone.utc).isoformat(), mode=args.mode, passed=False)
    try:
        with httpx.Client(base_url=args.base.rstrip('/'), timeout=90) as client:
            client.get('/health').raise_for_status()
            ops = client.get('/api/operations'); ops.raise_for_status()
            journal = ops.json()
            assert journal['storage'] == 'postgresql' and journal['samples']
            result['storage'] = journal['storage']
            result['boot_id'] = journal['samples'][-1]['boot_id']
            if args.mode == 'capture':
                response = client.post('/api/sessions'); response.raise_for_status()
                sid = response.json()['session_id']
                prefix = '/api/sessions/'+sid+'/evidence'
                prepared = client.post(prefix+'/prepare', json=dict(product='answer',query='하루 이체 한도',idempotency_key=str(uuid.uuid4())))
                prepared.raise_for_status()
                receipt = prepared.json()
                # Keep the API's exact receipt shape and action response for replay.
                rid = receipt['id']
                key = str(uuid.uuid4())
                action = client.post(prefix+f'/receipts/{rid}/execute', json={'idempotency_key':key})
                action.raise_for_status()
                fixture = dict(captured_at=result['at'], boot_id=result['boot_id'], session_id=sid,
                               receipt_id=rid, key=key, action=action.json())
                args.fixture.parent.mkdir(parents=True, exist_ok=True)
                args.fixture.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
                result['fixture'] = fixture
            else:
                fixture = json.loads(args.fixture.read_text())
                assert result['boot_id'] != fixture['boot_id'], 'observer boot did not change; redeploy proof is invalid'
                prefix = '/api/sessions/'+fixture['session_id']+'/evidence'
                response = client.post(prefix+f'/receipts/{fixture["receipt_id"]}/execute',json={'idempotency_key':fixture['key']})
                response.raise_for_status()
                # Replay changes only the replayed marker; the persisted action is unchanged.
                replay = response.json()
                assert replay['action_id'] == fixture['action']['action_id']
                assert replay['replayed'] is True
                listed = client.get(prefix+'/actions'); listed.raise_for_status()
                records = listed.json()['actions']
                assert sum(a['action_id'] == replay['action_id'] for a in records) == 1
                result.update(previous_boot_id=fixture['boot_id'], action_id=replay['action_id'],
                              replay=replay, persisted_actions=len(records), captured_at=fixture['captured_at'])
            result['passed'] = True
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
