# 실패 한 건을 API → 모델 → SQL 영수증까지 추적하기

질문은 **“HTTP 200인데 모델이 실패했다면, 어떤 결과를 저장하고 무엇으로 실패를 확인하는가?”**다. 2026-10-12의 격리된 로컬 실행에서 실제 HTTP 요청 두 건, SDK가 내보낸 OTLP span, API 구조화 로그, 별도 PostgreSQL 연결의 조회 결과를 묶었다. [원시 증거](evidence/failure-trace-proof.json)의 `success: true`는 [검증 스크립트](../scripts/verify_failure_trace.py)가 아래 연결과 결과를 확인했다는 뜻이다.

`/decisions` 모델 서빙 경로의 검증이다. 문서 일관성을 검사하고 SQL action을 실행하는 `/evidence/.../execute` 경로의 실패나 성능으로 해석하지 않는다. 공개 서비스 장애가 아니며 실제 고객 데이터도 사용하지 않았다.

## 조건과 기존 증거의 빈틈

- 실행 구간: **2026-10-12 05:55:20.575410–05:55:23.254974 UTC**. loopback API `18310`, 모델 `18311`, OTLP 수신기 `18312`, 로컬 PostgreSQL `15432`의 새 전용 DB `recheck_failure_walkthrough`.
- 실제 Python API와 모델을 별도 프로세스로 실행했다. `lightweight` 모델, inline 실행, 요청 deadline 300 ms이며 부하 실험은 아니다. 소스 SHA-256은 원시 증거의 `source_sha256`에 있다.
- 기존 [관측 스택 증거](evidence/observability-latest.json)의 Jaeger trace `aeb867df9167e20197d9e182f11070cb`는 **정상 요청**이다. 그 실행의 모델 실패 세 건은 집계 지표에만 남아 있고 개별 실패 receipt/trace/로그는 보존하지 않았다. 이 정상 trace를 실패 trace로 재사용하지 않았다.
- 이번에는 기존 SDK exporter가 전송한 protobuf를 작은 로컬 수신기에서 직접 읽었다. `exported_spans`는 실제 서비스·span·parent ID이며, 화면용 receipt span 목록에서 재구성한 것이 아니다. 이번 실행은 Jaeger·Alertmanager 경로를 재검증하지 않았다. 그 경로의 기존 성공 증거는 [operations.md](operations.md)에 별도로 있다.

## 실패 → 탐지 → 원인

05:55:22.592232 UTC에 `fault: "unavailable"`을 가진 결정 요청을 보냈다. 모델의 기존 fault injection이 `/infer`에서 **503 `model_unavailable`**을 발생시켰다. API는 HTTP **200**을 반환했지만 receipt는 **`review / model_unavailable`**, `risk_score: null`이었고 `/validate`는 **`valid: false`**였다. HTTP 코드만 집계하면 이 실패를 놓친다.

| 식별자 | 실제 값 |
| --- | --- |
| 실패 trace | `6a7b91369b9b3e7d85341d5b6c846e7b` |
| 실패 receipt | `c97efa86-a21d-43c5-a7ac-911b84bb0e8c` |
| session | `9acab7ac-0359-4c54-b805-9c6b4bb82f53` |
| API `decision` | `a01004a40a4ef03a` — ERROR `model_unavailable` |
| API `snapshot` | `cc8cda9fe75aa516`, parent `a01004a40a4ef03a` |
| API `model.http` | `b36ec6cf9809c7a7`, parent `a01004a40a4ef03a` — ERROR |
| worker `model.infer` | `0483dc21912eaca6`, parent **`b36ec6cf9809c7a7`** — ERROR |
| API `fence.commit` | `dbfd1eb25e771205`, parent `a01004a40a4ef03a` |

worker `model.infer`의 exception event에는 `HTTPException: 503: model_unavailable`이 남았다. 이 span의 parent가 API `model.http`와 일치하므로 서비스 경계를 넘어 같은 요청임을 확인할 수 있다. 원인은 주입한 모델 오류이며 CPU 과부하나 PostgreSQL 장애가 아니다. 실패 trace에는 **`model.predict`가 없다**. 예측 전에 실패했기 때문이다.

