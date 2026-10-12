# Sustained HTTP → CPU model → PostgreSQL evidence

## Question and measurement boundary

Does a fixed API/model/database deployment remain bounded through repeated overload and recover useful service when offered traffic returns to normal? The new experiment extends `scripts/benchmark_fullpath.py` with a continuous schedule in `scripts/benchmark_fullpath_sustained.py`. It measures `/api/sessions/{sid}/decisions`, including real CPU inference and PostgreSQL receipt transactions. The document-consistency `/evidence/.../execute` flow is a different workload; these numbers do not describe consultation execution.

The same API process, model service, two CPU pool children, PostgreSQL database and 32 sessions survive every phase. There is no restart, scale change, model delay injection, automatic retry, or drain between phases. The only drain occurs after warmup and after the entire measured schedule. Each of two cycles has 30 seconds at 10 rps, 30 seconds at 120 rps, and 30 seconds at 10 rps. The measured interval is 180 seconds; five seconds of HTTP warmup and process startup/model preloading are excluded.

## Measured outcome (2026-10-12)

[Summary](evidence/fullpath-sustained-summary.json) · [all attempts, resource series and final SQL](evidence/fullpath-sustained.json.gz) · [smoke summary](evidence/fullpath-sustained-smoke-summary.json). The main run retained **8,400 measured attempts plus 50 separate warmup attempts**. Warmup produced 50/50 good responses; the six measured phases ran continuously for 180 seconds, with all responses and worker drain complete after 180.034 seconds.

Rates below use the actual 30-second wall windows; the goodput column uses arrival cohorts including their response tails. These denominators differ intentionally at phase transitions. All latency columns include refusals and deferred outcomes.

| Cycle / phase | Target rps | Actual sent / completed rps | Good / offered | Cohort good rps | p50 / p95 / p99 ms | Deferred / HTTP429 / HTTP504 |
|---|---:|---:|---:|---:|---:|---:|
| 1 normal | 10 | 10.00 / 10.00 | 300 / 300 | 10.00 | 41.6 / 68.3 / 80.2 | 0 / 0 / 0 |
| 1 overload | 120 | 120.00 / 119.77 | 2,032 / 3,600 | 67.56 | 98.2 / 185.1 / 228.0 | 1,477 / 91 / 0 |
| 1 recovery | 10 | 10.00 / 10.23 | 300 / 300 | 10.00 | 43.8 / 69.5 / 80.3 | 0 / 0 / 0 |
| 2 normal | 10 | 10.00 / 10.00 | 300 / 300 | 10.00 | 43.5 / 67.0 / 91.9 | 0 / 0 / 0 |
| 2 overload | 120 | 119.73 / 119.30 | 2,040 / 3,600 | 67.65 | 93.6 / 163.9 / 220.2 | 1,506 / 53 / 1 |
| 2 recovery | 10 | 10.27 / 10.70 | 300 / 300 | 10.00 | 41.1 / 60.8 / 74.4 | 0 / 0 / 0 |

There were **5,272 useful on-time results, 2,983 deferred receipts, 144 refusals and one server deadline response**, with zero client timeouts, other errors or late useful HTTP 200s. Both overload intervals achieved only about 56% good responses despite returning many HTTP 200 receipts. Counting every HTTP 200 as successful inference would hide the overloaded model's fallback behavior. All four normal/recovery phases achieved 300/300 good responses, but that observation is not a reliability guarantee.

Overload generator lag p95 was 19.09 and 18.42 ms; p99 was 41.50 and 39.95 ms. Eight arrivals scheduled near the end of the second overload were sent during the following wall window. Their results remain attributed to the overload cohort. Normal/recovery lag p95 ranged 3.61–13.32 ms, so generator scheduling is material even at low offered load.

Both recovery phases had a qualifying first five-second window starting immediately after the rate transition, confirmed after **10 seconds** by a second window. Recovery-phase worker queue samples were all zero; all probes succeeded. The sampled overload queue reached four, and the worker's lifetime counters confirmed peak active **2**, peak admitted **6**, final active/admitted **0/0**. No process or resource scaling was needed to restore the measured 10-rps workload.

