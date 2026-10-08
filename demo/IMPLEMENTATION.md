# RECHECK interview demo

Korean React 19 / TypeScript / Vite interface. The default mode is an explicitly labeled browser simulation. It computes state transitions locally and uses a synthetic rule, not a Python ML model. No simulated p95, throughput, or production financial benefit is presented.

## Run

```sh
cd demo
npm ci
npm run dev
```

Default development URL: http://localhost:5173. In the demo, select **실제 Python 서버 연결**. Leave API address empty for same-origin hosting, or enter http://127.0.0.1:8000 for local development. Health must return the shared live contract before switching modes. Failed health checks and requests show an error; they never trigger an implicit fallback. Local gateway CORS must allow the frontend origin.

```sh
npm test
npm run build
npm run preview
```

The production output is `dist/`. Root integration serves this output together with `/api` and `/health`. Fonts are local assets, so the UI does not depend on third-party font requests.

## Interactions

- Request synthetic transfer checks, edit the next request amount, inject 0–1000ms delay, simulate deadline and unavailable faults.
- Change feature, policy, or model versions, including while inference is pending. **오래된 판단 재현** injects 220ms delay and mutates the feature after 70ms; no scripted success result is inserted.
- Toggle freshness protection. The intentionally unsafe baseline can emit a stale clear receipt. Independent use-time validation still refuses that receipt.
- Revalidate current use, observe actual receipt expiration, reset into an isolated session, inspect/download receipt JSON, and explore architecture/applicant story tabs.
- The guided walkthrough begins with a clean session and 150000 synthetic amount. Its final stage executes baseline and protection separately. It reports comparison completion only if the returned outcomes establish the counterexample; missing or review results do not become success. The returned receipt must also capture a feature version different from the actual mutation response; a live request that snapshots after mutation does not count as a reproduced stale race.

Browser simulation stores at most 30 visible receipts and 18 UI events per session; its local request ledger admits at most 51 keys. Receipt TTL is 20 seconds in simulation; live mode uses the API's `expires_at`. Displayed browser latency is observed local elapsed time including injected waiting, labeled accordingly. Snapshot and recheck spans without an observable elapsed interval show 0ms. These spans are not presented as Python OpenTelemetry traces.

The open receipt preserves the submitted amount and immutable feature/policy/model snapshot while the scenario input edits the next request. A side-by-side version ledger compares that snapshot with the last confirmed session state. Changed versions receive both a color and a CHANGED label; an unissued receipt shows a dash. The last-confirmed timestamp advances only on successful session creation or mutation, not on UI rerenders. A previously successful validation badge becomes refusal when current versions differ or the receipt expires. Generation checks keep late requests and scheduled mutations from updating a reset session.

## Verification performed

- `npm test`: 10 tests passed. The first 5 lifecycle tests, monotonic-model regression, and 4 presentation regressions were first run failing before their corresponding implementation.
- `npm run build`: TypeScript and production Vite bundle passed.
- Chromium/Playwright acceptance against local frontend and actual Python gateway: clear receipt → validation succeeds → feature change → validation refuses; protected race invalidates; baseline race exposes stale result; JSON download and Escape close work; all tabs and guided comparison work; live API clear and stale rejection work. No browser page errors. Reproduce with `python scripts/check_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8000`; evidence is in `docs/evidence/browser-checks.json` and adjacent PNG files.
- No horizontal overflow at 390px, 768px, and 1024px. Desktop and mobile screenshots inspected. Root integration owns final hosted acceptance and deliverable screenshots.

The first acceptance attempt stopped on an overly strict whitespace match for a story heading. The corrected assertion and complete acceptance run passed. The reproducible checker also verifies real 21-second expiry of a previous successful validation, both fault settings, policy/model invalidation, and mobile navigation accessible names.

## Limits and provenance

Browser mode is an educational state machine; it does not claim backend locks, real queue behavior, real ML inference, or real distributed traces. Live mode consumes the exact snake_case shared HTTP contract. The architecture view explicitly distinguishes the Python hosting configuration (SQLite), local Compose PostgreSQL, and the public GitHub Pages browser simulation (memory). Database deployment/benchmark evidence is owned by root/backend integration.

Applicant prose uses only supplied context: junior applicant, Python/LLM/AI-ML experience, investigating recurring AI-coding errors, comparing solutions. It invents no employers, production experience, achievements, or measured business outcomes.

Local font subsets come from Google Fonts' Noto Sans KR and DM Sans, with their SIL Open Font License files included in `public/fonts/`. Source URLs:

- https://github.com/google/fonts/tree/main/ofl/notosanskr
- https://github.com/google/fonts/tree/main/ofl/dmsans

Subset source glyphs include the interface's Korean text and ASCII. Unincluded glyphs use the declared system fallbacks.
