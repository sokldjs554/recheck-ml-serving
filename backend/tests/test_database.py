"""Threaded independent connections exercise actual DB locking, not one event loop."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time

import pytest


def store(tmp_path, **overrides):
    from recheck.config import Settings
    from recheck.store import Store
    return Store(Settings(database_url=os.getenv("RECHECK_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'concurrency.db'}"), **overrides))


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
