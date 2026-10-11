# Evidence case study Implementation Plan

> **For agentic workers:** Use executing-plans and test-driven-development. Independent backend, experiment and frontend tasks use dispatching-parallel-agents; shared interfaces below are fixed.

**Goal:** Turn RECHECK into one understandable, adversarially tested evidence-to-action case study.
**Architecture:** Existing FastAPI/SQL evidence store gains an atomic local task record. React entry orchestrates existing APIs plus execute. Offline evaluation compares three approaches using real SQL and production validation.
**Tech Stack:** Python, FastAPI, SQLAlchemy, React, TypeScript, Playwright.
**Spec:** docs/superpowers/specs/2026-10-11-evidence-case-study.md

## Global Constraints
- No new external dependencies, paid services, fabricated personal work, users or business gains.
- Existing public APIs and advanced labs remain compatible.
- Bound all public records; local actions are not external messages or transfers.
- Compact heading <=22px; mobile 390px and short landscape navigation usable.

## Review Focus
- Late HTTP completion after reset cannot overwrite a new case.
- Failed HTTP never leaves a success claim.
- An idempotent replay of an executed task is historical even after evidence changes.
- Concurrent change/action is serialized on the same session lock.
- No participation or ownership score is inferred from automated tests or notes.

### Task 1: Atomic synthetic task
Files: backend/recheck/evidence.py, evidence_routes.py, backend/tests/test_evidence_actions.py.
Interfaces: POST evidence/receipts/{rid}/execute body {idempotency_key:string}; result {action_id, receipt_id, output, committed_at, release_epoch, references, scope, replayed}. GET evidence/actions returns {actions:[...]}. Invalid evidence HTTP409 detail matches use reason. Reused key with another receipt HTTP409 action_idempotency_conflict; limit40.
- [x] Write endpoint tests for current, changed, deleted, expired, release switch, unrelated edit, retry, conflict, isolation, concurrent event/action.
- [x] Observe missing endpoint failure; implement same-transaction validation and append.
- [x] Run targeted and full backend tests. Document contract/linearization point.

### Task 2: Counterexample evaluation
Files: scripts/evaluate_safety.py, backend/tests/test_safety_evaluation.py, docs/evidence/safety-evaluation.json, docs/safety-case-study.md.
Consumes Task1 execution contract; may use production EvidenceStore directly with typed input.
- [x] Test evaluation detects deliberately unsafe baseline, counts unnecessary rejection and duplicate execution, and fails if guarded implementation is unsafe.
- [x] Implement deterministic event-schedule cases through real SQL and execute guard. No tests-only production hook.
- [x] Run all schedules on SQLite and PostgreSQL where available, preserve per-case outcomes and explain bounded oracle.

### Task 3: Guided first-visit case
Files: demo/src/CaseStudy.tsx, caseStudy.css, caseApi.ts; root integrates App.tsx and browser script.
Interface: default export CaseStudy({defaultBase:string,onExplore:()=>void,onEvidence:()=>void}); onExplore opens freshness, onEvidence opens evidence.
- [x] Test critical async/error behavior or browser actions against actual API.
- [x] Implement explicit steps: connect+draft, edit source, refuse old execution, rebuild+fresh draft, record current task, replay same key.
- [x] Show evidence snapshots/event trail from real responses, outcome explanation and local-only scope, JSON download. Do not fake live results or user reviews.
- [x] Test 390/768/1440 screens, failures, reset, pending disabled actions and downloads.

### Task 4: Narrative, evidence and release
Files: README.md, docs/ownership-workbook.md, docs/usability-protocol.md, docs/verification.md, App integration, CI workflows, web_static.
- [x] Replace stale primary screenshot/narrative with case; link deeper mechanisms and real evaluation.
- [x] Provide concrete mutation/debug exercises and blank human study protocol without claiming either complete.
- [x] Independent whole-change review, fix important findings with regressions.
- [ ] Full suites and actual desktop/mobile screenshots, rebuild fonts/static, publish GitHub and verify public browser checks + Render deploy. Local checks complete; remote release pending.
