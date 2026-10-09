# 검증 기록

2026-10-08, Linux 개발 컨테이너, Python 3.12.14, Node 24.19, PostgreSQL 16. 합성 데이터만 사용했다. CI 설정의 존재와 실제 실행을 구분한다.

[GitHub Actions 원격 검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37719089551)에서 PostgreSQL+HTTP 테스트 32 통과·1 생략, TypeScript 10 통과, production build와 저장된 배포 번들 일치 검사가 통과했다. [GitHub Pages 배포](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37719089545)도 성공했다. 공개 URL의 한국어 화면과 모드 표시를 확인했다. 개발 의존성의 알려진 취약점은 Vitest 5.0.3으로 수정했고, 당시 `npm audit`는 0개였다([원자료](evidence/npm-audit.json)).

첫 공개판 소스 `d7e393f`의 [원격 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37719664371)와 [공개 주소 브라우저 검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/37719664388)이 모두 성공했다. 후자는 실제 GitHub Pages URL에서 13개 확인을 수행했다: 정상 후 변경 거절, 정책·모델 변경, 보호·기준선 경쟁, JSON 다운로드, 두 장애 설정, 가이드·소개 탭, 실제 21초 만료, 3개 화면 폭, 페이지 오류 0. 로컬의 14개와 달리 공개 Python API 검증은 포함하지 않는다. JSON·스크린샷은 해당 실행의 `public-browser-evidence` 아티팩트에 보존된다.

## UI 재설계 검증

동일 날짜에 사이드바·휴대폰 목업을 버전 비교 화면으로 교체했다. 최신 로컬 production 번들에서 브라우저 15개 확인(실제 Python API 연결 1개 포함), 페이지 오류 0, TypeScript 10개 테스트, production build와 저장된 정적 번들 일치를 확인했다. 판단 생성 전 빈 기록, 버전 변경 뒤에도 남는 원본 snapshot, 다음 요청 중 기존 금액 불변을 검사한다. 390·768·1024px의 가로 넘침을 자동 검사하고 데스크톱·모바일 캡처를 검토했다. 별도 리뷰에서도 320–1440px의 네 탭을 확인했다.

