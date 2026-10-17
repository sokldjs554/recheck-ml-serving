"""The demo waterfall must describe the captured spans, not invent DB latency."""
import importlib.util
import json
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


def test_commit_exception_is_joined_to_the_actual_sql_row():
    import gzip
    import hashlib
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("serving_summary", Path(__file__).resolve().parents[2] / "scripts/build_serving_summary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = Path(__file__).resolve().parents[2]
    raw_bytes = (root / 'docs/evidence/fullpath-sustained.json.gz').read_bytes()
    raw = json.loads(gzip.decompress(raw_bytes))
    view = module.build()['sustained']
    assert view['raw_sha256'] == hashlib.sha256(raw_bytes).hexdigest()
    cases = view['commit_exceptions']
    assert len(cases) == 1
    case = cases[0]
    assert case['request'] in raw['measurement']['records']
    assert case['sql_row'] in raw['sql_rows']
    assert case['request']['http_status'] == 504
    assert case['request']['phase'] == 4
    for key in ('session_id', 'idempotency_key'):
        assert case['request'][key] == case['sql_row'][key]
