"""Bounded public lab endpoints; no user-uploaded executable model artifacts."""
import asyncio
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .admission import Admission, DeadlineExceeded, Overloaded
from .evidence import EvidenceStore


class SourceEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: Literal['transfer', 'refund', 'card', 'loan']
    revision: int = Field(ge=1, le=1000000)
    text: str = Field(max_length=600)
    deleted: bool = False

    @field_validator('text')
    @classmethod
    def trim_text(cls, value):
        return value.strip()

    @model_validator(mode='after')
    def live_text_required(self):
        if not self.deleted and not self.text:
            raise ValueError('live document text must not be blank')
        return self


class Prepare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product: Literal['answer', 'checklist']
    query: str = Field(min_length=2, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator('query')
    @classmethod
    def meaningful_query(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('query must contain at least two characters')
        return value.strip()


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate: Literal['paired', 'mismatch', 'regressed']


def evidence_router(store):
    lab = EvidenceStore(store)
    router = APIRouter(prefix='/api/sessions/{sid}/evidence', tags=['evidence-lab'])
    admission = Admission(2, 4)

    @router.get('')
    def state(sid: str):
        return lab.view(sid)

    @router.post('/events')
    def event(sid: str, body: SourceEvent):
        return lab.event(sid, body)

    @router.post('/prepare')
    def prepare(sid: str, body: Prepare):
        return lab.prepare(sid, body)

    @router.post('/receipts/{rid}/use')
    def use(sid: str, rid: str):
        return lab.use(sid, rid)

    @router.post('/releases/evaluate')
    async def evaluate(sid: str, body: Candidate):
        try:
            async with admission.slot(time.monotonic()+5):
                # Shield and join canceled CPU work before releasing its slot.
                task = asyncio.create_task(asyncio.to_thread(lab.evaluate, sid, body.candidate))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
        except (Overloaded, DeadlineExceeded) as exc:
            raise HTTPException(429, 'release_evaluation_busy') from exc

    @router.post('/releases/{report_id}/promote')
    def promote(sid: str, report_id: str):
        return lab.promote(sid, report_id)

    return router
