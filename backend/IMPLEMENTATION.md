# Python backend implementation and evidence

RECHECK executes an actual scikit-learn classifier through a separate HTTP worker.
The synthetic classifier is a teaching artifact, not a real fraud or credit model.

## Run

Python 3.12 was used for the recorded runs. All dependencies are pinned.

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn recheck.worker:app --host 127.0.0.1 --port 8001
# In a second terminal, from backend:
.venv/bin/uvicorn recheck.api:app --host 127.0.0.1 --port 8000
```

Without configuration, the API uses `sqlite:///./recheck.db`. PostgreSQL is selected
with `DATABASE_URL=postgresql+psycopg://user:password@host:5432/recheck`.
`postgresql://` and `postgres://` URLs are normalized to the psycopg driver.
`MODEL_SERVICE_URL` defaults to `http://127.0.0.1:8001`.

```bash
.venv/bin/pytest -q
# PostgreSQL plus actual gateway/worker subprocesses and sockets:
RECHECK_NETWORK_TESTS=1 \
RECHECK_TEST_DATABASE_URL=postgresql+psycopg://recheck:local-demo-only@127.0.0.1:55432/recheck \
  .venv/bin/pytest -q
```

From the repository root use `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q`.
The PostgreSQL test database must be disposable: tests create synthetic sessions
and decisions, and retain them until the session cleanup policy runs. The socket
test binds random local ports, independently of the demo's 8000/8001 ports.

```bash
.venv/bin/python -m recheck.model --output artifacts
```

This generates `.joblib` artifacts, an artifact-file SHA-256 and a model-parameter
SHA-256. The server reproducibly trains the two small base models at startup rather
than deserializing arbitrary pickles. `model_hash` identifies the deployment epoch,
seed, learned scaler and classifier parameters. It is an identity, not a signature.
The exact serialized artifact hash can differ across library versions.

## Configuration

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `RECHECK_DEADLINE_MS` | 300 | Queue + snapshot + HTTP + final fence budget, maximum 2000 |
| `RECHECK_RECEIPT_TTL_MS` | 15000 | Receipt lifetime from reservation |
| `RECHECK_FEATURE_TTL_MS` | 60000 | Maximum feature snapshot age; feature mutation refreshes it |
| `RECHECK_GATEWAY_CONCURRENCY` | 8 | Active requests per API process |
| `RECHECK_GATEWAY_QUEUE` | 16 | Additional admitted requests per API process |
| `RECHECK_WORKER_CONCURRENCY` | 2 | Active worker requests per worker process |
| `RECHECK_WORKER_QUEUE` | 8 | Additional admitted worker requests per process |
| `RECHECK_MAX_SESSIONS` | 1000 | Exact database session cap |
| `RECHECK_MAX_RECEIPTS` | 100 | Receipts/reservations per session |
| `RECHECK_SESSION_TTL_SECONDS` | 3600 | Session expiry, with cascading cleanup on session allocation |
| `RECHECK_CORS_ORIGINS` | localhost:5173, 127.0.0.1:5173 (HTTP) | Explicit comma-separated browser origins |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Optional real OTLP HTTP trace export |

Request delay injection is capped at 2000 ms; recipient/key lengths, amount and
feature vector shape/range are validated. No retries run behind a timed-out gateway.
The worker applies its own remaining deadline, so a disconnected gateway cannot
leave injected delays running indefinitely. Model prediction itself is a tiny,
synchronous CPU operation; it is never put in an unbounded background thread pool.
Slots stay held until that operation actually ends. A heavier production model
would require a bounded process pool and separate CPU/GPU capacity management.

## Persistence and concurrency

Idempotency reservation, final issuance, mutation and validation lock the same
session row in PostgreSQL with `SELECT ... FOR UPDATE`. SQLite explicitly uses
`BEGIN IMMEDIATE`, serializing writers across processes; it is a convenience
fallback and does not reproduce PostgreSQL's row-level parallelism.

The model HTTP request runs with no database transaction or row lock held.
The final transaction checks all versions, receipt expiry, feature freshness and
remaining deadline while holding the session lock. Trace display and receipt are
committed once, together. A second connection never sees a partially populated
trace or a receipt subsequently rewritten with trace data.

Feature/policy versions increment monotonically. Model versions are monotonic
deployment epochs (`risk-v1`, `risk-v2`, `risk-v3`, ...); two prepared base artifacts
rotate beneath these epochs. This avoids an ABA change reviving an old receipt.
Epoch identity participates in the model hash. The model epoch counter is bounded.

Repeated identical requests return the exact immutable receipt. Reusing a key
with changed input returns HTTP 409, including while the first request is pending.
An owner process crash can leave a pending reservation; retries return HTTP 409
and require a new key after the reservation's deadline. They never execute a
second inference under the old key. Session expiry eventually removes reservations.

