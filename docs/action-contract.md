# Atomic local support task contract

`POST /api/sessions/{sid}/evidence/receipts/{rid}/execute` accepts only
`{"idempotency_key":"task-1"}`. The key must contain a non-whitespace character
and be at most 128 characters. It identifies a task request within one session;
keys are compared exactly, including any leading or trailing whitespace.

A successful response is:

```json
{
  "action_id": "generated UUID",
  "receipt_id": "original receipt UUID",
  "output": "original prepared output",
  "committed_at": 1791676800.0,
  "release_epoch": 1,
  "references": [{"source_id": "transfer", "title": "source title", "text": "source snapshot", "revision": 1}],
  "scope": "atomic local synthetic support task recording; no external action",
  "replayed": false
}
```

`committed_at` is a Unix timestamp sampled at the guarded recording decision
inside the transaction, not a database engine's physical commit timestamp.
The response is returned only after the database transaction commits.

`GET /api/sessions/{sid}/evidence/actions` returns `{"actions":[...]}` with
newest records first. Every listed record has `replayed:false`; this describes
the original recording, not current evidence validity. No mutation or deletion
endpoint for action history is exposed. Up to 40 records are retained per
session, without eviction; session expiry and cleanup end their retention.

## Validation and retry

The receipt's cited source revisions, tombstone state, release epoch and expiry
must still be valid. Invalid evidence returns HTTP 409 with the same `detail`
as `/use`: `source_deleted`, `source_changed`, `release_changed`, or
`receipt_expired`, in that priority order. An unrelated document edit does not
invalidate a receipt. Revision ABA (change then restore the text under a newer
revision) remains invalid.

Repeating the same key and receipt returns the original historical action with
`replayed:true`, even after edits, deletion, expiry or a release change. This
does not validate the receipt again or produce another task. Reusing the key
for a different receipt returns HTTP 409 `action_idempotency_conflict`.
A different key intentionally requests a different task, even for the same
receipt. Callers must retain a key across retries.

A missing or another session's receipt returns HTTP 404
`evidence_receipt_missing`. A missing or expired session returns HTTP 404
`session_missing_or_expired`. At 40 recorded tasks, a new otherwise-valid task
returns HTTP 429 `evidence_action_capacity`; an existing retry still succeeds.
Invalid request shapes return HTTP 422. Failed validation appends no action.

## Transaction boundary

`EvidenceStore.execute` holds the same session lock used by document events and
release promotion. PostgreSQL locks the `demo_sessions` row with `FOR UPDATE`;
SQLite uses `BEGIN IMMEDIATE`, serializing writers for the local demo. Within
that transaction, execution reads prior keys, validates the current evidence,
and appends the immutable task snapshot to `evidence_states.payload`.

The guarded append is the operation's logical recording point; successful SQL
commit makes it durable before returning. No writer can change the cited
state between this validation and recording. Expiration is judged at that
logical point. If a concurrent edit wins the lock first, execution refuses the
old receipt; if execution wins first, the history contains a valid task that
predates the edit. SQL lock timeouts remain bounded and can return the existing
HTTP 503 `database_unavailable` response; retry with the same key.

This boundary covers only the local synthetic support task record. It sends no
message, transfers no money, and does not coordinate an external system. The
existing `/use` endpoint remains point-in-time validation. Unsafe experiment
baselines are confined to offline scripts and have no public execution mode.

## Verification

`backend/tests/test_evidence_actions.py` exercises the HTTP contract, all four
invalidation reasons, unrelated edits, revision ABA, same-key retries and
conflicts, session isolation, input bounds, capacity and simultaneous retries.
The edit/execute race test holds an actual database lock in one connection and
observes the other connection block on its SQL lock operation, testing both
winning orders. Set `RECHECK_TEST_DATABASE_URL` to exercise the same tests on
PostgreSQL; without it they use isolated SQLite files.
