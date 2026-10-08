# 검증 기록

2026-10-08, Linux 개발 컨테이너, Python 3.12.14, Node 24.19, PostgreSQL 16. 합성 데이터만 사용했다. CI 설정의 존재와 실제 실행을 구분한다.

## 확인한 실행

| 검증 | 결과 | 증거 |
|---|---|---|
| Python SQLite 테스트 | 32 통과, 1 선택적 socket 테스트 생략 | [상세 실행 기록](../backend/IMPLEMENTATION.md) |
| PostgreSQL + 실제 HTTP subprocess 통합 | 32 통과, 1 SQLite 전용 용량 fixture 생략 | [원문 출력](evidence/backend-tests.txt) |
| TypeScript 시뮬레이션·표시 회귀 테스트 | 10 통과 | `cd demo && npm test` |
| React production build | 성공 | `python scripts/build_demo.py` |
| Chromium 브라우저 수용 검증 | 14개 확인, 페이지 오류 0, 390·768·1024px 가로 넘침 없음 | [JSON 기록](evidence/browser-checks.json) |
| 실제 HTTP API 수용 검증 | 7개 확인 | [응답 원자료](evidence/http-proof.json) |
| Docker multi-stage 이미지 | 빌드 성공, 비root 실행 설정 | [Dockerfile](../Dockerfile) |
| Docker Compose 3개 서비스 | PostgreSQL·모델·API 정상 기동, 실제 HTTP 7개 확인 | [Compose 응답 원자료](evidence/compose-http-proof.json) |

HTTP 검증은 모델 해시·trace, 멱등 재생, 본문 충돌 409, 버전 변경 후 거절, 모델 응답 불가의 review 전환, 세션 격리, 다른 세션의 판단 404를 확인한다. 수용 검증 하나를 여러 개의 단위 테스트라고 합산하지 않는다.

브라우저 자동 검증과 Compose 실행 결과는 각각 [browser-checks.json](evidence/browser-checks.json), [compose-http-proof.json](evidence/compose-http-proof.json)에 기록한다. Kubernetes YAML은 구성 예제이며 실제 클러스터 검증을 완료했다는 주장은 하지 않는다.

## 부하 측정 방법

```bash
backend/.venv/bin/python scripts/benchmark.py --count 60 --rate 30 --delay 0 --repeats 3 --output docs/evidence/load-no-injected-delay.json
backend/.venv/bin/python scripts/benchmark.py --count 60 --rate 80 --delay 80 --repeats 3 --output docs/evidence/load-injected-delay.json
```

- 실제 HTTP gateway와 별도 Python 모델 프로세스, 공개 배포와 같은 SQLite 실행 경로에서 측정했다.
- open-arrival 방식, 5건 준비 실행, 기준선/보호 모드 순서를 교차해 각 3회, 회당 60건. 모든 성공·review·HTTP 오류·전송 오류를 저장한다.
- 0ms 실험은 **추가 지연을 주입하지 않은 실제 작은 모델 추론**이다. 80ms 실험은 의도적인 대기 시간을 넣어 수용·시간 예산 처리를 확인한다. 이를 모델 연산 성능이라고 부르지 않는다.
- p50·p95·p99는 클라이언트가 관측한 전체 응답이다. 서버 receipt의 latency는 최종 검증 직전까지이며 flush/commit·직렬화·네트워크 비용을 포함하지 않는다.
- 보호를 끈 기준선도 동일한 DB와 HTTP 경로를 쓴다. 단일 서버 대비 MSA의 성능 개선 실험이 아니다. 부하 발생기와 서버가 동일한 공유 개발 호스트에 있어 자원 간섭이 있다.
- 지연을 넘긴 새 clear 응답은 저장 후에도 확인하여 HTTP 504로 거절한다. 네트워크 전체의 절대 SLA를 보장하지 않는다. 기록이 남을 수 있으므로 재시도 응답은 역사적 기록으로 보고 사용 시점 검증이 필요하다.

원자료: [무주입 실험](evidence/load-no-injected-delay.json), [80ms 주입 실험](evidence/load-injected-delay.json). ‘p95가 낮으니 더 낫다’고 읽기 전에 clear 수·review 수·HTTP 거절 수를 함께 비교해야 한다. 처리량 우위나 운영 SLA의 증거로 사용하지 않는다.

이번 실행에서 보호 모드의 무주입 실험은 3회 모두 60/60 clear였고 각 회차 p95는 9.986·11.317·10.981ms였다. 80ms 주입·80rps에서는 매회 clear 8, review 50, HTTP 거절 2로 나타났다. 작은 모델을 빨리 호출하는 것과, 과부하에서 유효 결과를 충분히 제공하는 것은 별개다. 후자의 결과는 시스템 용량을 더 확보하거나 요청 정책을 조정해야 할 근거이며 성공률 개선 성과가 아니다.

## 리뷰에서 실제로 발견하고 고친 문제

1. 모델 v1→v2→v1 교체로 옛 판단이 되살아날 수 있었다. 배포 epoch를 단조 증가시키고 회귀 테스트를 추가했다.
2. 판단을 먼저 commit하고 trace를 나중에 붙여 다른 연결이 빈 trace를 볼 수 있었다. 최종 기록을 한 트랜잭션에서 저장한다.
3. 최종 DB 잠금·저장이 시간 예산을 넘기는 경로가 있었다. 잠금 안의 검사와 저장 후 응답 검사를 분리해 보완했다.
4. unsampled W3C 부모 trace에서 NonRecordingSpan의 없는 속성을 읽어 500이 발생했다. 기록 여부와 독립적인 시간 측정을 사용하며 always_off도 검증한다.
5. UI 비교 안내가 실패한 실행도 성공했다고 표현했다. 실제 기준선/보호 결과를 모두 확인한 경우에만 성공 안내를 표시한다.
6. 유효성 확인 후 만료돼도 ‘사용 가능’ 표시가 남았다. 표시 시점의 만료·버전 변경을 반영한다.

이는 이번 AI 지원 개발·독립 리뷰에서 관측한 기록이다. 사용자가 과거에 직접 수행한 작업으로 바꿔 서술하지 않는다.
