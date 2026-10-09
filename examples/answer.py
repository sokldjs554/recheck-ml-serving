"""Run: PYTHONPATH=backend python examples/answer.py [API origin]."""
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
        draft = await client.prepare('하루 이체 한도', product='answer')
        validation = await client.validate(draft['id'])
        print(json.dumps(dict(product='answer', receipt=draft, validation=validation), ensure_ascii=False, indent=2))
        if not validation['valid']:
            raise SystemExit('Evidence is no longer valid; re-prepare before use')


if __name__ == '__main__':
    asyncio.run(main())
