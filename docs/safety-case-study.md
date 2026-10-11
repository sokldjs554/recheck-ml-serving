# From a checked draft to an owned SQL action

The original nine ordered schedules below are retained. A separate [audit and extension](action-comparison-audit.md)
adds controlled concurrent requests, historical replay after source edits, and separately measured normal-path SQL cost.
Those results do not change the sample count or scope of this original experiment.

A support draft cites a transfer document that originally says “300만 원.” A source change can make that draft unsuitable for a new task. Validating it once does not protect a later task record: another transaction can change the source between the check and the write.

RECHECK's guarded operation validates the receipt and appends an immutable synthetic support task under the same session lock and SQL transaction. Source events and release promotions take that lock too. This covers a record owned by this database. It does not send a message, move money, or coordinate an external service.

The [offline experiment](../scripts/evaluate_safety.py) compares three validation placements against identical ordered events and real SQL state. Unsafe implementations exist only in this script; public routes expose only guarded recording.

## Measured results

[Raw evidence: safety-evaluation.json](evidence/safety-evaluation.json) contains the run timestamp, database/runtime versions, source hashes, all receipts, declared expectations, SQL state at submission, individual responses, newly persisted actions and totals. Both SQLite and PostgreSQL were run locally. Each engine independently produced the following results:

| Strategy | Stale commits / 6 stale opportunities | False rejects / 3 valid first actions | Duplicate commits / 1 retry | New records | Rejected submissions | Replays |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trust at creation | 6 / 6 | 0 / 3 | 0 / 1 | 9 | 0 | 1 |
| Check, then act | 5 / 6 | 0 / 3 | 0 / 1 | 8 | 1 | 1 |
| Atomic guarded recording | 0 / 6 | 0 / 3 | 0 / 1 | 3 | 6 | 1 |

Every strategy receives **nine cases and ten submissions per database**: six stale first-action opportunities, three valid first-action opportunities, and one retry. PostgreSQL repeats the same cases on another engine; it does not double the statistical sample. These are deterministic counterexamples, so confidence intervals and a general “accuracy” percentage would be misleading.

All strategies use the same key deduplication. The comparison isolates validation timing, rather than making an unsafe baseline weaker by also removing retries. Zero duplicate records in the two baselines is expected. Separate mutation tests show the evaluator detects duplicate writes if deduplication is removed.

## Exact ordered schedules

Each case starts with a fresh session, the real initial document corpus, the same query (`하루 이체 한도`) and a real retrieved checklist receipt citing `transfer`. “Check” below is the shared check opportunity: only check-then-act validates there. Trust-at-creation relies on issuance; the guarded strategy validates inside its final recording transaction. All mutations use production source/release operations.

| Case | Events after receipt issuance | Expected first action | Trust | Check then act | Guarded |
| --- | --- | --- | --- | --- | --- |
| Current | check → submit | commit | commit | commit | commit |
| Cited edit before check | edit → check → submit | reject `source_changed` | stale commit | reject | reject |
| Cited edit after check | check → edit → submit | reject `source_changed` | stale commit | stale commit | reject |
| Unrelated edit | check → edit `card` → submit | commit | commit | commit | commit |
| Deletion | check → delete cited source → submit | reject `source_deleted` | stale commit | stale commit | reject |
| TTL expiry | check → advance clock to `expires_at` → submit | reject `receipt_expired` | stale commit | stale commit | reject |
| Release change | check → evaluate and promote paired release → submit | reject `release_changed` | stale commit | stale commit | reject |
| Revision ABA | check → text A→B at revision 2 → text B→A at revision 3 → submit | reject `source_changed` | stale commit | stale commit | reject |
| Duplicate submission | check → submit → retry the same key | commit, then replay | commit, replay | commit, replay | commit, replay |

ABA restores identical text but keeps a later revision. It tests provenance identity, rather than only comparing visible text. An unrelated source edit intentionally leaves the cited receipt eligible; rejecting every receipt would fail this experiment.

The clock is controlled only in the offline process by temporarily replacing the existing evidence clock function. The expiry case advances exactly to the 120-second expiration boundary. Session lifetime still uses real time. No production endpoint or testing hook permits a caller to alter time.

## Oracle and regression checks

The expected reason is declared by each schedule independently of `use` and `execute`. The harness records source revision, deletion state, release epoch, expiry boundary and cited-text equality from SQL before submitting. It counts stale and duplicate actions from newly persisted action IDs, including writes accompanying a reported error. A claimed success without a persisted action fails the run. A valid first action that creates no record counts as a false rejection.

[Regression tests](../backend/tests/test_safety_evaluation.py) exercise the whole evaluator with real SQLite records. They then deliberately replace the production call in the test process with three faulty behaviors:

- A blind SQL append: the guardrail reports six stale commits.
- Rejecting everything: it reports three false rejections.
- Changing the key on each retry: it reports one duplicate commit.

These substitutions are negative controls in tests, not application options. The script itself calls the unmodified production `EvidenceStore.execute`. The test suite must fail if the real guarded implementation becomes unsafe. The script exits before writing a success artifact if guarded safety, rejection reasons or retry replay checks fail.

## Reproduce

From the repository root, with the backend dependencies installed:

```bash
backend/.venv/bin/python scripts/evaluate_safety.py
backend/.venv/bin/python -m pytest backend/tests/test_safety_evaluation.py -q
```

The first command creates a temporary SQLite database and replaces the evidence JSON. To measure PostgreSQL too, supply a disposable database URL through an environment variable:

```bash
export SAFETY_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE'
backend/.venv/bin/python scripts/evaluate_safety.py --postgres-url-env SAFETY_POSTGRES_URL
```

The URL is not written into evidence. The runner creates the normal schema if needed and removes only its own sessions and their cascaded records. Use a disposable test database: normal session allocation can expire old sessions as it does in the application. Outputs include random receipt/action IDs and real run metadata; schedule outcomes and totals should match.

## What this establishes—and its bounds

The measured post-check interleavings expose a concrete stale-action failure in a separate check and write. The guarded path rejects those scheduled stale actions while preserving current actions, selective invalidation and one same-key retry. [Atomic action tests](../backend/tests/test_evidence_actions.py) separately exercise actual concurrent event/action serialization and cross-store persistence; this offline report does not claim to measure concurrent stress.

The guarded operation linearizes while holding the database session lock. Receipt expiry is sampled during validation in that transaction; this is not a promise that a physical commit or external consumer finishes before a wall-clock deadline. A replay returns the previously committed historical action, even if its evidence subsequently changes, and does not claim renewed validity.

Nine fixed cases do not establish completeness across arbitrary schedules, crash recovery, distributed services, high load or clock faults. This is not a retrieval-quality benchmark, model-quality result, production SLA, user study or evidence of individual authorship. No human usability findings have been collected here. External effects would need a separate transactional outbox or downstream idempotency/fencing contract; this local record does not supply that contract.