Use-time validation always checks the current versions, freshness and expiry,
including for the deliberately unsafe comparison mode (`protected=false`). A clear
decision is evaluated while holding the row lock; the ORM subsequently flushes
and commits while retaining that lock. Time can still advance during durability.
After commit, newly computed clear delivery is rejected with HTTP 504
`deadline_exceeded_after_commit` if its budget is already exhausted, or HTTP 409
`receipt_expired_after_commit` if it already expired. The committed historical
receipt is preserved, so an identical retry returns that exact record without
another model call. Replay is historical retrieval, never a new grant of current
validity; the caller must validate it and use a new key to request a fresh decision.
A subsequent mutation or expiry can also occur before a timely HTTP response
reaches its caller. This is why validation at use remains necessary. Real
transfer/ledger atomicity is outside this demo.

## Observability and semantics

The gateway and worker use real OpenTelemetry SDK spans and W3C HTTP propagation.
Receipt spans are a bounded display copy (512 traces, up to 64 spans per trace);
OTLP retains real distributed span IDs and timestamps. Remote display spans are
positioned relative to the HTTP span so the UI does not assume synchronized clocks.
Unsampled incoming traces and `OTEL_TRACES_SAMPLER=always_off` continue to execute
inference and preserve trace identity, with an empty recorded-span display.
`fence.commit` spans lock acquisition and finalization just before the transaction's
commit. Receipt `latency_ms` measures work through finalization before commit and
HTTP serialization; client-observed load latency also includes these final costs.
The API checks clear delivery again after commit, but the deadline is not an
absolute end-to-end network SLA. Conservative review responses can take slightly
longer than the budget to persist; they never become late clear responses.

API health verifies the worker's prepared model identities. Worker health exposes
measured active/admitted/completed/failure counts and observed peak admission.
Session metrics classify each completed receipt by its current validity and report
a nearest-rank p95 of measured receipt latency. Pending reservations are excluded
from completed totals; `active` includes admitted API work for that session in this
process. Admission caps and active counters are per process, not a distributed
global rate limit. State and idempotency are shared through the database.

Success reasons are `no_current_warning` and `risk_signal`. Failure reasons include
`versions_changed`, `expired_at_issue`, `feature_stale`, `deadline_exceeded`,
`overloaded`, `model_unavailable`, `model_version_mismatch`, `request_cancelled`.
Validation also reports `current` and `expired`. Pre-admission overload, capacity
and pending-conflict responses use HTTP 429/409/504 with JSON `detail`, rather than
inventing a receipt for work the gateway never accepted. Database errors return a
sanitized HTTP 503. The database operations are short synchronous calls with
PostgreSQL statement/lock limits; a slow database can still block the API event
loop within those limits. This tradeoff is documented rather than presented as a
production high-SLA service.

## Recorded verification, 2026-10-08

Initial test-first run: **14 failed in 0.18 s** with explicit assertions that the
gateway and trained model did not exist. Initial green: **14 passed in 2.25 s**.
Further real regressions were observed before fixes:

- model version toggling returned `risk-v1` after two mutations, reviving an old epoch;
- a separate connection observed a committed receipt with an empty trace before a second write;
- a final database row lock let `clear` issuance occur after the request budget;
- worker unavailability was absent from its failure counter.
- slow ORM flush/commit delivered a clear HTTP 200 after 109.8 ms against a 60 ms budget;
- an unsampled W3C parent or `always_off` sampler caused `NonRecordingSpan.start_time` errors.

Each regression now has a passing behavior test. Additional tests cover receipt
expiry during issuance and at use, stale features, simultaneous retries,
changed-body conflicts, session isolation, retention limits, worker overload,
deadline cleanup and cancellation. Independent thread connections exercise
32 concurrent feature mutations, eight concurrent same-key reservations and
30 final-fence/update races; both SQLite and PostgreSQL were exercised.

The opt-in HTTP test starts two actual uvicorn subprocesses, verifies propagated
trace identity, stale-inference fencing, timeout review and eventual remote worker
cleanup. This complements in-process ASGI tests; ASGI cancellation alone is not
used to claim that a remote worker immediately cancels on socket disconnect.

With the pinned environment, synthetic holdout AUC was **0.8601128472** (`risk-v1`)
and **0.8600868056** (`risk-v2`), seed **660065**, 3000 training / 1000 test rows.
These numbers describe the invented data generator only. Model parameter hashes:

- `risk-v1`: `7de0929ba34aefaa313bf15354e6582133992cb755df11094ced0796125521be`
- `risk-v2`: `bf828d9fc64816ed1a8eb6f8832c43a875ac7730e0cf1945c82830f4e034d907`

Final commands and outputs:

- `.venv/bin/pytest -q`: **32 passed, 1 skipped in 3.31 s**. The skip is the opt-in socket/process test.
- `RECHECK_NETWORK_TESTS=1 RECHECK_TEST_DATABASE_URL=postgresql+psycopg://recheck:local-demo-only@127.0.0.1:55432/recheck .venv/bin/pytest -q`: **32 passed, 1 skipped in 5.96 s**. The skip is the isolated SQLite session-capacity fixture; threaded races use PostgreSQL and the process test uses separate HTTP services.
- `.venv/bin/python -m compileall -q recheck`: exit 0.

Additional full-suite evidence is recorded in the integration report. No production
fraud accuracy, GPU performance, transfer approval or Kubernetes execution is
claimed by this backend.
