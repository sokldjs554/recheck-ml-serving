# 공고 요구 → 구현 → 실행 근거 → 한계

기준 공고: [토스뱅크 ML Backend Engineer](https://toss.im/career/job-detail?job_id=6600650003), **2026-10-17 재확인**.
ML Service Team의 AI 제품 백엔드·공통 플랫폼, 연산량이 큰 AI 서비스의 지연·처리량,
분산 환경 장애 추적과 복구 요구에 맞춰 실제 확인할 경로를 연결한다.
Python/Kotlin/Go 중 하나 이상의 경험을 요구하므로 언어 수를 채우기 위한 구현은 추가하지 않았다.

기준 검토 커밋 `af69d2daa9b4d5a71335d7f741fb691c980749d5` 이후 기존 SQL·멱등성·관측·Kubernetes 구현을 재사용했다.
이번 작업은 UI 수명 결함, 반복 지속 부하, 정합성 비용의 측정 공백과 요청 단위 장애 근거를 보완한다.

| 공고 요구 / 평가 질문 | 구현 위치 | 실행 근거 | 보장하지 않는 범위 |
|---|---|---|---|
| Python 백엔드: 어떤 문제를 푸는가 | [`api.py`](../backend/recheck/api.py), [`evidence_routes.py`](../backend/recheck/evidence_routes.py), [`evidence.py`](../backend/recheck/evidence.py) | [실시간 정합성 체험](https://sokldjs554.github.io/recheck-ml-serving/#case): 답변 이후 원문 변경 → 이전 답변 실행 409 → 새 근거 기록 → 같은 작업 ID 재시도 | 합성 상담 문서와 내부 SQL 작업 기록. 실제 상담 발송·송금·금융 원장·LLM 생성 없음 |
| AI 제품을 위한 공통 기능 | [`sdk.py`](../backend/recheck/sdk.py), [`retrieval.py`](../backend/recheck/retrieval.py), [`model_bundle.py`](../backend/recheck/model_bundle.py) | [근거·릴리스 검증](evidence-release.md), [모델 인계](model-handoff.md): 문서 수정/삭제·역순 이벤트, 모델·인덱스 쌍 평가, bundle 무결성·시작 차단 | 작은 TF-IDF fixture와 합성 모델. 실사용 제품 조직의 공통 플랫폼 운영 경험이 아님 |
| 큰 모델 연산과 트래픽에서 서버 보호 | [`execution.py`](../backend/recheck/execution.py), [`admission.py`](../backend/recheck/admission.py), [`worker.py`](../backend/recheck/worker.py) | [180초 전체 경로 지속 부하](fullpath-sustained.md): 같은 자원에서 10→120→10 req/s 두 회차, 유효 응답·보류·거절·지연·RSS·CPU·대기열·회복·SQL 대조 | 개인 공유 호스트 3분 실험. 은행 처리량·장기 안정성·GPU/LLM 용량·공개 호스트 처리량 아님 |
| 안정적인 아키텍처 / 성능과 비용 선택 | [`store.py`](../backend/recheck/store.py), [`evidence.py`](../backend/recheck/evidence.py) | [기존 3방식 SQL 비교](safety-case-study.md), [세션 경합·상태 크기 비용](consistency-costs.md), [CPU 격리 비교](compute-experiments.md) | 전체 JSON 유지·세션 직렬화의 비용을 측정. 측정되지 않은 새 구조의 성능이나 금전적 절감 주장 없음 |
| MSA의 장애 위치 추적 | [`telemetry.py`](../backend/recheck/telemetry.py), [`observability.py`](../backend/recheck/observability.py), [`verify_failure_trace.py`](../scripts/verify_failure_trace.py) | [실패 요청 한 건](failure-walkthrough.md): API 구조화 로그 → 실제 OTLP 모델 exception → review receipt → 독립 PostgreSQL 조회. 기존 Jaeger·Prometheus 검증 재사용 | `fence.commit`은 ORM 커밋 전의 앱 span. 네이티브 SQL span 없음. 로컬 trace 수신 실험과 공개 관측은 별도 |
| 장애 최소화 / 복구 확인 | [`infra/k8s`](../infra/k8s), [`k8s_verify.py`](../scripts/k8s_verify.py), readiness/liveness | [기존 DB Pod 교체](kubernetes.md), [복구 타임라인](failure-walkthrough.md): 503 탐지 → 같은 PVC 재기동 → 정상 추론과 기존 기록 확인 | 단일 노드 kind. 실제 은행 온콜, 다중 노드/리전 가용성, 무중단 실적 아님 |
| 높은 SLA·운영 관측에 대한 이해 | [`synthetic_monitor.py`](../scripts/synthetic_monitor.py), [`operations.py`](../backend/recheck/operations.py), Prometheus rules | [공개 API 관측](public-runtime.md): 저장된 점검의 정확성 3/3·5초 내 2/3, 첫 응답 65.1초 실패 보존. 데모에서 운영 기록을 별도 조회 | 주기적 표본 사이 가용성 미확인. 무료 호스트 시작 지연 유지. 장기간 SLA 달성 주장 없음 |
| 문제 해결·성과 지표 / 기술 선택 설명 | [`benchmark_fullpath_sustained.py`](../scripts/benchmark_fullpath_sustained.py), [`benchmark_consistency_costs.py`](../scripts/benchmark_consistency_costs.py) | 전 시도 분모, 시간 예산 내 유효 응답, uncertain commit·최종 SQL, 지연·자원 비용. [설계 판단](decisions.md) | 실험 지표를 실제 고객 효과·매출·업무 시간 절감으로 바꾸지 않음 |
| 평가자가 재현할 수 있는 전달 방식 | [`App.tsx`](../demo/src/App.tsx), [`caseFlow.ts`](../demo/src/caseFlow.ts), [`caseStorage.ts`](../demo/src/caseStorage.ts), [`MeasuredReview.tsx`](../demo/src/MeasuredReview.tsx) | [UI 변경·회귀 근거](workspace-upgrade-2026-10-17.md), [새로고침 복원·후속 검증](reload-recovery-2026-10-17.md). 화면 이동·같은 탭 새로고침 시 확인된 기록과 재시도 키 보존 | 사용자 조사 없이 이해도 향상이 입증됐다고 주장하지 않음. 탭 종료·다른 기기·저장 차단 후 복원과 여러 탭 동기화는 보장하지 않음 |

## 소개 자료의 전달 경로

`da7a26f` 이후 [README와 데모 소개 개선](introduction-update.md)에서 상단 실행 버튼, 실제 로컬 시연 영상, 결과 중심의 부하·복구 화면을 추가했다. 공고 대응 구현과 측정 자체는 재사용했다. [README의 본인 역할과 AI 활용](../README.md#본인-역할과-ai-활용)은 확인된 사용자 역할을 별도로 설명하며 기술 구현 전체를 개인 기여로 표현하지 않는다.

## 공개 반영 근거

구현 커밋 `0b99e35`의 [공개 브라우저 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388240), [전체 회귀](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388408), [Kubernetes 재검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388305)이 모두 통과했다. [배포·검사 기록](evidence/reviewer-public-verification.json). 이 결과는 각 실행의 확인 범위이며 장기 운영 실적이 아니다.

## 측정 경계를 섞지 않기

2026-10-17 보완: [유사 프로젝트·데모 비교](comparative-research-2026-10.md)를 바탕으로 로그 필터·부하 구간 선택·실패/복구 span 탐색을 추가했다. [반영·검증 기록](inspection-update.md).
`scripts/synthetic_monitor.py`는 기존 여섯 HTTP 요청의 단계별 왕복 시간을 남긴다. 새 추론이나 수집 서버를 추가하지 않으며 5초 기준과 실패 보존은 동일하다. [10월 13일 점검 실패](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38328704268)의 원인은 과거 단계별 시간이 없어 여전히 미확정이다.

- **실시간 상담 정합성**: `/api/sessions/{sid}/evidence/receipts/{id}/execute`. 원문·릴리스 최신성 확인과 내부 작업 기록을 같은 트랜잭션에서 수행한다.
- **저장된 CPU 전체 경로 부하**: `/api/sessions/{sid}/decisions` → 별도 CPU 모델 → PostgreSQL receipt. 상담 화면의 처리 성능으로 표시하지 않는다.
- **저장된 worker 단독 비교**: 모델 서버 직접 호출. API·DB가 제외되고 200ms 예산이다. 전체 경로의 300ms 결과와 직접 합산하지 않는다.
- **브라우저 시뮬레이션**: 보조 메뉴에서만 시작하며 실제 API로 표시하지 않는다. 별도 명시적 API 연결 기능을 유지한다.

## 검증 근거와 실제 경력은 다르다

[10/17 공개 운영 점검](operations-2026-10-17.md): 실제 health 타임아웃을 Render 시작 로그와 연결해 모델 준비 전 조기 종료를 확인했다. `scripts/serve_demo.py`의 시작 deadline·종료 처리와 `backend/recheck/model.py`의 불필요한 학습 import를 보완했다. 공개 5초 기준·실패 기록은 유지하며, 무료 호스트 시작 지연 제거와 장기 SLA는 보장하지 않는다.

이 저장소는 개인 실험과 AI 지원 개발의 코드·실행 결과다. 실제 은행 규모의 운영 경력,
장기 SLA, 실사용자 개선·사업 성과, 지원자 본인의 독립적인 설명 능력을 코드 추가로 대신하지 않는다.
이력서·자소서·포트폴리오 문서를 이번 작업에서 작성하지 않았다.

## 조사 이후 화면·근거 연결 개선

[심층 재조사](deep-comparative-research-2026-10-17.md) 이후 [데모 업그레이드](workspace-upgrade-2026-10-17.md)에서 결과 중심으로 세 화면을 재배치했다. [`LoadExplorer.tsx`](../demo/src/LoadExplorer.tsx)는 원본 구간의 응답 분류와 저장 후504의 요청·SQL을 연결하고, [`TraceExplorer.tsx`](../demo/src/TraceExplorer.tsx)는 같은 시간축과 span ID 선택으로 실패·복구 근거를 보여준다. 새 성능 측정·모델·인프라 추가가 아니며 이전 측정 한계를 유지한다.

2026-10-17 후속: [새로고침 복원 최종 검증](reload-recovery-2026-10-17.md)에서 공개 78개(기존 60·Chromium 9·macOS WebKit 9) 통과를 확인했다. Linux CI WebKit의 영상 재생 실패는 별도 미해결 항목으로 보존하며 macOS 통과로 대체해 주장하지 않는다. 같은 탭 복원은 클라이언트의 과거 기록이며 실제 실행의 최신성·중복 검증은 서버에서 수행한다.
