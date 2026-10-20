# 백엔드 최종 점검과 기술적 판단

2026-10-21 KST. 시작 브랜치 `feat/project-introduction`, 기준 `5a60e88`, 원격 main과 동일하고 미커밋 변경이 없었다. [공식 ML Backend Engineer 공고](https://toss.im/career/job-detail?job_id=6600650003)를 다시 읽고 서버 안정성·모델 서빙·장애 추적·기술 선택의 비용을 대조했다. 이번 범위는 기존 백엔드 결함과 운영 진단 보완이다. UI·모델·저장 구조는 유지한다.

## 점검 결과

| 대상 | 코드에서 확인한 구조 | 이번 실행 / 판단 |
|---|---|---|
| 검사·기록·문서 변경·동일 키 | `EvidenceStore.execute/locked`, `Store.transaction`, 세션 행 잠금과 JSON 저장, 키 충돌 검사 | 기존 동시성·잠금 시간 초과·SQL 실패·재시도 검사를 SQLite와 PostgreSQL에서 다시 통과. 변경 불필요 |
| API 응답과 저장 결과 | evidence의 SQL 완료 로그와 HTTP 연결 종료 로그 분리, GET 목록과 동일 키 재시도. decisions는 저장 후 504여도 기존 receipt 보존 | 실제 socket 연결 종료 후 commit, 응답 유실 후 같은 ID 회복, 저장 후 deadline 경계 회귀 통과. 기존 계약 유지 |
| 무거운 모델의 자원 소유 | worker의 background task가 프로세스 연산 종료까지 슬롯 소유. 큐·주입 지연은 취소 가능 | 실제 CPU 프로세스의 timeout/취소 뒤 슬롯 유지와 pool 사망 후 503·수용 수 0 회귀 통과. 변경 불필요 |
| API SQL·릴리스 평가 취소 | 첫 취소 뒤에는 내부 task를 shield 없이 기다림 | **반복 취소 시 실제 thread가 끝나기 전에 슬롯 반환 재현. 수정함** |
| 공개 health 지연 | 기존 점검은 여섯 요청의 왕복 시간·실패 단계 보존. health 내부 DB/모델 구간과 실패 시 trace 연결은 없음 | **진단 공백 확인. 구간 시간·trace를 보완함**. 과거 지연 원인은 소급 확정하지 않음 |

## 사례 1. 반복 취소 중 SQL 작업 소유권 유지

**문제.** `/decisions`의 실제 `UPDATE decisions` 직전에 SQL thread를 멈추고 요청 task에 두 번 취소를 보냈다. 첫 취소 처리의 `await task`가 두 번째 취소를 내부 task로 전달했다. Python thread는 계속 실행하는데 API admission의 `active`가 **1 → 0**으로 내려갔다. 같은 패턴이 릴리스 평가에도 있었다. 이전 단일 취소 검사만으로는 이 조건을 발견하지 못했다. [최초 실패](evidence/backend-review-2026-10-21/before.log) · [이전 코드 격리 재현: 4개 실패](evidence/backend-review-2026-10-21/cancel-baseline-isolated.log).

**판단.** 즉시 슬롯 반환은 실제 진행 작업 수보다 적게 계측하므로 채택하지 않았다. 작업 큐나 별도 저장 모델을 추가하면 상태·복구 설계가 커진다. 현재 작업 한 개를 소유하는 구조를 유지하면서 모든 대기에서 shield를 적용하는 방법을 선택했다. 취소는 기억하고 실제 thread가 끝난 다음 호출자에게 다시 전달한다.

**구현.** [`task_lifecycle.run_owned_thread`](../backend/recheck/task_lifecycle.py)를 [`api.database_call`](../backend/recheck/api.py)과 [`evidence_routes.evaluate`](../backend/recheck/evidence_routes.py)에 연결했다. 취소 뒤 발생한 예외도 회수하고 예외 종류·작업명·trace ID만 경고 로그에 남긴다. 모델 프로세스의 기존 task 소유권 구조는 변경하지 않았다.

**검증.** [`test_cancellation_ownership.py`](../backend/tests/test_cancellation_ownership.py)는 실제 SQL thread가 멈춘 동안 슬롯 1 유지와 추가 요청 429를 확인한다. thread를 풀고 취소가 전달된 뒤 독립 SQL 연결에서 한 행을 확인하고, 같은 키 재시도의 동일 ID와 모델 완료 횟수 1을 대조한다. 세 번 취소·늦은 예외·릴리스 평가의 활성 2/대기 4 제한도 검사한다. 릴리스 평가 검사는 작업 종료를 통제하기 위해 평가 본문을 대기 함수로 대체하며 실제 모델 성능 측정으로 해석하지 않는다. SQLite·PostgreSQL 전체 회귀는 아래 원문에 연결했다.

**비용과 범위.** 취소한 호출자가 thread 종료까지 더 기다리고 수용 슬롯도 그동안 점유한다. 이것이 과수용을 막기 위해 선택한 비용이다. Python thread를 강제 종료하지 않는다. DB의 기존 pool/statement/lock timeout은 유지하지만 모든 OS·드라이버 정지를 시간 안에 끝낸다는 보장은 없다. 프로세스 강제 종료까지 견디는 작업 큐를 새로 구현한 것은 아니다. reserve 직후 취소되어 결과가 없는 예약은 기존 abandoned/in-progress 계약을 따른다.

## 사례 2. health 지연의 DB·모델 구간 진단

**문제.** 기존 공개 점검의 첫 health 왕복 시간이 길어도 DB 확인과 모델 확인 중 어느 구간인지 분리할 수 없었다. 추론 성공 이후에만 receipt trace가 기록되므로 health에서 응답을 잃으면 서버 로그 연결에 쓸 요청 trace도 없었다. [누락 재현](evidence/backend-review-2026-10-21/monitor-before.log). 기존 단계별 왕복 시간과 실패 분모는 올바르므로 유지했다.

**판단.** 추정한 시작 지연을 원인으로 기록하거나 5초 기준을 늘리지 않는다. 별도 수집 서버를 추가하지 않고 기존 OTel·구조화 로그와 HTTP 응답 헤더를 사용한다.

**구현.** [`health_observation.py`](../backend/recheck/health_observation.py)는 `health.database`, `health.model_http` span과 `health_finished` 로그를 남긴다. 성공·503 응답 모두 trace ID와 `Server-Timing`의 `health_db`, `health_model`, `health_app`을 제공한다. DB 구간은 thread dispatch·connection checkout·SELECT·정리를 포함한 앱 구간이며 네이티브 DB query 시간은 아니다. 모델 구간은 HTTP 확인·응답 검사를 포함하며 모델 추론 시간이 아니다. app 전체는 handler 진입 후 시간이며 호스트 기동·앞단 프록시·클라이언트 왕복을 포함하지 않는다.

[`synthetic_monitor.py`](../scripts/synthetic_monitor.py)는 각 요청 전에 trace ID를 생성해 전달한다. 응답이 없더라도 보낸 ID와 실패 단계·왕복 시간을 보존한다. 응답이 있을 때만 허용된 세 숫자 구간과 형식이 맞는 서버 trace ID를 수집한다. 원문 헤더·URL·본문·자격 증명은 점검 로그에 복사하지 않는다. 새 지표 라벨은 추가하지 않았다. health 성공 JSON 계약과 기존 observer 호출은 유지했다.

**검증.** DB 대기·DB 오류·모델 불가의 응답/로그/span, 실제 별도 API/worker HTTP 프로세스의 요청 trace와 서버 로그 일치, timeout 시 서버 시간을 만들어내지 않는 동작을 검사했다. [실제 로컬 HTTP 표본](evidence/backend-review-2026-10-21/local-http-probe.json) · [동일 trace의 서버 로그](evidence/backend-review-2026-10-21/local-api.log) · [검사 코드](../backend/tests/test_health_diagnostics.py). 6,000ms 성공 표본은 기존 5,000ms 기준에서 여전히 실패한다.

**비용과 범위.** health 호출마다 세 span, JSON 로그 한 줄, 짧은 헤더를 추가한다. 실제 exporter 비용과 로그 저장량은 호출 빈도·배포 설정에 따라 달라진다. 응답을 못 받은 표본에는 서버 구간 값이 없으며 보낸 trace로 서버 로그를 찾아야 한다. 서버에 도달하기 전 실패라면 해당 trace 로그도 없을 수 있다. 왕복 시간에서 app 시간을 뺀 나머지를 곧바로 호스팅 시작 지연이라고 이름 붙이지 않는다.

## 같은 조건의 비용 대조

측정 시점은 원자료의 UTC와 구분해 2026-10-21 KST로 표시한다. 기준 코드 `5a60e88`과 수정 작업 트리를 같은 호스트에서 **이전 → 수정 → 수정 → 이전** 순서로 실행했다. 각 실행은 3회차, 회차마다 5회 준비 후 30회 측정, health/decision 순차 요청, 실제 SQLite, lightweight 모델, ASGI transport, OMP/OpenBLAS 각 1 thread다. 네트워크·공개 호스트·CPU ensemble 부하 용량 측정이 아니다. 소스 해시는 [provenance](evidence/backend-review-2026-10-21/provenance.json)에 남겼다.

| 구간 | 이전 중앙값 / p95 (ms) | 수정 중앙값 / p95 (ms) |
|---|---|---|
| 첫 순서 health | 1.039 / 1.559 | 1.385 / 1.902 |
| 역순 health | 1.028 / 1.368 | 1.537 / 2.181 |
| 첫 순서 decision | 4.311 / 5.332 | 4.515 / 6.589 |
| 역순 decision | 4.237 / 5.501 | 5.491 / 7.022 |

변동을 포함한 관측값이다. health 계측에 추가 비용이 있고 decision 값도 증가했으나, 공유 호스트의 짧은 순차 측정으로 차이 전체의 원인을 helper에 귀속하거나 개선율·용량 저하율을 확정하지 않는다. 각 회차에서 warmup 포함 실제 35행·고유 ID 35개를 확인했다. [이전](evidence/backend-review-2026-10-21/cost-before.json) · [수정](evidence/backend-review-2026-10-21/cost-after.json) · [수정 역순](evidence/backend-review-2026-10-21/cost-after-reverse.json) · [이전 역순](evidence/backend-review-2026-10-21/cost-before-reverse.json).

기존 180초 부하의 **120 req/s는 목표 투입률**, 약 **67.6 req/s는 당시 조건의 유효 응답률**이다. 이번 코드의 처리 용량으로 재측정하지 않았다. [기존 조건·소스](measurement-provenance.md)와 [지속 부하](fullpath-sustained.md)를 그대로 유지한다.

## 이번 검증과 재현

- SQLite + 실제 HTTP·CPU 프로세스: **170 통과 / 45.11초**. [출력](evidence/backend-review-2026-10-21/sqlite.log).
- 격리 PostgreSQL 16 + 실제 HTTP·CPU 프로세스: **169 통과·SQLite 전용 1 제외 / 48.00초**. 제외한 세션 용량·만료 fixture는 위 SQLite 전체 실행에 포함된다. [출력](evidence/backend-review-2026-10-21/postgres.log).
- 프런트 68개 통과, production build와 `web_static` 일치, 기존 safety/serving/fullpath 요약 원문 일치 검사 통과. [프런트](evidence/backend-review-2026-10-21/frontend.log) · [빌드](evidence/backend-review-2026-10-21/build.log). UI 소스·번들은 변경하지 않았다.
- 기존 정합성·동시성·잠금 실패·저장 후504·socket 유실·실제 CPU 슬롯 유지·pool 사망 회귀를 보존했다. 테스트 수는 장기 안정성이나 사용자 이해도의 지표가 아니다.
- 첫 sandbox 내 실행은 완료되지 않아 종료했고, 로컬 thread/socket 실행 권한이 있는 환경에서 재현했다. 추가 baseline 검사 한 번은 pytest의 현재 경로 설정 때문에 수정 코드를 읽어 비교 자료에서 제외했다. 별도 임시 디렉터리에서 이전 코드만 읽도록 격리한 실패 로그를 사용했다.
- 기존 UI 코드 `1893070`의 [Pages·공개 브라우저 실행](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39279555809)은 이번 조회에서 success로 확인했다. 이번 백엔드 변경의 공개 검증으로 합산하지 않는다.

```sh
# Python 의존성 설치 후, localhost socket을 허용하는 환경
PYTHONPATH=backend RECHECK_NETWORK_TESTS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m pytest backend/tests -q
# PostgreSQL은 별도 테스트 DB만 사용. RECHECK_TEST_DATABASE_URL을 지정해 같은 명령 실행.
PYTHONPATH=backend python -m pytest backend/tests/test_cancellation_ownership.py \
  backend/tests/test_health_diagnostics.py backend/tests/test_synthetic_monitor.py -q
# 과거 트리 비교용 백엔드를 별도 디렉터리에 준비
mkdir -p /tmp/recheck-baseline
git archive 5a60e88 backend/recheck backend/model_artifacts | tar -x -C /tmp/recheck-baseline
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python scripts/compare_backend_cost.py \
  --backend /tmp/recheck-baseline/backend --output work/cost-before.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python scripts/compare_backend_cost.py \
  --backend backend --output work/cost-after.json
# 동일 조건에서 위 두 명령을 역순으로도 실행
```

## 운영 기록과 제출에 사용할 사실

Render 실제 `/health` 설정과 free 플랜을 이번에도 조회 확인했다. 10월 13일 첫 표본 약54.04초 실패와 10월19일 첫 표본6.04초 실패는 유지한다. 후자는 health 왕복4.318초를 확인할 수 있지만 당시 내부 구간 계측은 없었다. 새 코드를 그 과거 원인의 증명으로 쓰지 않는다. [버전 확정 당시 운영 조회](usability-feedback-2026-10-19.md#버전-확정과-후속-의견).

제출 문서에 연결할 사례는 **반복 취소 중 실제 작업과 수용 슬롯의 수명 일치**, **응답 유실과 저장 결과 분리(기존 구현 재검증)**, **health 지연의 단계별 근거 확보**다. 관련 문제·선택 이유·코드·실패/통과·비용은 위 항목에 연결했다. 새 모델·상용 HA·은행 규모 트래픽 운영을 구현했다고 표현하지 않는다.

사용자는 주제·방향 결정, 기능 요구·범위 조정, 구체적인 수정 요청, 결과 검토를 담당했다. AI가 코드 작성과 데모 제작을 주로 담당했다. 이번 기술 사례를 사용자의 직접 설계·코딩·실험 경력으로 바꾸지 않는다. 자소서·포트폴리오는 수정하지 않았다.

## 반영 상태

구현 커밋은 [`6053bc397c92a8ad33aefa1e6a23d64cdd7a2bde`](https://github.com/sokldjs554/recheck-ml-serving/commit/6053bc397c92a8ad33aefa1e6a23d64cdd7a2bde)다. 기준 `5a60e88`의 UI·미디어와 기존 부하 실험 출처를 유지했다.

- [필수 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39450678291): success. 원격 PostgreSQL 백엔드 169 통과·SQLite 전용 1 제외, 시간 경계 검사 3회, 모델 인계, 양쪽 DB의 정합성·경합 비교, 프런트 68, 빌드·번들·요약 대조가 모두 완료됐다.
- [API→CPU→PostgreSQL 기존 짧은 회귀](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39450678447): success. 5/30 req/s·각3초·1회인 기존 CI 조건이다. 새로운 지속 처리 용량 근거로 사용하지 않는다.
- [기존 Kubernetes 복구 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39450678013): success. 격리된 kind 검증이며 상용 HA 경험이 아니다.
- Render `dep-dbbon367bikc73b0ek8g`: 위 코드로 2026-10-20 15:43:03 UTC에 live. 실제 `/health`는 유지됐다. [조회·CI 원문 발췌](evidence/backend-review-2026-10-21/remote-verification.json).

### 배포와 겹친 첫 공개 점검 — 실패 보존

[공개 점검 첫 시도](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39450677938/attempts/1)의 세 표본은 15:41:11–15:42:59 UTC다. 기능은 세 번 모두 성공했으나 전체 시간은 **74,118.815 / 1,520.827 / 1,873.182ms**, 첫 health 왕복은 **72,523.711ms**로 5초 기준을 초과했다. 세 표본 모두 새 Render 배포 live 시각보다 앞서고 새 서버 구간 헤더도 없다. 이 결과를 수정 후 서버 성능으로 표시하지 않는다. 첫 지연의 세부 원인은 이 응답만으로 확정할 수 없다.

[실패 포함 모든 표본](evidence/backend-review-2026-10-21/public-attempt-1/synthetic.jsonl) · [분모·기준](evidence/backend-review-2026-10-21/public-attempt-1/summary.json) · [별도 공개 HTTP 기능 확인](evidence/backend-review-2026-10-21/public-attempt-1/public-http-proof.json) · [주입 응답 후 정상 추론·두 SQL 기록·관측 확인](evidence/backend-review-2026-10-21/public-attempt-1/public-observations-proof.json). 뒤의 기능·관측 검사가 성공해도 첫 점검 실패를 성공으로 바꾸지 않는다.

새 서버의 응답 헤더와 trace 연결을 확인하기 위해 배포 완료 후 **동일 코드·동일 기준으로 한 번 재실행**했다. 첫 원본은 위에 보존했으며 이 재실행은 첫 응답 실패를 제거하려는 재측정이 아니다. 후속 결과는 별도 표본으로 아래에 기록한다.


### 배포 완료 후 공개 점검 — 별도 표본

[두 번째 시도](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39450677938/attempts/2)는 15:45:18–15:45:54 UTC의 세 표본이다. 기능과 기존 5초 기준 모두 통과했으며 전체 시간은 **1,773.943 / 1,681.050 / 1,970.063ms**였다. 별도 HTTP 기능 확인과 주입 모델 실패→정상 추론→두 기록 저장→영속 관측 확인도 통과했다. [모든 표본](evidence/backend-review-2026-10-21/public-attempt-2/synthetic.jsonl) · [기준·분모](evidence/backend-review-2026-10-21/public-attempt-2/summary.json) · [HTTP 기능](evidence/backend-review-2026-10-21/public-attempt-2/public-http-proof.json) · [저장·관측](evidence/backend-review-2026-10-21/public-attempt-2/public-observations-proof.json).

첫 health 요청은 클라이언트 왕복 **642.832ms**, 응답의 앱 구간 **9.589ms**, 그중 DB 확인 **6.282ms**, 모델 HTTP 확인 **3.094ms**였다. 요청/응답 trace `6dc27f950f0849579c2a33412c6a956d`를 [실제 Render 로그](evidence/backend-review-2026-10-21/public-health-trace.json)와 대조했고 숫자가 일치했다. 차이를 서버 내부 모델 연산이나 DB commit으로 잘못 설명하지 않도록 분리된 근거가 확보됐다. 나머지 왕복 시간의 DNS/TLS/프록시/전송 등 세부 분해는 이 자료만으로 확인하지 못했다.

이 후속 표본은 배포가 완료되고 서버가 준비된 상태에서 실행했다. 첫 시도의74.12초 실패와 동일한 시작 조건이 아니므로 개선율을 계산하지 않는다. 오래 유휴한 무료 서버의 첫 응답 지연 해결이나 SLA 달성으로 표현하지 않는다. 원본 artifact ID는 각각 `12279455779`(첫 실패 포함), `12278756796`(배포 후)이며 GitHub의 최종 성공 표시와 첫 시도의 실패를 함께 읽어야 한다.

**종료 상태.** 확인된 반복 취소 결함 수정, health 운영 진단 보완, 로컬·원격 필수 회귀, 무료 공개 배포와 실제 trace 대조, README·공고 대응 문서 반영을 완료했다. 이번 백엔드 기술 보완은 종료한다. **무료 공개 환경의 긴 첫 응답 지연은 미해결**이며, 이번 첫 표본의 세부 원인은 새 계측 도입 전이라 확정하지 못했다. 과거 부하 측정은 현 코드의 지속 처리 용량으로 재측정하지 않았고, 강제 프로세스 종료의 작업 복구나 상용 HA까지 확장하지 않았다. UI는 확정 버전을 유지하며 사람의 이해도는 기존 간접 전달된 의견 범위로 남긴다.
