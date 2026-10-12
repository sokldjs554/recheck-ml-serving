# Reviewer Evidence Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration; dispatch independent experiment tasks with superpowers:dispatching-parallel-agents. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make RECHECK's correctness, serving protection and operational recovery assessable from working demos and measured evidence.
**Architecture:** Preserve backend interfaces. Lift CaseFlow lifetime above navigation. Extend experiment harnesses and derive display summaries from raw results; arrange three primary UI routes.
**Tech Stack:** Python/FastAPI, PostgreSQL, CPU process pool, React/TypeScript, Playwright, OpenTelemetry.
**Spec:** ../specs/2026-10-12-reviewer-evidence-design.md

## Global Constraints
No public overload, no extra paid resources, no full backend rewrite. Stored data, live API and simulation have distinct labels. No application documents, invented business impact or SLA. Baseline af69d2d.

## Review Focus
- In-flight navigation and React lifecycle must not cancel/duplicate work.
- Expiry and uncertain commit response retain historical evidence and idempotency key.
- Generator lag, session caps and expiry cannot masquerade as serving capacity.
- Concurrency experiments reconcile final SQL, including uncertain/failed outcomes.
- Mobile navigation and deep links preserve context and expose the same evidence scope.

### Task 1: Persistent case execution
Files: demo/src/App.tsx, CaseStudy.tsx, caseFlow.ts, caseFlow.test.ts; scripts/check_case_browser.py.
- [x] Reproduce navigation reset in browser and retain evidence.
- [x] Add failing reset/expiry/lifecycle assertions; lift flow ownership to app.
- [x] Verify in-flight/completed round trips, explicit reset and expiry without duplicate requests.

### Task 2: Sustained full-path experiment
Files: scripts/benchmark_fullpath.py or focused extension, backend tests for harness accounting, docs/evidence and docs/fullpath-sustained.md.
- [x] Audit and reuse current CPU isolation comparisons.
- [x] Add fixed-resource repeated normal/overload/normal schedule, accounting, queue/resource series and recovery definition.
- [x] Run isolated measurement after resource coordination; reconcile every response and final SQL; preserve raw and summary results.

### Task 3: Contention and failure evidence
Files: scripts/evaluate_action_workloads.py or focused extension, tests; docs/evidence and docs/consistency-costs.md; docs/failure-walkthrough.md.
- [x] Add shared/distinct-session, concurrency/edit-frequency/state-size matrix under supported limits.
- [x] Run separately from CPU experiment and inspect final SQL for stale/duplicate/missing actions.
- [x] Link one failed request through API/model/SQL trace and one existing verified recovery timeline.

### Task 4: UI evidence structure
Files: demo/src/App.tsx, styles.css, CaseStudy.tsx/caseStudy.css, ServingEvidence.tsx/servingEvidence.css; generated summary inputs and builders.
- [x] Capture before desktop/mobile and implement three primary paths with secondary detail navigation.
- [x] Present question/conditions/results/decision/limits and visually separate problem, rejection and saved result.
- [x] Inspect rendered desktop/mobile screens and regress navigation/actions/deep links.

### Task 5: Integrate and publish
Files: README.md, docs/job-coverage.md, affected workflows/browser scripts and web_static.
- [x] Run affected and existing regression suites, evidence consistency checks and browser paths.
- [x] Independent review of changes; resolve findings.
- [ ] Commit, push using established deployment; inspect CI/public demo proof for matching revision.
- [ ] Report changes, costs, measurements, limitations and reproduction links.
