"""Session-owned evidence with short SQL fences around actual retrieval work."""
from copy import deepcopy
from contextlib import contextmanager
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .store import Base
from .retrieval import SCOPE, initial_sources, digest, build_artifact, retrieve, evaluate_release, compatible

now = time.time


class EvidenceState(Base):
    __tablename__ = 'evidence_states'
    session_id: Mapped[str] = mapped_column(ForeignKey('demo_sessions.id', ondelete='CASCADE'), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def locked(self, sid):
        with self.store.transaction(write=True) as db:
            self.store.row(db, sid, lock=True)
            row = db.get(EvidenceState, sid)
            if row is None:
                sources = initial_sources()
                row = EvidenceState(session_id=sid, payload=dict(sources=sources,
                    active=dict(epoch=1, artifact=build_artifact(sources, 'baseline')),
                    receipts=[], reports=[], events=[]))
                db.add(row)
            state = deepcopy(row.payload)
            yield state
            row.payload = state

    def snapshot(self, sid):
        with self.locked(sid) as state:
            return state

    @staticmethod
    def active(state):
        active = state['active']
        return dict(release_epoch=active['epoch'], artifact_hash=active['artifact']['artifact_hash'],
                    model_hash=active['artifact']['model_hash'], index_model_hash=active['artifact']['index']['model_hash'],
                    corpus_hash=active['artifact']['corpus_hash'])

    def view(self, sid):
        state = self.snapshot(sid)
        return dict(sources=list(state['sources'].values()), active_release=self.active(state), corpus_hash=digest(state['sources']),
                    index_stale=digest(state['sources']) != state['active']['artifact']['corpus_hash'],
                    receipts=state['receipts'], reports=state['reports'], events=state['events'], scope=SCOPE)

    def event(self, sid, body):
        with self.locked(sid) as state:
            old = state['sources'][body.source_id]
            new = dict(source_id=body.source_id, title=old['title'], revision=body.revision,
                       text=body.text, deleted=body.deleted)
            if new['revision'] < old['revision']:
                raise HTTPException(409, 'out_of_order_event')
            if new['revision'] == old['revision']:
                if new != old:
                    raise HTTPException(409, 'conflicting_event_revision')
                return dict(applied=False, source=old)
            state['sources'][body.source_id] = new
            state['events'] = [dict(source_id=body.source_id, revision=body.revision,
                operation='delete' if body.deleted else 'update', at=now())] + state['events'][:19]
            return dict(applied=True, source=new)

    @staticmethod
    def existing(state, key, fingerprint):
        previous = next((r for r in state['receipts'] if r['idempotency_key'] == key), None)
        if previous and previous['request_hash'] != fingerprint:
            raise HTTPException(409, 'idempotency_body_conflict')
        return previous

    def prepare(self, sid, body):
        fingerprint = digest(body.model_dump(exclude={'idempotency_key'}))
        state = self.snapshot(sid)
        previous = self.existing(state, body.idempotency_key, fingerprint)
        if previous:
            return previous
        if len(state['receipts']) >= 40:
            raise HTTPException(429, 'evidence_receipt_capacity')
        active = state['active']
        corpus_hash = digest(state['sources'])
        if active['artifact']['corpus_hash'] != corpus_hash:
            raise HTTPException(409, 'index_stale_rebuild_required')
        started = time.perf_counter()
        hits = retrieve(active['artifact'], body.query)
        if not hits:
            raise HTTPException(422, 'no_matching_evidence')
        top = hits[0]
        # One cited source makes invalidation selective and inspectable. These are
        # extracts, never a claim that an LLM produced or verified an answer.
        references = [{k: top[k] for k in ('source_id', 'title', 'text', 'revision')}]
        output = top['text'] if body.product == 'answer' else f"확인할 근거: {top['title']}\n□ 적용 내용 확인: {top['text']}\n□ 사용 직전 근거 버전 재검증"
        issued = now()
        receipt = dict(id=str(uuid.uuid4()), product=body.product, query=body.query,
            output=output, references=references, release_epoch=active['epoch'],
            artifact_hash=active['artifact']['artifact_hash'], created_at=issued, expires_at=issued+120,
            idempotency_key=body.idempotency_key, request_hash=fingerprint,
            retrieval_ms=(time.perf_counter()-started)*1000, scope=SCOPE)
        with self.locked(sid) as current:
            previous = self.existing(current, body.idempotency_key, fingerprint)
            if previous:
                return previous
            if current['active']['epoch'] != active['epoch'] or digest(current['sources']) != corpus_hash:
                raise HTTPException(409, 'evidence_changed_during_prepare')
            if len(current['receipts']) >= 40:
                raise HTTPException(429, 'evidence_receipt_capacity')
            current['receipts'].insert(0, receipt)
        return receipt

    def use(self, sid, rid):
        with self.locked(sid) as state:
            receipt = next((r for r in state['receipts'] if r['id'] == rid), None)
            if receipt is None:
                raise HTTPException(404, 'evidence_receipt_missing')
            changed = [ref['source_id'] for ref in receipt['references']
                       if state['sources'][ref['source_id']]['revision'] != ref['revision']]
            deleted = [ref['source_id'] for ref in receipt['references'] if state['sources'][ref['source_id']]['deleted']]
            reason = ('source_deleted' if deleted else 'source_changed' if changed else
                      'release_changed' if receipt['release_epoch'] != state['active']['epoch'] else
                      'receipt_expired' if now() >= receipt['expires_at'] else 'current')
            return dict(valid=reason=='current', reason=reason, affected_sources=sorted(set(changed+deleted)),
                        receipt_id=rid, checked_at=now(), release_epoch=state['active']['epoch'],
                        scope='point-in-time validation; not an atomic external business action')

    def evaluate(self, sid, candidate):
        state = self.snapshot(sid)
        if len(state['reports']) >= 20:
            raise HTTPException(429, 'release_report_capacity')
        report = evaluate_release(state['sources'], candidate)
        artifact = report.pop('artifact')
        report.update(id=str(uuid.uuid4()), corpus_hash=digest(state['sources']),
            base_release_epoch=state['active']['epoch'], artifact_hash=artifact['artifact_hash'],
            model_hash=artifact['model_hash'], index_model_hash=artifact['index']['model_hash'],
            created_at=now())
        with self.locked(sid) as current:
            if digest(current['sources']) != report['corpus_hash'] or current['active']['epoch'] != report['base_release_epoch']:
                raise HTTPException(409, 'evaluation_snapshot_changed')
            if len(current['reports']) >= 20:
                raise HTTPException(429, 'release_report_capacity')
            current['reports'].insert(0, report)
        return report

    def promote(self, sid, report_id):
        state = self.snapshot(sid)
        report = next((r for r in state['reports'] if r['id']==report_id), None)
        if report is None:
            raise HTTPException(404, 'release_report_missing')
        if not report['passed']:
            raise HTTPException(409, 'release_gate_failed')
        # Reconstruct the measured, deterministic JSON artifact outside the lock.
        artifact = build_artifact(state['sources'], report['candidate'])
        with self.locked(sid) as current:
            if (digest(current['sources']) != report['corpus_hash']
                    or current['active']['epoch'] != report['base_release_epoch']):
                raise HTTPException(409, 'release_report_stale')
            if artifact['artifact_hash'] != report['artifact_hash'] or not compatible(artifact):
                raise HTTPException(409, 'release_artifact_changed')
            current['active'] = dict(epoch=current['active']['epoch']+1, artifact=artifact)
            return self.active(current)
