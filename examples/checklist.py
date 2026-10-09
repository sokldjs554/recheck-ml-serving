"""A second consumer of the same receipt protocol, without a second serving stack.
Run: PYTHONPATH=backend python examples/checklist.py [API origin]
"""
import asyncio
import json
import sys
import httpx
from recheck.sdk import EvidenceClient


async def main():
    async with httpx.AsyncClient(base_url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000', timeout=90) as http:
        session = await http.post('/api/sessions')
        session.raise_for_status()
        client = EvidenceClient(http, session.json()['session_id'])
        receipt = await client.prepare('대출 소득 증빙 서류', product='checklist')
        validation = await client.validate(receipt['id'])
        print(json.dumps(dict(product='checklist', receipt=receipt, validation=validation), ensure_ascii=False, indent=2))
        if not validation['valid']:
            raise SystemExit('Do not act on a stale checklist')


if __name__ == '__main__':
    asyncio.run(main())