API는 다음 기존 구조화 로그를 출력했다. receipt ID와 trace ID를 동시에 사용하면 HTTP 결과, span, SQL row를 연결할 수 있다.

```json
{"receipt_id":"c97efa86-a21d-43c5-a7ac-911b84bb0e8c","session_id":"9acab7ac-0359-4c54-b805-9c6b4bb82f53","trace_id":"6a7b91369b9b3e7d85341d5b6c846e7b","status":"review","reason":"model_unavailable"}
```

실제 `/metrics`에도 `recheck_business_outcomes_total{outcome="review",reason="model_unavailable",service="api"} 1.0`이 기록됐다. 이번 탐지는 응답·span exception·로그·지표의 직접 확인이다. 자동 알림 발생 시각을 이번 실행에서 측정했다고 주장하지 않는다.

## SQL 경계와 fail-closed 처리

실제 순서는 **SQL 예약/버전 snapshot → 모델 HTTP → SQL 최종 fence 및 receipt 저장**이다. 모델이 DB를 호출하는 구조가 아니다. 모델 실패 후에도 API는 `Store.finish`에서 실패한 검토용 receipt를 저장한다. 실패가 발생했다고 SQL 저장을 건너뛰거나 성공 receipt로 바꾸지 않는다.

`snapshot`과 `fence.commit`은 애플리케이션 span이다. **네이티브 PostgreSQL query span은 계측하지 않았다.** 특히 `fence.commit`은 `finalize` 안에서 종료되며 ORM flush/commit은 그 뒤에 일어나므로, 그 duration을 SQL commit 완료 시간으로 해석하면 안 된다. [API의 finalize](../backend/recheck/api.py)와 [Store.transaction / Store.finish](../backend/recheck/store.py)가 이 경계를 보여 준다.

SQL 저장 여부는 span 이름으로 추정하지 않고, HTTP 응답을 받은 뒤 **독립 SQL 연결**에서 다음 조회를 실행해 확인했다.

```sql
SELECT id, session_id, idempotency_key, payload
FROM decisions WHERE id = :id;
```

원시 증거의 `failed.sql_row.payload`가 `failed.receipt`와 완전히 같다는 assertion이 통과했다. 저장된 payload는 같은 실패 trace ID, `review`, `model_unavailable`, `risk_score: null`, `protected: true`를 가진다. 이는 검토 이력을 보존한 것이며 실행 가능한 정상 판정을 발급한 것이 아니다. DB가 실제로 실패한 요청의 SQL 성공이나 존재하지 않는 DB span을 만들어 설명하지 않았다.

## 원인 제거 → 정상 추론 → SQL 저장

같은 session에서 새 idempotency key로 fault를 제외한 요청을 05:55:22.628089 UTC에 보냈다. 이는 **요청 단위 fault 제거**이며 프로세스 재시작·Kubernetes 복구와는 별개다.

- 정상 trace: `8113074c95987bc85cbe12848382d313`.
- 정상 receipt: `21fe3c1a-28f1-4360-ade8-e88c5ef2a996` — `clear / no_current_warning`, 당시 `valid: true`.
- API `model.http` `1caf9d257f931040` → worker `model.infer` `fe85c7cc5c9cc068` → `model.predict` `0ae486e37c8b4644`의 parent 연결을 확인했다.
- `risk-v1` 모델 hash는 `7de0929ba34aefaa313bf15354e6582133992cb755df11094ced0796125521be`였다.
- `recovered.sql_row.payload == recovered.receipt` 및 같은 receipt/trace ID의 API 로그를 확인했다. 정상 결과도 HTTP 응답만 보고 저장됐다고 간주하지 않았다.

두 receipt의 유효기간은 15초다. 위 `valid: true`는 실행 당시 관측이며 현재도 유효하다는 주장이 아니다. 실패 receipt는 정상 요청 후에도 실패 이력으로 남는다.

## 이미 검증한 운영 복구 한 건: PostgreSQL Pod 교체