API/model process trees used **216.17 CPU-seconds** over the measured interval: 1.20 average owned CPU cores, **41.00 CPU ms per useful on-time response**, and peak summed RSS **652.61 MiB**. First-quarter/last-quarter mean summed RSS was 649.33/652.58 MiB (about +3.25 MiB). This short increase is reported, not treated as a proof of leak freedom. Database/generator resources are excluded.

Final SQL held **8,306 rows**: all **8,305 delivered HTTP 200 receipts matched their complete stored JSON**, one HTTP 504 attempt had committed, and all 144 HTTP 429 attempts had no SQL row. There were **zero duplicate keys, missing/mismatched delivered receipts, pending rows or unexpected rows**. The uncertain commit is retained explicitly: measured request index `7497`, key `e6df1df1-764f-46bf-8217-6f2209e055f7`, returned `504 deadline_exceeded_after_commit` at 303.35 ms scheduled latency; SQL retained receipt `be539dbc-2518-4cd5-a889-1e095bcdc41e`, trace `3b61ee76ae034ac9d48da1699e73d4f1`. Its stored historical status is clear, but it was **not delivered as a useful response** and was counted as a failed deadline attempt. No retry was used to erase that distinction.

Retention remained separate from serving pressure: 32 sessions survived, the largest session held 263 receipts against its 1,000 cap, and the oldest session was 186.32 seconds old against its 485-second TTL. No stale-feature, expired-session or receipt-capacity outcome occurred.

**Decision and cost:** retain process isolation and bounded admission for this demonstrated workload. The fixed resources recovered 10-rps useful service after both overloads; 120 offered rps is outside this run's useful-service envelope. The experiment does not identify a highest safe operating rate between those points. Increasing admission capacity alone would retain more waiting work; it would not add CPU capacity. Additional processes/replicas would require a new measured CPU and memory budget. No paid resource was added.

## Accounting and controls

Every scheduled arrival creates an independent request with a unique idempotency key. A sequential timer dispatches requests without waiting for responses. Per-request scheduled, sent and completion times remain in the compressed raw archive. HTTP connection pooling permits 256 concurrent connections; a five-second client timeout bounds outstanding requests. The generator, API, CPU children and database share a host, so scheduling lag is reported rather than assumed absent.

A **good** response is HTTP 200 with `no_current_warning` or `risk_signal`, received within 300 ms of its scheduled arrival. HTTP 200 `review`/fallback receipts are deferred outcomes, not useful model results. The exclusive categories distinguish useful on-time, useful late, HTTP 429 refusal, deferred HTTP 200, server 504, client timeout and other errors. All-outcome and useful-response latency p50/p95/p99 are separate; prompt refusal can lower the all-outcome latency while useful service worsens.

