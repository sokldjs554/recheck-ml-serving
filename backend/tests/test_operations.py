import time

from sqlalchemy import create_engine
from recheck.operations import Journal, counters
from recheck.observability import Metrics


def test_journal_survives_new_process_identity_and_retains_failures(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    first = Journal(engine)
    first.append({'id': 'a', 'at': time.time(), 'boot_id': 'boot-a', 'ready': False,
                  'reason': 'model_unavailable', 'api': [], 'model': []})
    second = Journal(engine)
    second.append({'id': 'b', 'at': time.time(), 'boot_id': 'boot-b', 'ready': True,
                   'reason': 'ok', 'api': [], 'model': []})
    rows = second.read()['samples']
    assert [r['ready'] for r in rows] == [False, True]
    assert [r['boot_id'] for r in rows] == ['boot-a', 'boot-b']
    second.append(rows[1])  # retry after ambiguous commit is idempotent
    assert len(second.read()['samples']) == 2


def test_journal_prunes_expired_samples(tmp_path):
    journal = Journal(create_engine(f"sqlite:///{tmp_path / 'ops.db'}"))
    journal.append({'id': 'old', 'at': time.time() - 8 * 86400, 'boot_id': 'a',
                    'ready': False, 'reason': 'old', 'api': [], 'model': []})
    assert journal.read()['samples'] == []


def test_counter_snapshot_keeps_http_200_business_failures_without_identifiers():
    metrics = Metrics('api')
    metrics.requests.labels('api', 'POST', '/api/sessions/{sid}/decisions', '200').inc()
    metrics.outcomes.labels('api', 'review', 'model_unavailable').inc()
    rows = counters(metrics.registry)
    assert any(r['labels'].get('reason') == 'model_unavailable' and r['value'] == 1 for r in rows)
    assert all(r['name'].endswith('_total') for r in rows)
