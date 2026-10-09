"""Small async HTTP client shared by two evidence-consuming products.

The caller owns httpx.AsyncClient (timeouts, authentication and lifetime).
HTTP failures raise; historical content is never promoted to a valid fallback.
"""
from typing import Literal
from urllib.parse import quote
import uuid

import httpx


class EvidenceClient:
    def __init__(self, client: httpx.AsyncClient, session_id: str):
        self.client = client
        self.path = f'/api/sessions/{quote(session_id, safe="")}/evidence'

    async def prepare(self, query: str, *, product: Literal['answer','checklist'], idempotency_key: str | None = None):
        response = await self.client.post(self.path+'/prepare', json=dict(query=query, product=product,
            idempotency_key=idempotency_key or str(uuid.uuid4())))
        response.raise_for_status()
        return response.json()

    async def validate(self, receipt_id: str):
        response = await self.client.post(self.path+f'/receipts/{quote(receipt_id, safe="")}/use', json={})
        response.raise_for_status()
        return response.json()
