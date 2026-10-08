# Operations Evidence Implementation Plan

Goal: close each technical portfolio gap with executed, reproducible evidence.
Spec: ../specs/2026-10-09-operations-design.md
Architecture: retain freshness-fenced API; extend bounded model execution and independently test operational infrastructure.
Tech: Python/FastAPI/scikit-learn, PostgreSQL, Kubernetes, Prometheus/Grafana/OTLP, React.

## Global constraints
- No invented production experience or results; free public resources only unless user approves concrete paid option.
- Keep synthetic simulation and actual Python measurements visibly distinct.
- Preserve current API and model epoch/hash contracts.
- Workload/metrics labels are bounded; don't expose session IDs in Prometheus labels.

## Review focus
- Timed-out CPU work must not free admission before execution stops.
- Unknown routes and identifiers must not create unbounded metrics labels.
- Replica failure must not silently reset receipt state or weaken idempotency.
- Bad model readiness must block rollout; rollback must restore real requests.
- Benchmark goodput must exclude rejects, failed and late results.

## Task 1 — actual CPU model and isolated execution
- [x] Test workload identity, event-loop responsiveness and cancellation occupancy, then implement bounded process execution and trained ensemble.
- [x] Remove timing race from real HTTP regression using observed worker state.
- [x] Run regression and repeated real CPU benchmark (baseline/isolated, rates/replicas); preserve every result and resource context.

## Task 2 — telemetry and alert proof
- [x] Test low-cardinality metrics, statuses and errors; install metrics on API/worker through shared hook.
- [x] Add monitoring compose, dashboards, SLO rules, alert sink and runbook.
- [x] Execute scrape, trace export, firing/recovery proof; store machine-readable evidence.

## Task 3 — Kubernetes operational validation
- [x] Create isolated cluster and deploy actual app with persistent DB and replicated services.
- [x] Exercise HTTP, pod recovery, rollout/rollback and persistence; store outcomes.
- [x] Add reproducible commands and CI, document local-host failure boundary.

## Task 4 — public deployment and continued measurement
- [x] Resolve authorized Render workspace, deploy existing free API, inspect status/logs and smoke actual HTTP.
- [x] Implement synthetic uptime checks and scheduled workflow with explicit observation window.
- [x] Link live API/evidence in demo; verify real connection and frontend regressions.

## Task 5 — integrated evidence and review
- [x] Compare resource/cost tradeoffs from measured results; map all job requirements and honest remaining experiential limits.
- [x] Run integrated regression/build/browser/cluster checks; independent code review and necessary fixes.
- [ ] Publish GitHub changes and verify remote CI/Pages/deployment.