프로세스 장애에 대한 복구 증거는 **2026-10-08의 기존 PostgreSQL Pod 교체**를 사용한다. [kubernetes-proof.json](evidence/kubernetes-proof.json)의 `postgres_pod_replacement` event와 `samples`, [실행 스크립트](../scripts/k8s_verify.py)의 persistence 검증이 근거다. 위 10월 12일 trace와 같은 사고·같은 실행으로 합치지 않는다.

| 단계 | 보존된 관측 |
| --- | --- |
| 원인 | 소유한 단일 PostgreSQL Pod `postgres-0`를 삭제해 교체하는 실험. DB replica/failover는 없다. |
| 실패·탐지 | 16:30:48.888104부터 16:30:50.889624 UTC까지 HTTP 503 `database_unavailable` 표본 5개. 0.5초 간격 create-session + inference probe로 탐지했다. |
| 복구 조치 | StatefulSet이 Pod를 다시 만들고 동일 PVC로 준비될 때까지 기다렸다. |
| 최초 정상 표본 | 16:30:51.389735 UTC. 최초 실패부터 관측된 복구까지 2.501631초. 표본 사이 실제 downtime은 알 수 없다. |
| 지속성 | 기존 receipt `42061cb3-41ab-4ed4-af73-24773812a8f6`가 남았고 PVC UID `19164689-c9da-441d-80c3-f60c93ff6032`가 유지됐다. persistence 함수는 새 DB Pod UID를 확인한 다음 API에서 receipt를 다시 읽는다. |
| 정상 추론 | 복구 검증 receipt `6188442f-ed16-4375-9b02-e167db72b34c`: `clear`, `valid: true`, model hash `89c4dfbdd770b5e43801c23a690f8b67e535e589546b88042f9afaf46f66ef71`. |
| 이후 표본 | `recovered` 단계 10건 모두 `clear / no_current_warning`. |

이 보존본의 PostgreSQL 교체 단계는 총 72표본 중 정상 67, HTTP 오류 5다. [kubernetes.md](kubernetes.md)에 연결된 다른 CI 실행의 오류 2개·4개와 숫자가 다르며, 서로 다른 실행 결과를 섞지 않았다. 이 기존 보존본은 개별 DB 실패의 trace ID/DB span을 저장하지 않았으므로 해당 503을 위 모델 실패 trace에 연결할 수 없다. 기존 지속성 검증은 재기동 후 API 조회로 확인했고, 이번 focused 실행은 별도 SQL 연결로 row를 확인했다.

## 판단, 비용, 한계와 재현

판단: HTTP 성공률 외에 business outcome을 집계하고, receipt의 trace ID를 보존하며, 모델 실패는 `review`로 닫는다. DB 장애 때는 503을 노출한다. SQLite로 조용히 대체하지 않는다. 대가는 실패 이력 저장을 위한 짧은 SQL transaction, span 전송, bounded receipt/telemetry 보관 비용이다. DB 단일 장애점과 짧은 receipt TTL은 그대로 드러난다.

기존 관측 스택·Kubernetes를 다시 띄우지 않고 두 요청만 추가했다. 재현하려면 Python 의존성과 **새 disposable local PostgreSQL DB**를 준비한다. 다음 값은 격리된 로컬 실험용 자격이며 공개 서비스 DB를 가리키면 안 된다. 스크립트도 loopback host, `recheck_failure_` DB 접두어, 빈 decisions schema를 요구한다.

```sh
# 소유한 로컬 PostgreSQL에 새 DB recheck_failure_repeat를 먼저 만든다.
DATABASE_URL='postgresql+psycopg://recheck:local-demo-only@127.0.0.1:15432/recheck_failure_repeat' \
  backend/.venv/bin/python scripts/verify_failure_trace.py \
  --output work/failure-trace-repeat.json
```

스크립트는 자신이 시작한 API/model만 종료한다. DB는 후속 조회를 위해 보존한다. 실패 시에도 `success: false` 및 error를 기록하며 기존 증거는 재현 출력 경로를 바꿔 보존한다. 공개 Render/Neon에서의 장애·복구, 장기간 SLO, 분산 DB failover, 전체 SQL query 추적은 이 증거로 검증하지 않았다.
