"""The demo waterfall must describe the captured spans, not invent DB latency."""
import importlib.util
from pathlib import Path


def test_trace_view_keeps_worker_parent_and_integer_nanosecond_precision():
    script = Path(__file__).resolve().parents[2] / 'scripts/build_serving_summary.py'
    spec = importlib.util.spec_from_file_location('serving_summary', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view = module.build()['failure']['trace_views']
    failed = view['failed']
    root = next(s for s in failed if s['name'] == 'decision')
    worker = next(s for s in failed if s['name'] == 'model.infer')
    http = next(s for s in failed if s['name'] == 'model.http')
    assert root['start_ms'] == 0
    assert root['duration_ms'] == 23.339256
    assert worker['duration_ms'] == 1.109943
    assert worker['parent_span_id'] == http['span_id']
    assert worker['depth'] == 2
    assert worker['service'] == 'recheck-worker' and worker['status_code'] == 2
    assert not any(s['name'] == 'model.predict' for s in failed)
    assert any(s['name'] == 'model.predict' for s in view['recovered'])
