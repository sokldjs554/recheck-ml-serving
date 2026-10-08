# RECHECK serving and operations evidence

Purpose: give interviewers executable evidence for every technical gap identified against Toss Bank ML Backend Engineer. Preserve the Korean version-freshness experiment and honest junior candidate story.

User authorized autonomous completion of all gaps; prior approval-loop rejection remains in force. No paid resources without a concrete price approval. No fabricated customers, business outcomes, long-lived uptime, GPU results, or production experience.

## Deliverables
1. Real computational workload: deterministic trained CPU ensemble, separate from the lightweight default. Bound execution in a process pool, preserve admission occupancy after cancellation until work really ends, keep health responsive. Compare baseline inline vs isolated execution using actual inference rather than sleep. Existing version/hash contracts must hold.
2. Reproducible load: multiple rates/repeats and 1/2 service instances, raw all-outcome records, throughput/goodput, p50/p95/p99, overload/error/deadline rates, capacity/cost assumptions, CPU/memory context. Measure before claiming improvements.
3. Actual Kubernetes lab: fresh isolated local cluster, PostgreSQL persistence, >=2 API/model replicas, probes, rolling update, disruption budget, requests/limits; execute pod replacement, rollout and rollback, report observed gaps. CI reproduces cluster proof. Local nodes share a host and are not production HA.
4. Observability: Prometheus request latency/status/outcome metrics with bounded labels, real OTLP collector/trace backend, Grafana panels, alert rules. Prove scrape, exported cross-service trace, alert firing and resolved transition using owned synthetic traffic. No third-party notifications.
5. SLO/operations: document explicit test SLO and denominator, error budget calculations, synthetic monitor with timestamped append-only evidence, incident/runbook; schedule ongoing checks of owned service once publicly reachable. Availability is a measurement, not guaranteed SLA.
6. Public API: deploy free Render service if account permits; connect actual demo and verify inference/version/trace behavior publicly. Durable PostgreSQL lab and lightweight ephemeral public mode remain distinct. Any unresolved external quota/access block remains explicit.
7. Demo/evidence: accessible Korean interface links to measured experiments, actual-vs-simulation label, clear candidate contribution and limitations; documents map each job requirement to code, command, evidence, limits.

## Interfaces and ownership
Backend workload task owns worker.py/model.py/config.py plus new inference module and tests; metrics task owns api.py plus observability module and wraps worker only through a documented install hook coordinated with backend. Kubernetes owns infra/k8s and scripts/k8s* and workflow. Root owns deploy, evidence integration, demo and final docs.

## Verification
Regression suite, true socket/process tests with event-driven races, baseline/isolated overload test, local cluster acceptance, collector/Prometheus/alert proof, production frontend build and browser checks, public HTTP smoke, independent whole-branch review.
