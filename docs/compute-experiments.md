# Real CPU inference and serving experiments

This experiment measures an actual trained CPU model over real HTTP. It is synthetic portfolio evidence, not production fraud performance, GPU/LLM serving experience, or a capacity guarantee.

## Model and serving contract

The default remains the small deterministic logistic regression (`RECHECK_WORKLOAD=lightweight`, `RECHECK_EXECUTION_MODE=inline`). The opt-in `cpu-ensemble` trains an ExtraTrees ensemble of 128 randomized decision trees on 3,000 deterministic synthetic rows, evaluates point-prediction AUC on a disjoint 1,000-row holdout, and scores 4,096 deterministic uncertainty scenarios per request. Every scenario contributes to the returned expected-risk score; no sleep, dummy burn loop, or injected delay supplies the measured work. Point risk and expected scenario risk receive equal weights. The scenario distribution and returned score are an illustrative synthetic workload, not a validated fraud policy.

`RECHECK_EXECUTION_MODE=process` starts a spawn-based process pool, preloads both artifacts, and executes a real warmup before `/ready` succeeds. `RECHECK_WORKER_CONCURRENCY` bounds both the pool and active inference; `RECHECK_WORKER_QUEUE` bounds admitted waiters. A request deadline/cancellation cancels queued work and injected delay. Once CPU work is submitted, its shielded background task retains the admission slot until the actual executor future completes. Thus timeout is an HTTP deadline, not a claim that operating-system computation stopped. `/live` and `/health` can run while the child computes. Shutdown drains owned tasks and joins the pool.

Model hashes cover trained tree structure/values, scenario offsets, score algorithm, and monotonic deployment epoch. All four benchmark configurations reported the same artifact hashes. Epoch 3 reuses epoch 1 weights with a distinct hash; old receipts remain fenced. API and worker must receive matching `RECHECK_WORKLOAD` configuration. Unexpected model hashes still fail closed.

## Reproduce

```sh
RECHECK_NETWORK_TESTS=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python scripts/benchmark_compute.py --duration 2 --rates 10 30 60 --repeats 2 --output docs/evidence/compute-load.json
```

The benchmark owns and terminates its Uvicorn subprocesses. One or two **separate service instances** receive round-robin requests; each has concurrency 1, queue 2, and a 200 ms deadline. Process mode has one additional CPU child per service instance. Open-loop arrivals preserve every success, rejection, server deadline, late 200, and client error. Goodput counts only HTTP 200 responses received within 200 ms of their **scheduled arrival**, including load-generator scheduling lag. Throughput uses the greater of offered interval and response-drain interval. All-outcome latency percentiles include rejects and failures, so they must be read together with outcome counts and goodput.

Boundary: model-worker HTTP only; gateway, freshness database, and browser latency are excluded. `scripts/benchmark.py` exercises a different gateway/synthetic-delay boundary and must not be pooled with these results. [`compute-load.json.gz`](evidence/compute-load.json.gz) retains per-request results, model spans and hashes, process-tree resource samples, health probes, and configuration. Resources include pool children; summed RSS may double-count shared pages. Single-thread numerical environment variables are set on owned workers.

The complete run recorded **1,600 attempts across 24 cases**. [`compute-summary.json`](evidence/compute-summary.json) contains settings, denominators, outcomes and aggregates without per-request bodies. To unpack the raw archive: `gzip -dc docs/evidence/compute-load.json.gz > work/compute-load.json`.

## Measured results

Two repeats per row; ranges below are the observed repeats, not confidence intervals. Latencies are milliseconds; RSS is maximum summed process-tree MiB.

| Execution | Service instances | Offered rps | Goodput rps | All-outcome p95 ms | Health p95 ms | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
| inline | 1 | 10 | 10.0–10.0 | 54.9–62.6 | 31.2–33.6 | 164 |
| inline | 1 | 30 | 29.8–29.8 | 54.1–61.6 | 25.0–26.6 | 164 |
| inline | 1 | 60 | 1.5–1.8 | 778.9–1875.0 | 246.2–305.5 | 166 |
| inline | 2 | 10 | 10.0–10.0 | 48.9–51.4 | 9.0–15.0 | 324 |
| inline | 2 | 30 | 29.7–29.7 | 52.7–53.3 | 21.8–23.3 | 324 |
| inline | 2 | 60 | 48.3–59.4 | 81.0–222.8 | 41.7–103.2 | 324 |
| process | 1 | 10 | 10.0–10.0 | 82.1–118.9 | 4.3–6.3 | 320 |
| process | 1 | 30 | 20.2–23.9 | 159.9–194.2 | 6.8–20.8 | 320 |
| process | 1 | 60 | 23.6–27.2 | 120.1–168.7 | 4.8–20.0 | 320 |
| process | 2 | 10 | 10.0–10.0 | 88.6–88.9 | 4.1–4.5 | 642 |
| process | 2 | 30 | 29.8–29.9 | 69.5–77.7 | 4.9–6.3 | 642 |
| process | 2 | 60 | 48.1–49.4 | 136.2–141.9 | 5.1–8.9 | 643 |

