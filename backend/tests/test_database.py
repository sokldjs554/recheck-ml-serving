"""Threaded independent connections exercise actual DB locking, not one event loop."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time

import pytest


def store(tmp_path, **overrides):
    from recheck.config import Settings
    from recheck.store import Store
    db = Store(Settings(database_url=os.getenv("RECHECK_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'concurrency.db'}"), **overrides))
    # These tests verify serialization, not the production 100 ms admission
    # budget. A descheduled lock holder must not turn a correct fence into a
    # flaky assertion. Production timeouts remain unchanged and have separate
    # real-lock HTTP acceptance tests in test_evidence_actions.py.
    from sqlalchemy import event
    @event.listens_for(db.engine, 'checkout')
    def correctness_budget(connection, *_):
        cursor = connection.cursor()
        try:
            if db.sqlite:
                cursor.execute('PRAGMA busy_timeout=5000')
            else:
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SET lock_timeout = '5s'")
                connection.commit()
        finally:
            cursor.close()
    return db


def test_threaded_duplicate_reservation_has_exactly_one_owner(tmp_path):
    db = store(tmp_path)
    sid = db.create_session()["session_id"]
    barrier = threading.Barrier(8)
    def reserve():
        barrier.wait(timeout=2)
        return db.reserve(sid, "same-key", "a" * 64)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: reserve(), range(8)))
    assert len({did for did, _, _ in results}) == 1
    assert sum(snapshot is not None for _, snapshot, _ in results) == 1


def test_threaded_mutations_do_not_lose_version_increments(tmp_path):
    db = store(tmp_path)
    sid = db.create_session()["session_id"]
    with ThreadPoolExecutor(max_workers=8) as executor:
        mutations = list(executor.map(lambda _: db.mutate(sid, "feature"), range(32)))
    assert sorted(m["feature_version"] for m in mutations) == list(range(2, 34))


def test_fence_and_update_race_over_independent_connections(tmp_path):
    from recheck.api import iso
    db = store(tmp_path)
    sid = db.create_session()["session_id"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        for trial in range(30):
            did, snapshot, _ = db.reserve(sid, str(trial), "b" * 64)
            receipt = dict(id=did, session_id=sid, status="clear", reason="no_current_warning", risk_score=0.1,
                           feature_version=snapshot["feature_version"], policy_version=snapshot["policy_version"],
                           model_version=snapshot["model_version"], expires_at=iso(time.time() + 15), protected=True)
            barrier = threading.Barrier(2)
            def finish():
                barrier.wait(timeout=2)
                return db.finish(sid, did, snapshot, receipt)
            def mutate():
                barrier.wait(timeout=2)
                return db.mutate(sid, "feature")
            completed, changed = executor.submit(finish), executor.submit(mutate)
            result, version = completed.result(), changed.result()
            assert result["status"] in ("clear", "invalidated")
            assert version["feature_version"] == snapshot["feature_version"] + 1
            # Regardless of which transaction wins, the old version is unusable
            # after the update commits. There is no impossible revalidation window.
            assert db.validate(sid, did)["valid"] is False


def test_production_lock_timeout_never_publishes_unfenced_receipt(tmp_path):
    """Use unchanged production limits; timeout must roll back before recovery."""
    from recheck.api import iso
    from recheck.config import Settings
    from recheck.store import Store
    from sqlalchemy.exc import OperationalError
    # Deliberately bypass the correctness-only fixture's generous lock budget.
    db = Store(Settings(database_url=os.getenv('RECHECK_TEST_DATABASE_URL', f"sqlite:///{tmp_path / 'timeout.db'}")))
    sid = db.create_session()['session_id']
    did, snapshot, _ = db.reserve(sid, 'timeout-recovery', 'c' * 64)
    receipt = dict(id=did, session_id=sid, status='clear', reason='no_current_warning',
                   risk_score=.1, feature_version=snapshot['feature_version'],
                   policy_version=snapshot['policy_version'], model_version=snapshot['model_version'],
                   expires_at=iso(time.time() + 15), protected=True)
    acquired, release = threading.Event(), threading.Event()
    def hold_mutation():
        with db.transaction(write=True) as connection:
            row = db.row(connection, sid, lock=True)
            row.feature_version += 1
            acquired.set()
            assert release.wait(5)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            held = executor.submit(hold_mutation)
            try:
                assert acquired.wait(3)
                with pytest.raises(OperationalError):
                    db.finish(sid, did, snapshot, receipt)
                assert db.pending(sid, did)[0] is None
            finally:
                release.set()
                held.result(3)
        recovered = db.finish(sid, did, snapshot, receipt)
        assert recovered['status'] == 'invalidated'
        assert recovered['reason'] == 'versions_changed'
        assert not db.validate(sid, did)['valid']
        replay_id, replay_snapshot, replay = db.reserve(sid, 'timeout-recovery', 'c' * 64)
        assert replay_id == did and replay_snapshot is None and replay == recovered
    finally:
        db.engine.dispose()


@pytest.mark.skipif(bool(os.getenv("RECHECK_TEST_DATABASE_URL")), reason="Capacity fixture requires isolated SQLite; DB races above exercise PostgreSQL")
def test_session_capacity_and_expired_session_cleanup(tmp_path):
    from recheck.store import DemoSession
    from fastapi import HTTPException
    db = store(tmp_path, max_sessions=1)
    sid = db.create_session()["session_id"]
    with pytest.raises(HTTPException) as failure:
        db.create_session()
    assert failure.value.status_code == 429
    with db.transaction(write=True) as connection:
        connection.get(DemoSession, sid).created_at = time.time() - 3601
    assert db.create_session()["session_id"] != sid
