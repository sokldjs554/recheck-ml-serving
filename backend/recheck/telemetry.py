"""Real SDK spans, bounded display buffer, optional OTLP HTTP exporter."""
from collections import OrderedDict
from contextlib import contextmanager
import os
import threading

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult


@contextmanager
def finishing_span(tracer, name, **kwargs):
    """Allow a DB finalizer to close spans before atomically persisting the receipt."""
    with tracer.start_as_current_span(name, end_on_exit=False, **kwargs) as span:
        try:
            yield span
        finally:
            if span.is_recording():
                span.end()


class DisplayExporter(SpanExporter):
    def __init__(self):
        self.traces = OrderedDict()
        self.lock = threading.Lock()

    def export(self, spans):
        with self.lock:
            for span in spans:
                key = f"{span.context.trace_id:032x}"
                records = self.traces.setdefault(key, [])
                if len(records) < 64:
                    records.append({"name": span.name, "start_ns": span.start_time,
                                    "duration_ms": (span.end_time - span.start_time) / 1e6,
                                    "status": "error" if span.status.status_code == trace.StatusCode.ERROR else "ok",
                                    "span_id": f"{span.context.span_id:016x}",
                                    "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None})
                self.traces.move_to_end(key)
            while len(self.traces) > 512:
                self.traces.popitem(last=False)
        return SpanExportResult.SUCCESS

    def records(self, trace_id, start_ns):
        with self.lock:
            return [dict(name=s["name"], start_ms=max(0, (s["start_ns"] - start_ns) / 1e6),
                         duration_ms=s["duration_ms"], status=s["status"]) for s in self.traces.get(trace_id, [])]


def telemetry(service):
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    display = DisplayExporter()
    provider.add_span_processor(SimpleSpanProcessor(display))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(), max_queue_size=512, max_export_batch_size=64))
    return provider.get_tracer("recheck"), display, provider
