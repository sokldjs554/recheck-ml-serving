# Public runtime and its boundaries

The Render Python service uses a dedicated Neon PostgreSQL 17 database in Singapore.
`DATABASE_URL` is injected through Render; credentials never enter the repository.
SQLite remains a local-only convenience. Demo sessions expire after one hour by design;
persistence does not promise unlimited retention or transfer old ephemeral SQLite sessions.

## Database and concurrency

The application uses the direct TLS PostgreSQL endpoint because transactions rely on
session-level SQL timeout settings and startup schema initialization. The application
pool is bounded to four connections, no overflow, a 300 ms checkout timeout, and a
240 second recycle interval. Row locks and statements retain the 100/150 ms limits.
Blocking SQL runs outside the asyncio loop. A cancelled transaction is joined before
its admission slot is released; cancellation does not undo a committed receipt.

`verify_public_storage.py` captures an owned synthetic action before redeployment,
then requires a different process boot ID and the same action ID with one stored
record afterward. This is separate from SQL unit tests and the Kubernetes lab.
Fixtures expire with their one-hour sessions; dated evidence is not an evergreen test.

## Public observation

Set `RECHECK_OBSERVE=1`. `/api/operations` returns the latest 120 durable observations.
The observer samples the API's bounded Prometheus HTTP/business counters, worker
counters and dependency readiness every 60 seconds **when request counters changed**.
It does not send traffic to its own public host to prevent sleeping. Data is retained
for seven days. No queries, bodies, credentials or per-user labels are stored.

Counters are cumulative within one boot ID. Never sum cumulative snapshots. HTTP 200
with `model_unavailable` remains visible as a business failure. On database failure,
up to 120 observations wait in memory; the next successful write flushes them. Overflow
is counted. A hard process kill loses unflushed samples. A sleeping/dead host cannot
observe itself, and quiet intervals are unknown. GitHub's external synthetic workflow
continues to record total workflow latency and failure, including first-access delay.

This durable public journal is **not** a hosted Grafana/Jaeger installation. The
separate local observability lab still demonstrates OTLP trace propagation,
Prometheus scraping and alert firing/resolution. Long-term operational experience and
production banking reliability are not claimed.

## Always-on deployment: prepared, not purchased

As checked on 2026-10-12 KST, Render's official pricing lists the `0.5c-512mb` plan
(legacy `starter`, 0.5 CPU / 512 MB) at US$7/month, prorated by running time, before
tax/extra usage. This is the minimum candidate for the existing lightweight demo.
The free runtime still sleeps. Upgrading an existing service requires changing its
compute plan in the Render dashboard; changing this repository's YAML alone does not
prove the live service changed. No paid upgrade has been made without approval.

- Existing service: https://dashboard.render.com/web/srv-db3rmj3ncjis73bi8fl0
- Pricing: https://render.com/pricing
- Plan names: https://render.com/docs/compute-plans-update

After approval: change only this service to the paid plan, verify the live plan and
memory, leave it idle for over 15 minutes, then measure first-access latency without
warming the API first. Keep the failed/slow result if any. Free Neon may also suspend;
no claim of zero cold-start latency is made. CPU ensemble load requires more memory
than 512 MB and stays in the explicitly separate benchmark environment.

## Full-path experiment

`docs/evidence/fullpath-load.json` records all 500 scheduled attempts through real
HTTP API → CPU model/process pool → PostgreSQL. Rates 5/15/30 req/s each ran twice
for five seconds, with a 500 ms end-to-end budget. It retains a 503 in the first
segment; another SQL evaluator was using the same local database in that run.
All 499 HTTP 200 payloads matched SQL records. Separate checks cover model failure,
timeout, client disconnect followed by exact-key retry, conflicting reuse and API
restart. A client disconnect is not falsely described as server-side cancellation.

Reproduce with a disposable PostgreSQL database (never a production database):

```sh
RECHECK_BENCH_DB=postgresql+psycopg://... python scripts/benchmark_fullpath.py \
  --database-url-env RECHECK_BENCH_DB
python scripts/build_fullpath_summary.py
```

RSS/CPU cover API and model process trees, not PostgreSQL; shared memory can be counted
more than once. This short shared-host measurement does not establish public Render
capacity, multi-host scale, or an SLA.

The follow-up saturation run used its own disposable PostgreSQL database, at
60/120 req/s for two seconds twice. Of 480 requests at 120 req/s, 250 were valid
within 500 ms; 17 were HTTP 429 and 213 were HTTP 200 review/overload responses.
The compressed raw JSON retains all 720 attempts, including the 60 req/s cases:
`docs/evidence/fullpath-saturation.json.gz`. Decompress with `gzip -dc`.
All 703 delivered HTTP 200 receipts matched SQL; replay/restart checks passed again.
