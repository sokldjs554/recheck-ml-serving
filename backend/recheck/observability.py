"""Per-process Prometheus metrics. Run one Uvicorn process per container.

Route templates, methods, statuses and outcome reasons have bounded vocabularies.
No request/session IDs, exception strings or user values become metric labels.
"""
import asyncio
import json
import time

from fastapi.responses import Response
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

METHODS = frozenset({'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'})
REASONS = frozenset({'no_current_warning', 'risk_signal', 'feature_stale', 'model_unavailable',
    'model_version_mismatch', 'model_executor_unavailable', 'overloaded', 'deadline_exceeded', 'request_cancelled',
    'versions_changed', 'expired_at_issue',
    'deadline_exceeded_after_commit', 'deadline_exceeded_before_admission',
    'receipt_expired_after_commit', 'request_in_progress_retry_same_key',
    'abandoned_request_requires_new_key'})
BUSINESS_ROUTES = {'/api/sessions/{sid}/decisions', '/infer'}


class MetricsMiddleware:
    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] == '/metrics':
            return await self.app(scope, receive, send)
        started, status, chunks, size = time.monotonic(), 500, [], 0
        cancelled = False
        self.metrics.inflight.inc()

        async def measured_send(message):
            nonlocal status, size
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body':
                data = message.get('body', b'')
                size += len(data)
                if size <= 16384:
                    chunks.append(data)
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        except asyncio.CancelledError:
            cancelled, status = True, 499
            raise
        finally:
            self.metrics.inflight.dec()
            route = getattr(scope.get('route'), 'path', 'unmatched')
            method = scope['method'] if scope['method'] in METHODS else 'OTHER'
            labels = (self.metrics.service, method, route, str(status) if 100 <= status <= 599 else 'other')
            self.metrics.requests.labels(*labels).inc()
            self.metrics.duration.labels(*labels).observe(time.monotonic() - started)
            if method == 'POST' and route in BUSINESS_ROUTES:
                payload = {}
                if size <= 16384:
                    try:
                        payload = json.loads(b''.join(chunks))
                    except (ValueError, UnicodeError):
                        pass
                if not isinstance(payload, dict):
                    payload = {}
                outcome = 'cancelled' if cancelled else 'rejected' if status == 429 else 'error'
                if 200 <= status < 300:
                    outcome = payload.get('status', 'success')
                    if outcome not in {'clear', 'review', 'invalidated', 'success'}:
                        outcome = 'other'
                reason = 'request_cancelled' if cancelled else payload.get('reason', payload.get('detail', 'none' if status < 300 else 'unknown'))
                if not isinstance(reason, str) or reason not in REASONS | {'none'}:
                    reason = 'other'
                self.metrics.outcomes.labels(self.metrics.service, outcome, reason).inc()
                self.metrics.business_duration.labels(self.metrics.service, outcome, reason).observe(time.monotonic() - started)


class Metrics:
    def __init__(self, service):
        if service not in {'api', 'model'}:
            raise ValueError('service must be api or model')
        self.service = service
        self.registry = CollectorRegistry()
        labels = ['service', 'method', 'route', 'status']
        self.requests = Counter('recheck_http_requests_total', 'Completed HTTP attempts including errors and rejects', labels, registry=self.registry)
        self.duration = Histogram('recheck_http_request_duration_seconds', 'Time through final ASGI response body including error responses', labels,
            buckets=(.005, .01, .025, .05, .1, .2, .3, .5, 1, 2, 5), registry=self.registry)
        self.inflight = Gauge('recheck_http_inflight', 'In-flight requests excluding metrics scrapes', ['service'], registry=self.registry).labels(service)
        self.business_duration = Histogram("recheck_business_duration_seconds", "Decision/inference duration by delivered outcome", ["service", "outcome", "reason"],
            buckets=(.05, .1, .2, .3, .5, 1, 2, 5), registry=self.registry)
        self.outcomes = Counter('recheck_business_outcomes_total', 'Decision/inference attempt outcomes; retries counted separately', ['service', 'outcome', 'reason'], registry=self.registry)


def install_metrics(app, service):
    metrics = Metrics(service)
    app.state.prometheus = metrics
    app.add_middleware(MetricsMiddleware, metrics=metrics)

    @app.get('/metrics', include_in_schema=False)
    async def metrics_endpoint():
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    if not any(getattr(route, 'path', None) == '/live' for route in app.routes):
        @app.get('/live', include_in_schema=False)
        async def liveness():
            return {'status': 'ok', 'service': service}

    return metrics