현재 화면 증거: [버전 불일치](evidence/demo-comparison.png) · [정상 판단](evidence/demo-desktop.png) · [모바일](evidence/demo-mobile.png). 공개 배포 후 실행되는 브라우저 검증은 아래 로컬 기록과 구분하며, [Pages 워크플로](https://github.com/sokldjs554/recheck-ml-serving/actions/workflows/pages.yml)의 해당 커밋 실행에서 확인할 수 있다.

## 문구 개선 검증

실제 참고 화면을 확인한 뒤 제목·버튼·빈 상태·결과 문구를 한국어 행동 중심으로 수정했다. 업데이트한 버튼 이름으로 로컬 production 데모의 15개 브라우저 확인을 다시 통과했다. 390px에서 네 탭의 제목과 가로 넘침을 확인했고, 단어가 한 글자만 다음 줄에 남던 제목은 짧게 고쳤다. 조사 범위와 반영 내용은 [화면 조사](research.md#네-프로젝트의-실제-데모-조사)에 기록했다.

## 확인한 실행

| 검증 | 결과 | 증거 |
|---|---|---|
| Python SQLite 테스트 | 32 통과, 1 선택적 socket 테스트 생략 | [상세 실행 기록](../backend/IMPLEMENTATION.md) |
| PostgreSQL + 실제 HTTP subprocess 통합 | 32 통과, 1 SQLite 전용 용량 fixture 생략 | [원문 출력](evidence/backend-tests.txt) |
| TypeScript 시뮬레이션·표시 회귀 테스트 | 10 통과 | `cd demo && npm test` |
| React production build | 성공 | `python scripts/build_demo.py` |
| Chromium 브라우저 수용 검증 | 15개 확인, 페이지 오류 0, 390·768·1024px 가로 넘침 없음 | [JSON 기록](evidence/browser-checks.json) |
| 실제 HTTP API 수용 검증 | 7개 확인 | [응답 원자료](evidence/http-proof.json) |
| Docker multi-stage 이미지 | 빌드 성공, 비root 실행 설정 | [Dockerfile](../Dockerfile) |
| Docker Compose 3개 서비스 | PostgreSQL·모델·API 정상 기동, 실제 HTTP 7개 확인 | [Compose 응답 원자료](evidence/compose-http-proof.json) |

HTTP 검증은 모델 해시·trace, 멱등 재생, 본문 충돌 409, 버전 변경 후 거절, 모델 응답 불가의 review 전환, 세션 격리, 다른 세션의 판단 404를 확인한다. 수용 검증 하나를 여러 개의 단위 테스트라고 합산하지 않는다.

브라우저 자동 검증과 Compose 실행 결과는 각각 [browser-checks.json](evidence/browser-checks.json), [compose-http-proof.json](evidence/compose-http-proof.json)에 기록한다. 이 초기 기록 당시 Kubernetes YAML은 구성 예제였다. 아래 운영 보완에서 실제 클러스터 검증을 추가했다.

## 부하 측정 방법

```bash
backend/.venv/bin/python scripts/benchmark.py --count 60 --rate 30 --delay 0 --repeats 3 --output docs/evidence/load-no-injected-delay.json
backend/.venv/bin/python scripts/benchmark.py --count 60 --rate 80 --delay 80 --repeats 3 --output docs/evidence/load-injected-delay.json
```

- 실제 HTTP gateway와 별도 Python 모델 프로세스, Python 호스팅 구성과 같은 SQLite 실행 경로에서 측정했다.
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
7. UI 재설계 리뷰에서 다음 요청이 진행되는 동안 이전 기록의 금액이 새 입력값으로 바뀌어 보였다. 기록별 제출 금액을 사용하도록 수정했다. 기존 번들에서 150,000원 → 900,000원 변경으로 재현했고, 브라우저 검증에 요청 진행 중 금액 불변 확인을 추가했다.

이는 이번 AI 지원 개발·독립 리뷰에서 관측한 기록이다. 사용자가 과거에 직접 수행한 작업으로 바꿔 서술하지 않는다.

## 운영 보완, 2026-10-09 KST

- PostgreSQL + 실제 HTTP 회귀: **54 통과·1 SQLite 전용 fixture 생략**, 11.39초. SQLite + HTTP는 **55 통과**. 프런트엔드 **18 통과**, Kubernetes 검증기의 잘못된 성공을 막는 반례 **3 통과**.
- [CPU 비교](compute-experiments.md): 실제 앙상블 추론 **10,900건**을 원자료에 보존. 격리 2개·30rps·30초에서 896/900건이 200ms 기준 내 성공. 60rps·60초에서는 2572/3600건으로 용량 한계를 확인했다. 거절·오류도 분모에 포함한다.
- [Kubernetes](kubernetes.md): 실제 GitHub Actions 클러스터의 장애·배포·복구 **6개 검증**. 초기 291개 표본 중 DB 재시작 단계의 HTTP 오류 2개를 함께 기록했다. 0.5초 표본 간격에서 보이지 않는 중단까지 없었다고 주장하지 않는다.
- [관측](operations.md): Prometheus 두 대상, Grafana 6개 패널, 실제 API→모델 trace, 업무 실패와 모델 중단 알림의 발화·해제, 복구 후 새 유효 판단을 확인했다.
- [공개 점검](evidence/public-synthetic-initial.json): Render의 실제 Python 서버를 외부에서 호출해 초기 3개 표본과 HTTP 기능 7개를 확인했다. 매시간 점검은 실행별 원자료를 보존하며 장기간 실적과 구분한다.

추가 리뷰에서 자식 프로세스가 죽어도 준비 상태가 정상이던 문제, 처음부터 무효인 판단도 합성 점검이 성공으로 오인하던 문제, 복구 검증이 readiness만 확인하던 문제를 고쳤다. 현재 검증은 새 정상 추론과 사용 시점의 유효성까지 확인한다.

최종 로컬 production 번들의 [브라우저 검사](evidence/operations-browser-checks.json)는 **17개 확인**을 통과했다. 실제 Python HTTP 모드의 정상 판단·변경 후 거절, 390·768·1024px 가로 넘침, 새 검증 탭, 페이지 오류 0을 포함한다. [PostgreSQL 테스트 출력](evidence/operations-backend-tests.txt)도 보존했다. 처음 임시18765 출처에서는 CORS가 막았으며, 설정된5173 출처에서 재검증했다.

### 공개 검증이 찾아낸 추가 문제

공개 Pages 브라우저 검사에서 정보 변경 응답보다 사용 시점 검증 응답이 먼저 반환됐다. 실제 로그는 검증 응답16:27:39.640UTC, 변경 응답16:27:39.849UTC였다. 변경 응답이 앞선 검증 표시를 지우면서 사용자가 재검증 결과를 볼 수 없었다. 로컬에서 실제 변경 요청을 브라우저 라우트로 보류해 재현했고, 변경 처리 중에는 재검증 버튼과 핸들러를 차단했다. 같은 반례가 수정 전 실패·수정 후 통과했다. 이 회귀를 공개 브라우저 검사에도 포함한다.

[배포 중 외부 점검](evidence/public-synthetic-deployment.json)은 정확성3/3이지만 시작 지연75.4초로 5초 이내2/3이었다. [배포 후 재실행](evidence/public-synthetic-recovered.json)은 3/3이며 HTTP 기능7개도 통과했다. 실패 기록을 삭제하거나 장기간 가용성으로 바꾸지 않는다.

## 2026-10-09 자료 기반 근거 실험 업데이트

[검증 요약 JSON](evidence/evidence-lab-verification.json),
[실제 브라우저 12항목](evidence/evidence-lab-browser.json),
[검색 품질 실패 후보 원본](evidence/evidence-lab-negative-release.json),
[SDK 답변 예제](evidence/evidence-sdk-answer.json),
[SDK 체크리스트 예제](evidence/evidence-sdk-checklist.json)를 추가했습니다.

로컬 최종 백엔드 73개(`RECHECK_NETWORK_TESTS=1`), 프런트엔드 21개 통과.
기존 데모 브라우저 검증 17개와 새 근거 실험 12개가 실제 HTTP로 통과했습니다.
로컬 백엔드 전체 실행은 SQLite이며 PostgreSQL 검증은 저장소 CI를 확인합니다.
공개 Pages의 새 실험 검증은 Python API 업데이트를 기다린 후 실제 API로 실행하고,
화면 캡처·원본 결과를 `public-browser-evidence` 워크플로 아티팩트에 남깁니다.

독립 리뷰에서 빈 원문이 제목만으로 검색되어 빈 답변이 유효해지는 경우를 발견하여,
삭제 이벤트를 제외한 공백 본문을 API에서 거절하도록 수정했습니다. 외부 요청으로
문서가 바뀐 경우 이전 배포 평가의 통과 표시도 숨기고 재평가를 요구합니다.


## 2026-10-09 UI 재구성

대형 슬로건을 제거하고 18~20px 작업 제목, 고정 좌측 메뉴, 조건 설정/버전 비교/검증 결과를
배치한 작업 공간으로 변경했습니다. 근거 실험의 연결 전 화면은 실행 결과가 아님을 표시한
문서 미리보기로 바꿨습니다. 서버 동작과 검증 기준은 동일합니다.

[실제 화면 캡처](evidence/ui-workspace-desktop.png), [6개 페이지 × 3개 화면 크기 검사](evidence/ui-layout-audit.json).
390/768/1440px에서 가로 넘침 없이 표시되고, 기존 21개 프런트엔드 테스트 및 실제 브라우저 30항목이 통과했습니다.

844×390px 가로 화면에서 키보드로 마지막 메뉴에 이동하면 메뉴가 화면 안으로 스크롤되는지도 검증했습니다.
