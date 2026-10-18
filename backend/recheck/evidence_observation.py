"""Evidence SQL completion is distinct from delivery of an HTTP response.

Phases are application envelopes, not database-engine wait/commit timings.
The 15s server observation threshold uses CaseApi's wait value but excludes
network transit. It never cancels SQL or guarantees browser delivery.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
import sqlite3
import time

from fastapi import HTTPException
from opentelemetry import propagate, trace
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger('recheck.evidence')
logger.setLevel(logging.INFO)
# Render uses uvicorn's handlers; retain propagation for test/log collectors.
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)

RESPONSE_WAIT_SECONDS = 15.0
_current = ContextVar('evidence_execution_observation', default=None)
BLOCK_REASONS = frozenset({'source_changed', 'source_deleted', 'release_changed', 'receipt_expired'})
KNOWN_REASONS = BLOCK_REASONS | {'action_idempotency_conflict', 'evidence_action_capacity',
    'session_missing_or_expired', 'evidence_receipt_missing'}


def lock_timeout(exc):
    original = getattr(exc, 'orig', None)
    return (getattr(original, 'sqlstate', None) == '55P03' or
            getattr(original, 'sqlite_errorcode', None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})


@contextmanager
def phase(name):
    current = _current.get()
    if current is None:
        yield
        return
    started = time.monotonic()
    current['phase'] = name
    outcome = 'ok'
    try:
        with current['tracer'].start_as_current_span('evidence.' + name):
            yield
    except BaseException:
        outcome = 'error'
        raise
    finally:
        elapsed = time.monotonic() - started
        current['phases_ms'][name] = current['phases_ms'].get(name, 0) + elapsed * 1000
        current['metrics'].evidence_phase.labels(name, outcome).observe(elapsed)


def observe_execute(call, sid, rid, body, request, response, metrics, tracer):
    worker_started = time.monotonic()
    started = request.scope.get('state', {}).get('evidence_http_started', worker_started)
    observation = dict(tracer=tracer, metrics=metrics, phases_ms={}, phase='before_sql')
    token = _current.set(observation)
    outcome, reason, storage, action_id = 'error', 'unexpected', 'unknown', None
    try:
        with tracer.start_as_current_span('evidence.execute', context=propagate.extract(request.headers),
                attributes={'recheck.session_id': sid, 'recheck.receipt_id': rid,
                            'recheck.request_key': body.idempotency_key}) as span:
            trace_id = f'{span.get_span_context().trace_id:032x}'
            request.state.evidence_trace_id = trace_id
            response.headers['X-Recheck-Trace-Id'] = trace_id
            try:
                result = call(sid, rid, body)
                outcome = 'replayed' if result['replayed'] else 'recorded'
                reason, storage, action_id = 'current' if outcome == 'recorded' else 'same_key', 'committed', result['action_id']
                return result
            except HTTPException as exc:
                reason = exc.detail if isinstance(exc.detail, str) and exc.detail in KNOWN_REASONS else 'other'
                outcome = 'blocked' if reason in BLOCK_REASONS else 'rejected'
                storage = 'not_written'
                exc.headers = {**(exc.headers or {}), 'X-Recheck-Trace-Id': trace_id}
                raise
            except SQLAlchemyError as exc:
                outcome = 'lock_timeout' if lock_timeout(exc) else 'db_error'
                reason = outcome
                # Commit acknowledgement can be lost. Only pre-write failures
                # establish no write; a later failure must be reconciled by key.
                storage = 'not_written' if observation['phase'] in {'before_sql', 'lock_acquire', 'state_read'} else 'unknown'
                raise
            finally:
                elapsed = time.monotonic() - started
                budget = 'exceeded' if elapsed > RESPONSE_WAIT_SECONDS else 'within'
                metrics.evidence_outcomes.labels(outcome, reason, budget).inc()
                metrics.evidence_duration.labels(outcome).observe(elapsed)
                span.set_attributes({'recheck.outcome': outcome, 'recheck.reason': reason,
                    'recheck.storage': storage, 'recheck.response_budget': budget})
                if action_id:
                    span.set_attribute('recheck.action_id', action_id)
                logger.info(json.dumps(dict(event='evidence_execution_finished', session_id=sid,
                    receipt_id=rid, request_key=body.idempotency_key, action_id=action_id,
                    trace_id=trace_id, outcome=outcome, reason=reason, storage=storage,
                    response_budget=budget, response_budget_seconds=RESPONSE_WAIT_SECONDS,
                    duration_ms=round(elapsed*1000, 3), dispatch_ms=round((worker_started-started)*1000, 3),
                    worker_ms=round((time.monotonic()-worker_started)*1000, 3), phases_ms=observation['phases_ms']), ensure_ascii=False))
    finally:
        _current.reset(token)
