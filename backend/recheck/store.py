"""Short fenced transactions; no database lock is held during model HTTP work.

PostgreSQL uses a row lock. SQLite explicitly begins an IMMEDIATE transaction,
serializing writers across connections and processes (for the local demo only).
"""
from contextlib import contextmanager
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine, delete, event, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feature_version: Mapped[int] = mapped_column(Integer, default=1)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    model_version: Mapped[str] = mapped_column(String(32), default="risk-v1")
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


def versions(row):
    return {"feature_version": row.feature_version, "policy_version": row.policy_version, "model_version": row.model_version}


class Store:
    def __init__(self, settings):
        self.settings = settings
        url = settings.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        sqlite = url.startswith("sqlite:")
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 0.1} if sqlite else {"connect_timeout": 3, "options": "-c statement_timeout=150 -c lock_timeout=100"}, pool_pre_ping=True)
        if sqlite:
            @event.listens_for(self.engine, "connect")
            def pragma(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        # Register all tables even for schema-init processes that import only Store.
        from .evidence import EvidenceState  # noqa: F401
        Base.metadata.create_all(self.engine)
        self.sqlite = sqlite

    @contextmanager
    def transaction(self, write=False):
        with Session(self.engine, expire_on_commit=False) as db:
            if write and self.sqlite:
                db.execute(text("BEGIN IMMEDIATE"))
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def row(self, db, sid, lock=False):
        query = select(DemoSession).where(DemoSession.id == sid)
        if lock:
            query = query.with_for_update()
        row = db.scalar(query)
        if not row or row.created_at + self.settings.session_ttl_seconds <= time.time():
            raise HTTPException(404, "session_missing_or_expired")
        return row

    def create_session(self):
        with self.transaction(write=True) as db:
            if not self.sqlite:
                # Only session allocation needs a global lock to make the retention cap exact.
                db.execute(text("LOCK TABLE demo_sessions IN EXCLUSIVE MODE"))
            db.execute(delete(DemoSession).where(DemoSession.created_at <= time.time() - self.settings.session_ttl_seconds))
            if db.scalar(select(func.count()).select_from(DemoSession)) >= self.settings.max_sessions:
                raise HTTPException(429, "session_capacity_reached")
            now = time.time()
            row = DemoSession(id=str(uuid.uuid4()), feature_version=1, policy_version=1, model_version="risk-v1", created_at=now, updated_at=now)
            db.add(row)
            db.flush()
            return {"session_id": row.id, **versions(row)}

    def reserve(self, sid, key, request_hash):
        with self.transaction(write=True) as db:
            row = self.row(db, sid, lock=True)
            decision = db.scalar(select(Decision).where(Decision.session_id == sid, Decision.idempotency_key == key))
            if decision:
                if decision.request_hash != request_hash:
                    raise HTTPException(409, "idempotency_body_conflict")
                return decision.id, None, decision.payload
            if db.scalar(select(func.count()).select_from(Decision).where(Decision.session_id == sid)) >= self.settings.max_receipts:
                raise HTTPException(429, "receipt_capacity_reached")
            now = time.time()
            decision = Decision(id=str(uuid.uuid4()), session_id=sid, idempotency_key=key, request_hash=request_hash, created_at=now)
            db.add(decision)
            snapshot = {**versions(row), "updated_at": row.updated_at, "created_at": now}
            return decision.id, snapshot, None

    def pending(self, sid, did):
        with self.transaction() as db:
            self.row(db, sid)
            decision = db.get(Decision, did)
            if not decision or decision.session_id != sid:
                raise HTTPException(404, "receipt_missing")
            return decision.payload, decision.created_at

    def finish(self, sid, did, snapshot, receipt, finalize=None):
        with self.transaction(write=True) as db:
            row = self.row(db, sid, lock=True)
            decision = db.get(Decision, did)
            if decision.payload is not None:
                return decision.payload
            if snapshot and receipt["protected"]:
                if versions(row) != {k: snapshot[k] for k in versions(row)}:
                    receipt.update(status="invalidated", reason="versions_changed")
                elif time.time() >= snapshot["created_at"] + self.settings.receipt_ttl_ms / 1000:
                    receipt.update(status="invalidated", reason="expired_at_issue")
                elif time.time() >= row.updated_at + self.settings.feature_ttl_ms / 1000:
                    receipt.update(status="review", reason="feature_stale", risk_score=None)
            if finalize:
                receipt = finalize(receipt)
            decision.payload = receipt
            return receipt

    def mutate(self, sid, kind):
        with self.transaction(write=True) as db:
            row = self.row(db, sid, lock=True)
            if kind == "feature":
                row.feature_version += 1
                row.updated_at = time.time()
            elif kind == "policy":
                row.policy_version += 1
            else:
                epoch = int(row.model_version.split("v")[1])
                if epoch >= 999999:
                    raise HTTPException(429, "model_epoch_capacity_reached")
                row.model_version = f"risk-v{epoch + 1}"
            return versions(row)

    def receipts(self, sid):
        with self.transaction() as db:
            self.row(db, sid)
            return list(db.scalars(select(Decision.payload).where(Decision.session_id == sid, Decision.payload.is_not(None)).order_by(Decision.created_at.desc())))

    def validate(self, sid, did):
        with self.transaction(write=True) as db:
            row = self.row(db, sid, lock=True)
            decision = db.get(Decision, did)
            if not decision or decision.session_id != sid or decision.payload is None:
                raise HTTPException(404, "receipt_missing")
            return self.validity(row, decision.payload)

    def validity(self, row, receipt):
        from datetime import datetime
        reason = "current"
        if versions(row) != {k: receipt[k] for k in versions(row)}:
            reason = "versions_changed"
        elif time.time() >= datetime.fromisoformat(receipt["expires_at"]).timestamp():
            reason = "expired"
        elif time.time() >= row.updated_at + self.settings.feature_ttl_ms / 1000:
            reason = "feature_stale"
        elif receipt["status"] != "clear":
            reason = receipt["reason"]
        return {"valid": reason == "current", "reason": reason, "current_versions": versions(row)}

    def metrics(self, sid, active):
        with self.transaction(write=True) as db:
            row = self.row(db, sid, lock=True)
            receipts = list(db.scalars(select(Decision.payload).where(Decision.session_id == sid, Decision.payload.is_not(None))))
            valid = review = invalidated = 0
            for receipt in receipts:
                validity = self.validity(row, receipt)
                if validity["valid"]:
                    valid += 1
                elif validity["reason"] in ("versions_changed", "expired", "expired_at_issue", "feature_stale") or receipt["status"] == "invalidated":
                    invalidated += 1
                else:
                    review += 1
            values = sorted(r["latency_ms"] for r in receipts)
            import math
            return {"total": len(receipts), "valid": valid, "review": review, "invalidated": invalidated,
                    "p95_ms": values[math.ceil(len(values) * 0.95) - 1] if values else 0, "active": active}
