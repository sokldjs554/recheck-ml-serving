# 공개 상담 실행의 관측과 저장 결과 확인

2026-10-18 보완. 대상은 `/api/sessions/{sid}/evidence/receipts/{rid}/execute`이며 CPU 모델 부하의 `/decisions`와 별도다. 기존 검증·기록 트랜잭션과 같은 키 재시도를 유지하고 관측을 연결했다.

## 결과와 HTTP 응답의 구분

| SQL 실행 결과 | 분류 | 확인 방법 |
|---|---|---|
| 원문 변경·삭제, 배포 변경, 답변 만료로 차단 | `blocked` + 정해진 사유 | 409, 작업 미생성 |
| 최신 답변으로 새 작업 기록 | `recorded / current` | commit 반환 뒤 작업 ID |
| 같은 요청 키의 기존 작업 반환 | `replayed / same_key` | 원래 작업 ID, `replayed=true` |
| PostgreSQL 55P03 / SQLite BUSY·LOCKED | `lock_timeout` | 잠금 획득 실패, 기록 전 실패 |
| 기타 SQL 처리 실패 | `db_error` | 단계와 `storage` 함께 확인 |

`recheck_evidence_executions_total{outcome,reason,response_budget}`은 SQL 작업 스레드가 끝난 횟수다. 재시도도 별도 시도로 센다. 세션·키·작업 ID·trace ID는 지표 라벨에 넣지 않는다. 고정 분류만 `/metrics`와 기존 운영 기록의 표본에 저장한다.

`recheck_evidence_http_total{outcome}`은 별도의 응답 관측이다. `response_sent`는 ASGI 송신 완료, `failed_response`는 오류 응답, `cancelled`는 애플리케이션 task 취소, `disconnected`는 응답 완료 전 수신한 연결 종료다. 송신 완료만으로 사용자의 수신을 보장하지 않는다. 요청 본문을 모두 받은 execute 경로에서만 종료를 감시하고, 감시 task는 요청 종료 시 정리한다. 연결 종료로 진행 중 SQL 작업을 강제 중단하지 않는다.

## 시간 구간과 비용

- `dispatch_ms`: middleware 진입부터 동기 작업 스레드 시작까지. 요청 파싱·디스패치 대기를 포함한다.
- `evidence.lock_acquire`: SQLite `BEGIN IMMEDIATE`, PostgreSQL 세션 행 `SELECT … FOR UPDATE` 호출 구간. 연결 획득·SQL 호출 비용을 포함한 애플리케이션 구간이며 DB 엔진의 순수 잠금 대기 시간이 아니다.
- `evidence.state_read`: evidence JSON 행 조회.
- `evidence.flush_commit`: ORM `Session.commit()` 호출 전체. 자동 flush와 commit 반환을 포함하며 디스크 fsync만의 시간은 아니다.
- `duration_ms`: 서버 요청 진입부터 SQL 작업 결과 확정까지. `worker_ms`는 작업 스레드 안의 시간만 포함한다.

15초는 상담 브라우저의 응답 대기 값과 맞춘 **서버 관측 기준**이다. 네트워크 왕복을 포함하지 않고 SQL을 취소하지 않는다. 초과해도 `recorded` 또는 `replayed`와 `response_budget=exceeded`를 함께 기록한다. CPU `/decisions`의 300ms 정책과 다르다.

비용은 실행당 구조화 로그 2종, 루트 span 1개와 SQL 단계 span, 고정 라벨 지표다. OTel의 기존 512개 trace 표시 버퍼·선택적 OTLP exporter를 재사용한다. 전체 작업 JSON을 새로 로그에 복제하지 않으며 SQL 스키마·잠금 범위·작업 제한을 바꾸지 않았다. 이번에 관측 오버헤드를 처리량 수치로 측정하지는 않았다.

## 로그 → trace → 작업 확인

`evidence_execution_finished`에 `session_id`, `receipt_id`, `request_key`, `action_id`, `trace_id`, 단계 시간, 결과를 남긴다. `evidence_http_finished`는 같은 trace ID로 응답 상태를 연결한다. 들어온 `traceparent`를 추출하며, 응답의 `X-Recheck-Trace-Id`는 CORS에서도 읽을 수 있다. 데모의 원본 응답 JSON에 성공·차단 요청의 trace ID를 함께 보존한다.

`storage=committed`는 저장 또는 기존 작업 반환의 트랜잭션이 정상 종료한 경우다. `not_written`은 검증 차단·기록 전 SQL 실패다. flush/commit 구간의 DB 오류는 `unknown`으로 남긴다. 연결 오류가 commit 성공 후 발생했을 가능성을 메시지 하나로 배제하지 않는다. `/evidence/actions` 조회와 같은 요청 키 재시도로 확인한다.

[이번 로컬 실행 로그·trace·독립 SQL 대조](evidence/release-2026-10-18/local-execution-observation.json)와 [회귀 테스트](../backend/tests/test_evidence_observability.py)를 참고한다. 공개 체험에서 `전체 과정 실행`을 완료하고 실행 로그의 원본 응답을 펼치면 차단·새 기록·같은 작업 반환을 확인할 수 있다.

## 직접 재현

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
PYTHONPATH=backend RECHECK_NETWORK_TESTS=1 backend/.venv/bin/python -m pytest \
  backend/tests/test_evidence_observability.py \
  backend/tests/test_evidence_actions.py backend/tests/test_compute.py -q
```

기본값은 테스트별 임시 SQLite다. CI는 같은 검사를 격리된 PostgreSQL에도 실행한다. 실제 socket 취소 검사는 로컬 Uvicorn에만 연결한다. 잠금·쓰기 실패 주입 및 가상 시계 검사는 공개 API에 수행하지 않는다.

검사는 정상/재시도/차단과 라벨 제한, 실제 잠금 시간 초과 후 회복, SQL UPDATE 실패 후 행 미생성, ASGI task 취소와 실제 HTTP socket 종료 후 commit·동일 키 회복, 15초 초과 및 디스패치 대기 포함, 운영 표본 수집을 확인한다. 시간 예산 경계 테스트의 시계 이동은 실제 지연 성능 측정이 아니다.

핵심 코드: [`evidence_observation.py`](../backend/recheck/evidence_observation.py), [`observability.py`](../backend/recheck/observability.py), [`evidence.py`](../backend/recheck/evidence.py), [`store.py`](../backend/recheck/store.py), [`evidence_routes.py`](../backend/recheck/evidence_routes.py).
