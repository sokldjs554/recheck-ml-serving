# What does guarded SQL execution cost?

The question is whether contention, document edits and a larger supported session JSON change the cost of the atomic evidence action. This experiment exercises `EvidenceStore.execute` directly against isolated local PostgreSQL. It does **not** measure the `/decisions` CPU model, HTTP admission, browser performance or production capacity.

## Conditions

The unchanged store uses a four-connection pool, 300 ms pool timeout, 100 ms PostgreSQL lock timeout and 150 ms statement timeout. Sessions contend on `demo_sessions` row locks; evidence is stored in one JSON payload per session. The harness adds read-only auditing while that lock is held and a separate PostgreSQL connection samples `pg_stat_activity` every 5 ms.

Each matrix cell has three repeats of four completed waves; matrix order rotates between repeats. Each wave sends one execute per worker. Shared sessions send all workers to one session; distinct sessions give each worker its own session. Workers are 1, 4 or 8. Edits affect the cited `transfer` source in no waves, each fourth wave or each second wave (0%, 25%, 50% of **waves**, not request percentages). Each affected session gets one edit in an edit wave. Edits and executes enter the same thread pool; alternating insertion order avoids always putting the edit first. The next wave waits for all operations in the current wave. Therefore the offered load is finite, closed-loop and completion paced; this is not a fixed-rate saturation experiment.

An edit invalidates the original receipt. Subsequent refusals are expected correctness behavior, and faster rejection cannot count as higher useful throughput. There is no automatic receipt rebuild, refresh or retry inside a measured cell. Source revisions remain monotonic, and separate SQL inspection includes actions whose caller saw an operational error. Existing [action workloads](evidence/action-workloads.json) and [`evaluate_action_workloads.py`](../scripts/evaluate_action_workloads.py) cover deduplication, controlled stale-write races and actual lock-timeout retry; this extension adds the cost matrix instead of repeating those experiments.

| Fixture | Receipts | Release reports | Seed actions | Largest measured action count |
|---|---:|---:|---:|---:|
| small | 1 | 0 | 0 | 32 |
| medium | 20 | 10 | 4 | 36 |
| near cap | 40 | 20 | 8 | 40 |

All fixtures are constructed through the existing prepare/evaluate/execute methods using the shipped documents. No arbitrary JSON padding, unsupported document count, expanded retention cap or fake clock is used. The near-cap profile reaches the receipt/report caps before timing and leaves room for 32 new actions. Separate boundary probes attempt action 41, receipt 41, report 21 and a 601-character source. The supported source cap is 600 characters; this run does not maximize every string field or claim a global maximum JSON size.

The four database connections and one normal execute are warmed before measurement. Timers include lazy worker startup, executor queueing, thread scheduling, production validation, JSON work, SQL commit, audit overhead and interaction with server polling. Fixture creation, final SQL inspection, cleanup and sampler connection setup are excluded. Raw samples retain every outcome. Percentiles use nearest rank; aggregate throughput divides the total count by total measured duration. Row-acquisition time includes pool acquisition and SQL execution as well as lock waiting; it is **not** a pure lock-wait duration. Server samples identify observed `Lock` waiters but can miss short waits.

## Measured outcome (2026-10-12)

[Raw requests and SQL evidence](evidence/consistency-costs.json.gz) · [54-cell summary](evidence/consistency-costs-summary.json)

PostgreSQL 16.15, Python 3.12.14, Linux x86-64; 5 logical CPUs reported. The 162 short runs completed 3,240 offered/sent operations: 2,808 executes and 432 edits. Executes produced **2,095 new committed actions, 711 `source_changed` refusals and 2 PostgreSQL lock timeouts**. All edits succeeded. Final SQL contained exactly the 2,095 acknowledged new actions: zero stale writes, duplicates, missing acknowledged actions, unacknowledged actions or refused requests with actions. The two timed-out keys were individually absent from final SQL. `validation.passed` means reconciliation and probes passed; it does not mean every request succeeded.

Initial stored JSON was approximately 49,673–49,678 bytes (small), 120,447–120,488 bytes (medium) and 192,586–192,647 bytes (near cap) in the no-edit cells. Shared near-cap state reached 226,302 bytes after 32 commits. These are actual `octet_length(payload::text)` values, not RAM use or wire sizes. The built-in lexical index already contributes to the small fixture. All four separate boundary probes rejected unsupported requests as expected: action 41, receipt 41 and report 21 returned their specific 429 capacity reasons; a 601-character source failed schema validation.

No-edit results below pool all three repeats; every execute in these cells committed. Latency includes executor queueing and all SQL work.

| Sessions | Workers | State | Execute p50 / p95 (ms) | New actions/s | Row acquisition p95 (ms) | Max sampled lock waiters |
|---|---:|---|---:|---:|---:|---:|
| shared | 1 | small | 5.41 / 7.71 | 175.16 | 2.89 | 0 |
| shared | 1 | near cap | 10.85 / 15.98 | 85.29 | 3.59 | 0 |
| shared | 4 | small | 15.16 / 23.12 | 181.88 | 18.25 | 3 |
| shared | 4 | near cap | 28.59 / 48.06 | 90.96 | 34.18 | 3 |
| shared | 8 | small | 27.13 / 45.55 | 178.13 | 37.89 | 3 |
| shared | 8 | near cap | 52.06 / 86.87 | 91.89 | 73.49 | 3 |
| distinct | 1 | small | 5.67 / 6.67 | 173.68 | 1.66 | 0 |
| distinct | 1 | near cap | 11.57 / 14.38 | 82.56 | 3.39 | 0 |
| distinct | 4 | small | 15.70 / 20.94 | 219.82 | 11.97 | 0 |
| distinct | 4 | near cap | 30.50 / 43.07 | 113.38 | 17.50 | 0 |
| distinct | 8 | small | 25.79 / 43.27 | 218.22 | 26.93 | 0 |
| distinct | 8 | near cap | 51.82 / 78.64 | 111.43 | 56.05 | 0 |

