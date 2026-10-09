# RECHECK: evidence that survives change

The user asked to update the existing project and its actual demo using the two
Toss talks and the LabHub study guide, while preserving an unusual topic and an
honest junior Python/AI portfolio. Implementation and publication are authorized
in this conversation; do not repeat design/deployment approval questions.

## Sources and decision

- Toss Securities tech talk / https://toss.tech/article/tech_talk_talk_3:
  bind embedding model and vector index versions, and ingest real document changes.
- SLASH22 / https://toss.im/slash-22/sessions/3-2: reusable serving boundaries and
  portable model artifacts. This update uses a inspectable JSON retrieval artifact.
- LabHub / https://labhub.hopto.org/blog/culture/2026-03-21-tossbank-ml-backend-engineer-study-guide:
  measure quality/latency and explain tradeoffs. Its example SLAs/stacks are not JD requirements.

Extend the existing receipt/fence idea to two consumers of retrieved evidence:
an answer draft and an operational checklist. Keep the existing inference demo.
Avoid adding GPU/Kafka infrastructure that this small controlled experiment does
not need. Actual Python retrieval, SQL persistence and HTTP SDK calls are required;
no canned scores and no paid LLM API. Outputs are deterministic evidence extracts,
explicitly not LLM generation or real bank policies.

## Contract

A bounded fictional corpus has four source IDs. Versioned update/delete events
change actual content, not just counters. Identical replay is idempotent, older
revisions cannot resurrect deleted content, conflicting same revisions fail.
Each session owns its corpus, release reports and receipts; session expiry and
deletion cascade through the existing Store. All writes lock its session row.
No lock is held during retrieval/evaluation; final writes compare the snapshot.

A JSON artifact contains a fitted character TF-IDF model and cosine-search index.
Model v2 reverses coordinates: dimension alone cannot prove index compatibility.
The manifest binds model parameters, source versions, index vectors and IDs.
This is a transparent lexical retrieval baseline, not neural semantic embedding.

Evaluate a paired candidate, a deliberate model/index mismatch, or a deliberate
query-encoder quality regression. Run the same fixed labeled query set; publish
Recall@1, warm query p95 and raw timing samples. Gates: compatible artifacts,
Recall@1 >= 0.90, regression <= 0.05 against current corpus baseline, p95 <= 50ms.
These are project-local thresholds, not bank SLAs. Reports are server-owned and
bound to corpus digest and active release epoch; promotion checks them again in
a transaction and atomically switches the whole pair. Failed candidates remain
inactive. Concurrent promotion or changed corpus requires reevaluation.

Prepare records exact cited source versions, selected release epoch, expiry and
immutable excerpts. Use-time validation refuses missing/deleted/changed evidence,
expired receipts and superseded releases. Retrieval refuses a dirty index until
a validated rebuild. A successful validation is a point-in-time check, not an
atomic transaction with an external business action.

## Demo and reuse

Add an evidence lab to the existing editorial UI: an editable source document,
the historical answer/checklist, and an event/result timeline. Guide users through
prepare -> edit -> refuse use -> evaluate/rebuild -> fresh receipt. A separate
release bench exposes negative candidates, measurements and the unchanged active
release on failure. Always label this lab as actual Python and show connection,
loading, failure and recovery states. Guard duplicate clicks and late responses.
Export real report JSON. Keyboard/mobile layouts must work at 390/768/1440px.

A small async HTTP Python SDK is used by two runnable example clients. They use
the same receipt lifecycle and fail closed on HTTP errors. SDK proof uses a real
ASGI gateway/database; browser acceptance uses actual HTTP processes.

## Limits

Tiny synthetic corpus and exact query fixtures demonstrate mechanics, not search
quality at scale, regulatory compliance or production experience. Public Render
SQLite remains ephemeral. No claim of business impact, GPU serving, online canary
traffic, automatic quality rollback, LLM hallucination prevention or full video
viewing is introduced.