At 60 offered rps, one inline instance produced only 11 deadline-qualified successes out of 240 attempts across both runs. One isolated instance produced 106/240, while rejecting 132 promptly with HTTP 429; two isolated instances produced 209/240 with 30 HTTP 429. Remaining differences include late 200 responses, all visible in raw records. One inline health probe timed out; isolated probes all succeeded. Process isolation improved overload behavior and health responsiveness in these runs, but increased memory and did **not** improve every low-load or two-instance throughput result. Two inline instances can also distribute CPU work across cores and sometimes served more good requests than two isolated instances.

This shared 5-CPU-affinity host concurrently ran Kubernetes/monitoring setup. The two-second runs have scheduling noise and should not be used to size production. Re-run longer after other work settles before making purchasing decisions. More replicas multiply model/pool memory; a second isolated service used approximately twice the memory of one. No cloud charge or paid deployment was incurred, and no dollar-per-request claim is inferred without an actual provider price and sustained workload.

## Verification and limitations

55 backend tests passed including real socket/process freshness races, CPU cancellation occupancy, a 1 ms CPU deadline retaining admission, deterministic ensemble scores, epoch/hash fencing, and health progress during active CPU work. The prior HTTP freshness race now constructs and warms its observer **before** starting the 50 ms request, requires an observed active worker, and waits for observed admission drain instead of a fixed post-timeout sleep. The delay was not increased. Five additional consecutive real-HTTP race runs passed; command output is saved in [`compute-verification.json`](evidence/compute-verification.json).

CPU cancellation is cooperative only before submission; running pool work finishes naturally. Fixed bounded scenario size makes that finite. An unexpected process-pool child exit makes inference and `/ready`, `/health`, and `/live` return 503; the supervisor can replace the worker. A real test kills an owned idle CPU child and verifies readiness fails before the next inference, then checks the 503 response and released admission. Idle failure detection reads CPython’s pool-manager broken flag because the executor lacks a public idle-health API; public `BrokenProcessPool` handling provides a submission/result fallback. Lifespan cleanup also covers warmup failure. A hung native process still requires supervisor recovery; this is not a hard per-job process-kill architecture. The short load series and operational tests do not establish an availability SLA, multi-host availability, GPU efficiency, real customer traffic, or long-term reliability.

## Longer confirmation and sustained observation

The subsequent confirmation used **60 offered rps for 10 seconds, twice per configuration**, adding 4,800 attempts. The CPU profile then ran for **60 seconds at 60 rps with two isolated service instances**, adding 3,600 attempts. A lower offered-rate check ran the final pool-failure-fixed code for **30 seconds at 30 rps**, adding 900 attempts. Across the initial and later series, **10,900 attempt records** are preserved. These are distinct runs; they are not aggregated into an availability claim.

```sh
backend/.venv/bin/python scripts/benchmark_compute.py --duration 10 --rates 60 --repeats 2 --output work/operations/compute-confirmation.json
backend/.venv/bin/python scripts/benchmark_compute.py --modes process --replicas 2 --duration 60 --rates 60 --repeats 1 --output work/operations/compute-sustained.json
backend/.venv/bin/python scripts/benchmark_compute.py --modes process --replicas 2 --duration 30 --rates 30 --repeats 1 --output work/operations/compute-capacity.json
```