At eight workers, shared near-cap sessions delivered 91.89 new actions/s versus 111.43 for distinct sessions; shared row acquisition p95 was 73.49 ms versus 56.05 ms. The sampler observed up to three lock waiters in shared no-edit runs and none in distinct no-edit runs. Increasing a one-worker shared fixture from small to near cap raised p95 from 7.71 to 15.98 ms and reduced throughput from 175.16 to 85.29 actions/s. These associations demonstrate measurable costs in this setup; they do not separate JSON serialization from other per-session work.

With eight workers and near-cap state, the edit-frequency tradeoff was:

| Sessions | Waves with edits | Edit requests | Commits / refusals (of 96 executes) | Execute p95 (ms) | Completed executes/s | New actions/s |
|---|---:|---:|---:|---:|---:|---:|
| shared | 0% | 0 | 96 / 0 | 86.87 | 91.89 | 91.89 |
| shared | 25% | 3 | 87 / 9 | 99.10 | 89.44 | 81.06 |
| shared | 50% | 6 | 39 / 57 | 88.35 | 100.82 | 40.96 |
| distinct | 0% | 0 | 96 / 0 | 78.64 | 111.43 | 111.43 |
| distinct | 25% | 24 | 78 / 18 | 106.48 | 98.88 | 80.34 |
| distinct | 50% | 48 | 35 / 61 | 173.46 | 74.43 | 27.14 |

More frequent source changes lowered useful throughput because the old receipt became invalid. Distinct sessions require more total edits to apply the same per-session frequency, so the table retains edit counts rather than treating the two shapes as equal request mixes. The shared near-cap 50% case completed executes faster than its no-edit case while committing less than half as many actions per second; that is cheaper refusal, not improved useful capacity.

The two lock timeouts occurred in **shared / 8 workers / medium / edit each fourth wave / repeat 1** (zero-based repeat). Both had SQLSTATE `55P03`; request latencies were 125.06 and 128.16 ms. Session `a0b918cd-4ae3-4b64-acc6-e05c2763f3c2`, keys `matrix-2-3` and `matrix-2-4`, had no final action. The timeout happened before the scheduled edit, so it is not a source-change refusal. This transient is retained even though the other repeats completed without timeout. There were no statement timeouts. No retry was included in this matrix; the existing controlled lock-timeout workload supplies separate retry evidence.

**Decision and cost:** keep the atomic guard and current bounded demo state, expose refusal and timeout outcomes, and avoid interpreting more concurrent callers as proportional useful throughput. This evidence does not justify removing locks, increasing caps or rewriting JSON storage. A storage redesign would need a longer controlled comparison that holds state shape and arrival rate constant while separately profiling serialization, pool wait and database lock duration.

## Reproduction

Use a dedicated local database named `recheck_consistency*`; the script rejects non-loopback hosts and other database names. The database must be disposable and owned by the person running the test. Run without other measured CPU workloads on the host.

```sh
docker exec recheck-completion-postgres createdb -U recheck recheck_consistency_20261012
export CONSISTENCY_DATABASE_URL='postgresql+psycopg://recheck:local-demo-only@127.0.0.1:15432/recheck_consistency_20261012'
PYTHONPATH=backend backend/.venv/bin/python scripts/benchmark_consistency_costs.py \
  --repeats 3 --output docs/evidence/consistency-costs.json
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_consistency_costs.py -q
```

The committed raw JSON is gzip-compressed after measurement; the harness writes plain JSON so it can be inspected before compression. Run `gzip -n -f docs/evidence/consistency-costs.json` to produce the published format. Archive and uncompressed hashes are in `evidence/reviewer-local-verification.json`.

The script deletes only sessions it creates. Source hashes, actual PostgreSQL version, environment, parameters, per-request timings/audits, SQL identities, JSON byte sizes/hashes, lock samples and reconciliation accompany the raw report. Full repeated outputs/report bodies are projected out of SQL snapshots; identity and version evidence is retained. Failed reconciliation writes `.failed.json` without replacing successful evidence. The focused harness tests also inject a lost acknowledgment after an actual SQL commit and corrupted stale/duplicate records to check that failed responses cannot disappear from reconciliation.

## Limits on the decision

These are short local repeats with synchronized waves, synthetic documents and one PostgreSQL server. Three repeats do not establish a confidence interval, capacity ceiling or SLA. Shared sessions also accumulate more actions per session than distinct sessions, so their final JSON sizes differ; both initial and final bytes are retained. The four-connection pool, Python scheduling/GIL, JSON load/copy/serialization, SQL execution and lock waiting all contribute. The experiment does not isolate their individual causal costs. Larger payloads or observed lock waits alone do not establish that JSON storage or session locking is the system bottleneck. Receipt expiry, retention-cap refusal and HTTP admission are excluded from the timed matrix; cap boundaries are probed separately.
