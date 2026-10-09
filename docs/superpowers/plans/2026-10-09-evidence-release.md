# Evidence release implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. One independent final review.

**Goal:** Turn the supplied sources into a working, inspectable evidence freshness and release demo.
**Architecture:** Session-scoped SQL state, pure retrieval artifacts/gates, FastAPI routes, async SDK and React evidence lab.
**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/NumPy/httpx, React/TypeScript, Playwright.
**Spec:** docs/superpowers/specs/2026-10-09-evidence-release-design.md

## Global Constraints

- Preserve existing inference and deployment flows; no paid API needed.
- Four fictional sources, bounded text and at most 40 receipts/20 reports per session.
- Gates: Recall@1 >= .90, regression <= .05, warm p95 <= 50ms and matching artifacts.
- Every public result states synthetic lexical retrieval scope; no invented experience or bank SLA.
- Session lock for writes; compute outside lock; promotion binds corpus and release epoch.

## Review Focus

- Replayed/deleted/out-of-order events must not resurrect old content.
- Report from another session, changed corpus or old release must not deploy.
- Empty corpus/query, zero vectors and nonfinite measurements fail closed.
- Late HTTP responses after session reset must not display old results as current.
- Public cold start/network failures must remain errors, never simulated successes.

## Task 1: Retrieval and release evaluation

Files: backend/recheck/retrieval.py; backend/tests/test_retrieval.py.
Produces: build_artifact(sources, variant), retrieve(artifact, query), evaluate_release(sources, candidate), artifact compatibility checks.
- [ ] Tests first: paired retrieval; same-dimensional incompatible model/index; degraded Recall; empty corpus; finite latency gate and reproducible hashes.
- [ ] Run failing tests, implement JSON artifacts/actual cosine search and measured gates, run tests, commit.

## Task 2: Persistent lifecycle and SDK

Files: backend/recheck/evidence.py, evidence_routes.py, sdk.py; backend/recheck/api.py; backend/tests/test_evidence.py; examples/answer.py, checklist.py.
Consumes Task 1 artifact/evaluation API; produces /api/sessions/{sid}/evidence state/events/prepare/receipts/{rid}/use/releases/evaluate/releases/{report_id}/promote.
- [ ] Tests first: actual content changes/deletes/replays; cross-session/report isolation; expired and in-flight receipts; stale report/candidate promotion; persistent second Store instance; two SDK consumers.
- [ ] Verify failures, implement SQL JSON row + immutable bounded receipts/reports and atomic fences, run complete backend suite, commit.

## Task 3: Demo, documentation and public verification

Files: demo/src/EvidenceLab.tsx, evidenceApi.ts, styles.css, App.tsx; scripts/check_evidence_browser.py; docs; README; CI pages workflow.
Consumes Task 2 endpoints; UI performs actual Python work and renders measured reports.
- [ ] Write browser acceptance for edit/refusal/rebuild, negative release, shared consumers, exports, mobile, delayed/error responses.
- [ ] Implement dedicated lab, source/receipt comparison, guided steps and release bench; run unit/build + actual browser checks, visually inspect screenshots.
- [ ] Update research mapping, limitations, SDK instructions and interview demo. Rebuild web_static.
- [ ] Independent code review; fix important findings with regression tests.
- [ ] Publish checked changes to GitHub, wait for CI/Render/Pages, verify public interactions; retain evidence and report accurate limits.
