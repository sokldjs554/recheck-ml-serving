# Reviewer evidence design

User brief (2026-10-12) supersedes earlier direction. Keep RECHECK and the existing Python backend. Complete verified implementation evidence, not application documents. Latest checked origin/main and clean base: af69d2d.

## Decisions
- Keep CaseFlow above page navigation: views subscribe/unsubscribe; only application teardown or explicit API reconfiguration disposes a flow. Navigation performs no API operation. Explicit restart fences pending responses; expired sessions preserve historical evidence and require a new session explicitly.
- Separate `/evidence/.../execute` (lexical document consistency and SQL action) from `/decisions` (HTTP CPU model serving and SQL receipts). Never label CPU load numbers as the consultation flow's performance.
- Three primary paths, one restrained light interface: execute, serving limits, failure/recovery. Put the purpose and choices at entry; preserve URL deep links. Comparison and raw evidence remain secondary context links; browser simulation is explicitly optional.
- Extend existing experiment harnesses rather than replace architecture. Sustained normal/overload/recovery cycles and contention/state-size matrix run only against isolated local PostgreSQL/API processes. Do not overlap measured CPU experiments. Warmup, expiry, record caps and generator scheduling are measured separately.
- Stored evidence uses question, conditions, outcomes, decision/cost and limitations. Reuse existing process isolation and Kubernetes recovery evidence where sufficient. Add one trace-linked failure narrative with scope and raw identifiers.
- Update README and job-coverage mapping. Preserve failed runs; no invented capacity, SLA or hiring score.

## Acceptance
Navigation during/after execution preserves session, progress, log, receipts and action ID without extra requests. Explicit reset and session expiry are separately tested. Measure offered/sent/completed/useful rates, all outcomes, latency, CPU/RSS/queue, recovery and SQL reconciliation. Cover shared/distinct sessions, concurrency, edit frequency and supported state sizes. Desktop/mobile browser regression and the existing public deployment pipeline must run; unexecutable checks remain explicitly unverified.