| Confirmation execution | Instances | On-time / attempted, both repeats | Goodput rps range | Health p95 ms range | Peak process-tree RSS MiB |
|---|---:|---:|---:|---:|---:|
| inline | 1 | 6 / 1200 | 0.00–0.50 | 1003.7–1003.7 | 163.4 |
| inline | 2 | 636 / 1200 | 3.41–59.76 | 39.0–342.4 | 325.3 |
| process | 1 | 579 / 1200 | 28.51–28.98 | 3.6–5.5 | 322.0 |
| process | 2 | 1050 / 1200 | 48.88–55.46 | 4.6–7.0 | 642.0 |

One inline instance recorded 614 client read timeouts across its two longer runs; these remain failed attempts. Two inline instances varied sharply between repeats (600/600 and 36/600 on time), illustrating how little CPU scheduling headroom remained. The isolated instances rejected overload promptly and kept health responsive, but did not make excess traffic successful.

| Two isolated instances | 60 rps × 60 s | 30 rps × 30 s |
|---|---:|---:|
| On-time success / all attempts | 2,572 / 3,600 (71.44%) | 896 / 900 (99.56%) |
| HTTP outcomes | 2,720×200; 775×429; 105×504 | 896×200; 1×429; 3×504 |
| Goodput | 42.78 rps | 29.81 rps |
| All-outcome p95 | 221.3 ms | 90.0 ms |
| Health p95; failures | 12.8 ms; 0 | 6.4 ms; 0 |
| Mean owned CPU cores | 1.74 | 1.12 |
| CPU ms per good response | 40.67 | 37.70 |
| Peak summed RSS | 644.75 MiB | 621.31 MiB |
| First / last quarter mean RSS | 643.76 / 644.75 MiB | 620.44 / 621.08 MiB |
| Maximum active / admitted per replica | 1 / 3 | 1 / 3 |
| Final active / admitted per replica | 0 / 0 | 0 / 0 |

The one-minute run shows bounded admission and about 1 MiB growth between first/last quarter mean RSS, consistent with bounded trace-buffer warmup over this interval. It does not prove absence of long-term leaks. All health probes succeeded, even while 28.56% of offered attempts missed the inference objective.

**Capacity decision for this experiment:** use two isolated instances when control-plane responsiveness and predictable rejection under overload matter. Budget about 650 MiB of summed worker/pool RSS (API/database and container overhead excluded) plus CPU headroom. Treat **30 offered rps total** as the measured provisional operating point: the 900-attempt check achieved 99.56% within the stricter worker-only 200 ms objective. It consumed 4 of a hypothetical 9 bad-attempt budget for a 99% objective. Sixty offered rps is explicitly **outside** that objective: the sustained run had 1,028 bad attempts against a 36-attempt budget (28.56× budget burn). The application’s separately documented 300 ms, 30-day end-to-end SLO is a different measurement boundary and is not established by this worker test.

A second isolated service approximately doubles memory and CPU capacity on this host; it does not demonstrate independent-host high availability. Provider costs must be calculated from the actual selected instance price: `monthly worker cost = replica count × provider monthly price`, and `worker cost per million good responses = hourly worker cost × 1,000,000 / (3,600 × sustained goodput)`. No dollar figure is asserted from local RSS alone. Repeat at the chosen cloud CPU/memory limits with the gateway/database included before treating this as purchasing or production sizing evidence.

Evidence:

- [10-second repeat summary](evidence/compute-confirmation-summary.json), [all raw confirmation records](evidence/compute-confirmation.json.gz)
- [60-second observation summary](evidence/compute-sustained-summary.json), [all raw sustained records](evidence/compute-sustained.json.gz)
- [30-rps operating-point summary](evidence/compute-capacity-summary.json), [all raw operating-point records](evidence/compute-capacity.json.gz)

Kubernetes control-plane work, image/disk cleanup, monitoring setup and other agents shared the five available CPUs during these runs. Both repeat variability and background interference are part of the reported evidence. No runs or bad outcomes were discarded.

A later full-suite run encountered an unexpected status in the existing admission test while disk space was exhausted. That old assertion did not capture the response body, so its original cause is unknown. Ten diagnostic repetitions then returned only 200/429. The test now prints status/reason diagnostics, allows HTTP 504 only for the API’s two documented deadline responses, still requires an actual 429 overload rejection, preserves all admission bounds, and waits for observed drain. A separate deterministic occupied-gateway test captures `504 deadline_exceeded_before_admission` without entering the worker. After disk cleanup and these test changes, the full suite passed **55 tests in 10.32 seconds**. This sequence is retained in the verification JSON rather than treating the intermediate failure as a proven deadline bug.