Each phase has both arrival-cohort rates (all eventual results for arrivals scheduled in that phase, divided by phase duration including any response tail) and wall-window rates (actual sends/completions/good completions within that phase's fixed 30 seconds). A completion can fall into the following wall window while retaining its original arrival phase. Target offered rate is separate from both. Raw generator lag captures delayed dispatch.

The process pool has two active slots and four queued slots; API admission allows eight active and eight queued. PostgreSQL's API connection pool has four connections. About every 0.5 seconds the harness samples API/model process-tree CPU and summed RSS, worker active/admitted counts (queue = admitted − active), and API HTTP inflight. API inflight is not a gateway-queue measurement; the gateway queue is not exposed separately. PostgreSQL and generator CPU/RSS are excluded, and summed RSS may double-count shared pages. Probe latency and failures are retained.

The experiment raises session TTL to measured duration + warmup + 300 seconds and feature TTL to the same interval in milliseconds. Receipt cap remains 1,000 per session, with at most 265 offered requests per session including warmup. It records final oldest-session age and maximum stored receipts per session. Warmup receipts are reconciled but excluded from measured rates. The retained 15-second receipt validity does not expire the sessions or remove SQL rows; this benchmark counts delivery at issue time, not later reuse of receipts.

Recovery is deliberately a windowed observation: after each overload, two consecutive complete five-second arrival windows must achieve at least 99% good responses, at least 95% of target sends, p95 scheduled latency no higher than `min(deadline, max(150 ms, first-normal-p95 × 1.5))`, every sampled worker queue at most one, and no probe errors. The report gives the first qualifying window's start and the time at which the second window confirms it. A ten-second confirmation does not mean the system needed ten seconds to drain. No qualifying pair is reported as unconfirmed, not zero recovery time.

Final SQL is read after client responses and worker admission drain. The archive retains every SQL row and compares complete delivered JSON, including IDs and trace evidence. It separately reports missing/mismatched HTTP 200 receipts, duplicate keys, pending SQL rows, unexpected SQL keys, non-200 attempts that nevertheless committed, and non-200 attempts with no row. This catches uncertain commits without retrying and changing evidence.

## Reproduce locally

The harness rejects remote PostgreSQL addresses, database names outside `fullpath_sustained_*`, and any database with pre-existing tables. Create a new dedicated database for **each** run. The repository's PostgreSQL compose credentials are local demo credentials; never point this at a public API or production database.

```sh
# Existing local container, newly allocated disposable database:
docker exec recheck-completion-postgres createdb -U recheck fullpath_sustained_example
export RECHECK_SUSTAINED_DB='postgresql+psycopg://recheck:local-demo-only@127.0.0.1:15432/fullpath_sustained_example'
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_fullpath_sustained.py -q
PYTHONPATH=backend backend/.venv/bin/python scripts/benchmark_fullpath_sustained.py \
  --database-url-env RECHECK_SUSTAINED_DB \
  --output docs/evidence/fullpath-sustained.json.gz
```

The harness owns and terminates its HTTP/model processes, writes raw gzip directly, and emits a companion summary with archive hash and backend/harness source hashes. It does not delete the database. Coordinate other CPU/database measurements first; shared-host interference is a limitation even when other benchmark agents are paused.

## Existing comparison evidence reused

[CPU isolation experiments](compute-experiments.md) already compare inline event-loop inference with process isolation, one/two service instances, and bounded admission at 200 ms worker-only deadlines. The longer confirmation retains all 4,800 attempts: one inline instance achieved 0–0.50 good rps at 60 offered rps, versus 28.51–28.98 for one isolated instance; process isolation roughly doubled summed memory per instance. Two isolated instances achieved 48.88–55.46 good rps with healthy control-plane probes. Those runs had background interference and a worker-only boundary, so their numbers are neither pooled with this experiment nor treated as controlled causal estimates of the full path.

The present experiment evaluates the selected fixed process/admission/deadline configuration over repeated full-path cycles. It does not compare alternate queue sizes or deadlines. Deadline protection may return a response while already-submitted CPU work continues; worker admission remains occupied until actual work ends. Existing cancellation/process-health tests cover this behavior. Local CPU seconds per good response and summed RSS describe resource cost; no cloud bill, monetary efficiency or production capacity is inferred.

## Limits of the observation

The host exposes five affinity CPUs but its cgroup CPU quota is four cores (`cpu.max = 400000 100000`); cgroup memory limit is 16 GiB. These are host/container ceilings, not dedicated reservations for this benchmark. Other measurement agents paused CPU-heavy runs during this slot; unrelated local services still existed. API/model tree resource measurements do not include PostgreSQL, those services, or the load generator.

Two cycles on one continuously running deployment are not independent hosts or statistical confidence intervals. Three minutes can reveal repeated overload behavior and short-term memory/queue trends; it cannot establish absence of long-term leaks, a production SLA, autoscaling performance, cloud hardware capacity, or independent-host availability. No queue-size/deadline tuning sweep is claimed. In particular, the prior worker-only 200 ms evidence and this full-path 300 ms experiment have different boundaries and budgets.
