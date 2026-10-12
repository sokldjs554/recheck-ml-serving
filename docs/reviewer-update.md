# 2026-10-12 검토 보완과 검증 경계

기준은 `af69d2daa9b4d5a71335d7f741fb691c980749d5`다. 시작 시 최신 `origin/main`과 같았으며 작업 중인 변경은 없었다. 기존 백엔드·SQL 원자성·멱등성·OTel·Jaeger·Prometheus·Kubernetes 구현을 유지했다.

[변경 전 데스크톱](evidence/reviewer-before-desktop.png) · [변경 후 데스크톱](evidence/reviewer-after-desktop.png) · [변경 전 모바일](evidence/reviewer-before-mobile.png) · [변경 후 모바일](evidence/reviewer-after-mobile.png)

[서빙 화면](evidence/reviewer-serving-desktop.png) · [복구 화면](evidence/reviewer-recovery-mobile.png)

## UI에서 바꾼 문제

| 이전에 확인한 문제 | 변경 | 확인 범위 |
|---|---|---|
| 실제 API 사례 완료 → 세 방식 비교 → 실행 재현 복귀 시 step 6→0, 작업 ID 사라짐 | `CaseFlow`를 `App` 소유로 옮김. `CaseStudy`는 구독/표시만 수행 | 실제 브라우저에서 수정 전 재현, 수정 후 다운로드 snapshot·세션·전체 로그·작업 ID 동일, 복귀 API 요청 0건 |
| 진행 중 화면을 떠나면 flow가 dispose됨 | 실행 수명과 탭 수명 분리, 명시적 재시작의 generation fence 유지 | 실제 HTTP 변경 요청을 보류한 채 이동 → 원 요청 완료 → 복귀; 같은 세션과 작업 1개, 중복 요청 없음 |
| 만료와 일반 네트워크 실패를 같은 재시도 안내로 처리 | HTTP 상태/기계용 오류 사유를 보존; 세션 만료는 과거 근거 유지 + 명시적 새 실행 안내 | 주입한 404와 별도 로컬 서버의 실제 TTL 2초 만료를 구분해서 검증 |
| 상단 7개 메뉴와 별도 3개 탭이 경쟁 | 상단 실행 재현·모델 부하·장애 복구, 나머지 보조 메뉴 | 모든 기존 목적지와 키보드 탐색 회귀 검사 |
| 최초 진입에 단일 상담 사례만 설명 | 목적과 직접 실행 / 저장된 서빙 / 저장된 실패·복구 경로 배치 | 데스크톱·모바일 직접 렌더링 확인 |
| 장식적인 gate·티켓·색 배경이 정보보다 강조됨 | 원문/준비 답변/실행 판단을 명시, 상태 색과 텍스트 병기, 글자·간격·모바일 단일 열 수정 | 변경 전후 스크린샷. 사용자 이해도 향상을 입증하는 연구는 아님 |
| 서빙·복구에 긴 표가 먼저 노출됨 | 질문→조건→관측→판단→한계, 원본·기존 비교는 펼침 영역 | raw 링크는 새 탭으로 열어 기존 체험 보존 |

첫 화면의 상담 정합성 경로는 `/evidence/…/execute`이며 CPU 부하의 `/decisions`와 다르다.
저장된 결과는 실시간 성능으로 표시하지 않고 브라우저 시뮬레이션은 보조 경로로 유지한다.
새로고침·탭 닫기 후 클라이언트 실행 복원은 지원하지 않는다. 서버 만료는 다음 API 요청이 응답할 때 확인한다.
화면을 떠나 있는 동안에도 진행 중 요청은 계속되며, ‘처음부터’ 이후 도착한 이전 응답은 UI를 덮어쓰지 못한다.
원격에서 이미 완료된 쓰기를 클라이언트 reset으로 되돌리지는 않는다.

## 새 측정과 재사용한 근거

- [180초 실제 API→CPU→PostgreSQL](fullpath-sustained.md): 같은 프로세스·자원에서 2회 정상→과부하→복귀. 8,400 측정 + 50 워밍업 시도, 거절·보류·504·생성기 지연·CPU/RSS·대기열·회복·전체 SQL 대조. HTTP 504 이후 이미 저장된 1건도 보존.
- [정합성 비용](consistency-costs.md): 동일/다른 세션·동시성·변경 빈도·지원 상태 크기, 54조건×3회. 2,808실행 중 2,095기록·711변경 거절·2잠금 시간 초과, 432변경. 최종 SQL의 오래된 기록·중복·누락 없음.
- [실패 요청 연결](failure-walkthrough.md): 실제 실패 trace·모델 exception·API 로그·독립 SQL 조회. 별도 정상 요청과 저장 확인. 기존 PostgreSQL Pod 복구를 다른 실행임을 명시하여 재사용.
- 기존 worker 단독 격리 비교, 3방식 SQL 안전성, 제어된 잠금 시간 초과/재시도, Jaeger·알림·Kubernetes 자료를 중복 구현하지 않았다.

