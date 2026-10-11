"""Bounded, durable observations; cumulative counters are scoped to a boot ID.

This is a sampled operational journal, not a replacement for an external uptime
monitor. A sleeping/dead host cannot observe itself. Never store request bodies.
"""
import asyncio
from collections import deque
import logging
import time
import uuid

from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import JSON, Float, String, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

log = logging.getLogger('recheck.operations')


class OpsBase(DeclarativeBase):
    pass


class Observation(OpsBase):
    __tablename__ = 'operational_observations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


def counter_rows(families):
    return [dict(name=s.name, labels=s.labels, value=s.value)
            for family in families for s in family.samples
            if s.name in {'recheck_http_requests_total', 'recheck_business_outcomes_total'}][:1024]


def counters(registry):
    return counter_rows(registry.collect())


class Journal:
    def __init__(self, engine):
        self.engine = engine
        OpsBase.metadata.create_all(engine)

    def append(self, row):
        with Session(self.engine) as db, db.begin():
            if db.get(Observation, row['id']) is None:
                db.add(Observation(id=row['id'], at=row['at'], payload=row))
            db.execute(delete(Observation).where(Observation.at < time.time() - 7 * 86400))

    def read(self):
        with Session(self.engine) as db:
            rows = list(db.scalars(select(Observation.payload).order_by(Observation.at.desc()).limit(120)))
        return dict(storage=self.engine.dialect.name, retention_days=7, interval_seconds=60,
                    scope='Latest 120 persisted samples; boot-scoped cumulative counters. Gaps are unknown, not uptime.',
                    samples=list(reversed(rows)))


class Observer:
    def __init__(self, engine, metrics, model_client, health):
        self.journal = Journal(engine)
        self.metrics, self.model_client, self.health = metrics, model_client, health
        self.boot_id = str(uuid.uuid4())
        self.pending = deque(maxlen=120)
        self.dropped = 0
        self.stop = asyncio.Event()
        self.previous = None

    async def sample(self):
        current = counters(self.metrics.registry)
        # No self-traffic or idle DB polling to defeat free-tier suspension.
        if current == self.previous and not self.pending:
            return
        row = dict(id=str(uuid.uuid4()), at=time.time(), boot_id=self.boot_id,
                   ready=True, reason='ok', api=current, model=[])
        try:
            await self.health()
        except Exception as exc:
            row.update(ready=False, reason=getattr(exc, 'detail', 'probe_failed'))
        try:
            response = await self.model_client.get('/metrics', timeout=1)
            response.raise_for_status()
            row['model'] = counter_rows(text_string_to_metric_families(response.text))
        except Exception:
            row['model_metrics_missing'] = True
        if len(self.pending) == self.pending.maxlen:
            self.dropped += 1
        row['dropped_unpersisted_samples'] = self.dropped
        self.pending.append(row)
        while self.pending:
            try:
                await asyncio.to_thread(self.journal.append, self.pending[0])
                self.pending.popleft()
            except Exception as exc:
                log.warning('observation persistence failed: %s', type(exc).__name__)
                break
        self.previous = current

    async def run(self):
        while not self.stop.is_set():
            await self.sample()
            try:
                await asyncio.wait_for(self.stop.wait(), 60)
            except TimeoutError:
                pass
        await self.sample()