프로세스 격리는 메모리와 IPC 비용을, 수용 제한은 거절을, 시간 예산은 저장 후 응답 실패 가능성을 남긴다.
세션 직렬화·상태 증가의 비용은 관측했지만 JSON 저장이나 잠금 하나가 유일한 병목이라고 결론내리지 않았다.
은행 처리량·장기 SLA·사업 성과는 측정하지 않았다.

## 실행 검증

로컬 검증은 별도 PostgreSQL 테스트 DB와 SQLite 브라우저 fixture에서 진행했다.

- 전체 백엔드: **139 passed, 1 skipped**. PostgreSQL 실행에서 의도적으로 건너뛴 SQLite 전용 세션 용량/만료 정리 테스트는 따로 실행해 **1 passed**.
- 프런트: **44 passed**, TypeScript·Vite 빌드 통과. 상태 수명·만료·응답 검증 및 외부 근거 링크 검사.
- 대표 사례 브라우저: 전체/단계 실행, 완료 후 이동, 진행 중 이동, 응답 유실 재시도, 명시적 초기화, 네트워크 실패, 404 만료 보존.
- 실제 만료 브라우저: 독립 API·worker·SQLite, 실제 2초 TTL, HTTP 404 수신, 모바일 로그 유지·복귀 요청 0건·새 세션 시작. HTTP 응답 모의나 시계 패치 없음.
- 화면 회귀: 기존 시뮬레이션·실제 API 모드·원문 수정/삭제·릴리스 게이트·저장된 비교·서빙/복구. 390/768/1440 및 작은 화면·가로 배치 검사.

브라우저 검사 중 개발 서버 hot reload로 중단된 실행은 화면 파일을 고정한 뒤 재실행했다.
로컬 관측 비활성 서버로 운영 조회를 검사한 설정 오류는 관측을 활성화한 fixture로 바로잡았다.
둘을 서비스의 측정 성능 결과에 포함하지 않았다.

[전체 로컬 검증 JSON](evidence/reviewer-local-verification.json) · [실제 세션 만료 결과](evidence/reviewer-real-expiry.json)

## 재현

```sh
# 의존성 설치와 로컬 앱 실행은 README 참고
PYTHONPATH=backend RECHECK_TEST_DATABASE_URL='<전용 로컬 PostgreSQL URL>' RECHECK_NETWORK_TESTS=1 \
  backend/.venv/bin/python -m pytest backend/tests -q
cd demo && npm test && npm run build
# 저장소 루트에서 실행, 로컬 frontend/API 주소를 지정
backend/.venv/bin/python scripts/check_case_browser.py --base http://127.0.0.1:5178 --api http://127.0.0.1:8023
backend/.venv/bin/python scripts/check_case_expiry_browser.py --base http://127.0.0.1:5178
```

공개 배포는 기존 main→GitHub Pages/Render 절차를 사용한다. 공개에서는 기능·화면 이동만 검사하며 부하/장애를 주입하는 용량 실험을 실행하지 않는다.
최종 커밋·공개 브라우저 실행은 이 문서의 후속 검증 기록과 GitHub Actions에서 확인한다.

## 공개 반영 확인

구현 커밋: [`0b99e35`](https://github.com/sokldjs554/recheck-ml-serving/commit/0b99e35cf7d59f624cbc8eab5c31bc1359ca4108).
기존 무료 Render 서비스의 자동 배포 `dep-db67qb7avr4c73fopqk0`가 2026-10-12 06:26:37 UTC에 live가 되었다.
GitHub Pages는 같은 소스에서 배포하며, 공개 브라우저 검사 시작 전에 Python 호스트의 `web_static` 번들 해시 일치를 기다린다.

[전체 회귀 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388408) ·
[공개 브라우저 검사와 스크린샷 artifact](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388240) ·
[Kubernetes 재검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38212388305).

세 실행 모두 **success**로 종료됐다. 공개 Chromium에서 대표 체험 완료 후/진행 중 이동과 API 중복 없음, 모바일, 비교 자료, 서빙·복구, PostgreSQL 운영 기록 조회를 확인했다.

[공개 배포·검사 원문 발췌](evidence/reviewer-public-verification.json). 공개 스크린샷은 해당 Actions artifact에 보존한다.
로컬에서 변경 전후 UI를 직접 확인했으며, 공개 자동 검증은 동일 번들 확인과 실제 렌더링·조작 검증이다.
공개 세션 만료 404는 클라이언트 동작 확인용 주입이며, 실제 서버 TTL 만료는 별도의 로컬 2초 fixture에서 검증했다.
