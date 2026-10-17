# 새로고침 복원과 남은 검증 보완

시작 기준은 `c69eabae3af370b5ffc58e570fe70fc7abacabfa`다. [앞선 화면 개선](workspace-upgrade-2026-10-17.md)의 미완료 항목 중 같은 탭 새로고침 복원을 구현했다. 기존 CaseFlow·API·무료 운영 구성을 유지했다.

## 구현한 동작

- 확인한 응답, 진행 단계, 세션, 두 답변, 작업 ID, 로그, 멱등 재시도 키를 같은 탭의 sessionStorage에 저장한다. 별도 API 주소를 지정한 사례도 해당 주소로 복원한다.
- 복원은 네트워크 요청을 발생시키지 않는다. 진행 중이던 작업은 ‘중단된 실행’으로 표시하고 자동 재전송하지 않는다. 사용자가 이어서 실행하면 읽기 전용 세션 확인 후 진행한다.
- 기록 요청 직전에 키와 재준비 금지 상태를 저장한다. 서버가 이미 기록했으나 응답을 받지 못한 채 새로고침했을 때 같은 키로 재시도한다. 정상적인 서버 응답으로 확인하기 전에는 작업 완료를 표시하지 않는다.
- 세션 확인이 404를 반환하면 과거 답변·로그를 보존하고 새 실행을 막는다. 완료된 사례를 복원할 때는 현재 세션이 유효하다고 주장하지 않는다.
- 명시적 ‘처음부터’는 저장한 사례도 지운다. 손상·구버전·다른 API의 checkpoint는 거부한다. 저장 권한·용량 오류는 진행을 중단시키는 대신 복원 불가 경고와 JSON 내려받기를 안내한다.

구현: [CaseFlow](../demo/src/caseFlow.ts), [저장·형식 검사](../demo/src/caseStorage.ts), [실제 API 브라우저 검사](../scripts/check_restoration_browser.py).

## 비용과 보장 범위

상태 변경마다 JSON 직렬화·동기식 sessionStorage 쓰기가 추가된다. 저장 상한은 문자열 1,000,000자와 이벤트 512개다. 상한 초과·저장 실패 시 경고하며, 영구 보관 기능으로 표현하지 않는다. 탭 종료·기기 변경·여러 탭의 협조 실행은 범위 밖이다.

복원 데이터는 화면을 위한 과거 기록이다. 클라이언트 저장 데이터를 서버의 정합성 증거로 신뢰하지 않으며, 실제 기록은 기존 SQL 검증과 멱등성 계약을 따른다. 새로고침이 이미 전송된 서버 작업을 취소한다는 보장도 없다.

세션 생성의 응답 자체를 받기 전에 새로고침하면 그 세션 ID를 알 수 없다. 이후 명시적 실행으로 새 세션이 만들어질 수 있으며 기존 세션은 서버 만료 정책에 따른다. 검색·평가 도중 끊긴 단계의 명시적 재시도는 새 검색/평가 기록을 남길 수 있다. 상담 작업 기록은 기존 동일 키를 보존해 재시도한다.

## 검증 기록

- 프런트 **58개 통과**. 기존 48개와 복원 계약 10개다. TypeScript/Vite 빌드도 통과했다.
- 로컬 실제 Chromium·Python API·SQLite에서 기존 대표 체험 **10개** 회귀 검사와 새 복원 **9개** 검사를 통과했다. 새 검사는 완료 후 재로딩, 실제 저장 응답 보류 중 재로딩 후 같은 키로 한 건만 반환, 명시적 초기화, 지정 API 복원, 320/390/768/1440px 배치, 영상 디코딩, 손상 데이터, 저장소 차단, 통제된 404를 포함한다. 404와 저장 차단은 통제된 주입 검사다. [복원 결과](evidence/reload-recovery/local-chromium.json) · [기존 대표 체험](evidence/reload-recovery/local-case-regression.json) · [모바일 복원 화면](evidence/reload-recovery/local-mobile.png).
- 테스트 우선 구현의 최초 복원 검사는 실패했다. 리뷰와 실제 API 실행에서 인용 참조에는 `deleted` 필드가 없다는 차이를 발견했다. 원문/참조 검증을 분리하고 실제 응답 모양으로 단위 fixture를 고쳤다. 지정 API 주소를 잃던 문제도 함께 수정했다.
- 저장소를 둘 다 차단하는 브라우저 조건에서는 기존 App 초기화의 localStorage 접근이 `SecurityError`로 실패해 사례 화면이 0개였다. 기본 API 주소로 초기화하는 fallback을 추가했고, 같은 주입 조건에서 실제 답변 준비가 성공하며 복원 불가 경고가 남는 것을 확인했다.
- 실제 응답 보류 후 페이지를 폐기하는 로컬 Playwright **1.62.0** 실행에서 종료 시 `CancelledError` 콜백 진단이 남았다. 제품의 `pageerror`는 0건이고 모든 assertion·프로세스 종료는 성공했다. 공개 workflow는 기존 핀인 **1.55.0**을 사용한다. 이를 제품 오류나 깨끗한 테스트 로그로 바꾸어 표현하지 않는다.
- 공개 배포 후 기존 60개 검사와 Chromium·macOS WebKit 각각의 새 복원 검사를 실행하도록 workflow를 추가했다. 최종 결과는 아래에 기록한다. WebKit은 Safari와 관련된 엔진 검사이며 Apple 실기기 Safari 인증을 뜻하지 않는다.
- [첫 공개 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39011893430)는 기존 상세 탐색의 초점 assertion에서 실패했고 뒤의 WebKit 단계는 실행되지 않았다. 클릭 다음 `requestAnimationFrame`에서 초점을 옮기는데 검사는 클릭 직후 동기적으로 읽고 있었다. 로컬에서 프레임을 120ms 지연한 3회 모두 즉시 읽기는 false, 다음 프레임의 실제 초점은 true였다. 초점 조건을 기다리는 Playwright assertion으로 수정했고 기존 전달 검사 7개가 로컬에서 통과했다. 제품 동작이나 정기 점검의 5초 기준은 바꾸지 않았다.
- [두 번째 공개 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39012317138)는 기존 60개 검사를 통과했으나 새 복원 검사에서 ‘중단’ 표시 assertion에 실패해 WebKit은 실행되지 않았다. 로컬 실제 API에서 저장 응답을 보류한 뒤 전송을 취소하고 새로고침했더니 `busy=false`, `error=Failed to fetch`, `canReprepare=false`, `action=null`로 같은 표시 공백이 재현됐다. 완료 여부가 불확실한 요청과 오류로 멈춘 실행도 중단 상태로 복원하고, 마지막 오류를 안내에 보존하도록 수정했다. 이 조건의 단위 검사 실패 후 수정·통과, 실제 API 동일 키 재시도와 저장 작업 1건을 다시 확인했다. 당시 공개 실패의 저장값 전체를 확보한 것은 아니므로 모든 세부 원인이 동일했다고 단정하지 않는다.

- [세 번째 공개 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39012716336)는 기존 60개와 Chromium 복원 9개를 통과했다. [Chromium 원본 결과](evidence/reload-recovery/public-chromium-fe2395d.json). WebKit은 복원·멱등 재시도·반응형 검사 이후 영상 재생 조건에서 20초 시간 초과로 실패했다. 이 실행을 전체 성공으로 집계하지 않는다. 재생 시점의 소스·오류·준비 상태와 가시 영역을 기록하고 실제 플레이어를 화면에 보이게 하는 후속 검사를 추가했다.

- [재생 진단 실행](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39013166624)에서도 WebKit 영상 검사에 실패했다. 로그에는 WebM 선택, `readyState=4`, `play()` 성공, 1280px 폭, 초기 재생 시간 약 0.013초가 남았지만 이후 0.2초 초과 조건을 통과하지 못했다. 플레이어는 960px 화면 안의 y=654~890에 있었다. 가시 영역 보정만으로 해결되지 않았으며, 브라우저 내부 디코더 원인까지 확정하지 않는다. 같은 녹화의 기존 H.264 MP4를 우선 제공하고 WebM 대체 소스를 유지해 재검증한다. [로컬 MP4 실제 디코딩과 화면 회귀 7개](evidence/reload-recovery/local-media-mp4.json)는 통과했다. 영상 내용·재생 속도·검사 시간 기준은 바꾸지 않았다.

- [MP4 우선 공개 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39013518112)에서도 기존 60개와 Chromium 복원 9개는 통과했지만 WebKit 영상은 20초 뒤 `currentTime=0.1628`, `readyState=2`, `networkState=2`로 실패했다. MP4 우선순위 변경만으로 해결됐다고 주장하지 않는다. 후속 검사에서는 의도적으로 응답을 보류·취소하는 네트워크 주입 전에 정상 영상 재생을 검증하도록 순서를 분리했다. 재생 시간·해상도·20초 제한 조건은 유지한다.

- [네트워크 주입 전 영상 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39013891732)도 WebKit MP4에서 약 0.1628초·버퍼링 상태로 실패했다. 따라서 주입 순서가 원인이라고 결론 내릴 수 없다. 후속 검사기는 영상 실패를 별도 배열에 남기고 다른 기능 검사를 계속하되, 마지막에는 실패 종료한다. 실패한 영상 검사를 통과 수에 더하지 않는다.

- [Linux 최종 분리 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39014250899): 기존 60개와 [Chromium 9개](evidence/reload-recovery/public-linux-chromium.json)는 통과했다. [WebKit 26.0](evidence/reload-recovery/public-linux-webkit.json)은 복원·멱등성·배치·만료·저장 차단 등 8개 통과, 영상 1개 실패다. React·CSS·API·주입 코드가 없는 새 빈 페이지에서도 같은 공개 MP4가 약 0.16초에서 멈췄다. 따라서 RECHECK만의 DOM 문제로 단정하지 않으며, Linux 미디어 스택의 정확한 원인도 미확정이다. 전체 workflow는 의도대로 실패 종료했다. 동일 Playwright 1.55.0·재생 시간·20초 제한을 유지한 macOS-14 표준 러너로 WebKit 검증 환경을 분리하고, Linux 실패는 원본과 함께 보존했다. macOS 검사는 실기기 Safari 인증이 아니다.

## CI와 배포 확인

- 기능 구현 커밋 `fe2395dbd2405b9bc72ad0b031ef92ed7189ccb7`의 [CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39012716326)는 PostgreSQL 백엔드 **151개 통과·1개 제외**, 프런트 **58개 통과**다. SQLite 전용 `test_session_capacity_and_expired_session_cleanup`은 [직전 로컬 SQLite 전체 실행](workspace-upgrade-2026-10-17.md)의 150개 통과에 포함됐다. 이번 프런트 변경에서는 그 백엔드 근거를 재사용한다.
- 같은 기능 커밋의 Render 배포 `dep-db9hva9srm7s739ijlfg`는 2026-10-17 07:13:40 UTC에 live가 됐다. 기존 free 서비스이며 루트 번들은 `/assets/index-DmJz_Clg.js`다. 공개 브라우저 workflow도 일치하는 Python 배포를 확인한 뒤 검사를 진행한다.

- 영상 소스 우선순위 변경까지 포함한 최종 기능 커밋은 `17a8c29538de69d361ed6bf6fed54a658d8642ee`다. [최종 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39013517903)도 백엔드 151개 통과·1개 제외, 프런트 58개 통과다. Render `dep-db9i5cbm8hqs73ah54lg`는 07:26:40 UTC에 live가 됐고 번들은 `/assets/index-5ydDs-wz.js`다.


### 최종 공개 결과

검증 구성 커밋 `c2516f42ee5da919bc46ca63d7e61a8e72dcc42a`의 [최종 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39014594177)와 [Pages 배포·공개 브라우저 검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39014594238)이 성공했다. 공개 검사는 **기존 60개 + Linux Chromium 9개 + macOS-14 WebKit 9개 = 78개 통과**다. backend 151개 통과·1개 제외와 frontend 58개 통과도 다시 확인했다.

- [최종 Chromium 결과](evidence/reload-recovery/final-chromium.json): Chromium 140.0.7339.16, WebM 실제 디코딩, 9개 통과, pageerror 0건.
- [최종 macOS WebKit 결과](evidence/reload-recovery/final-webkit-macos.json): WebKit 26.0, MP4 실제 디코딩, 9개 통과, pageerror 0건. 40.24초 영상의 1280×1080 해상도와 재생 시간 진행을 확인했다. 전체 영상 프레임 전수 검사나 Apple 실기기 Safari 검사가 아니다.
- 캡처 산출물: [기존·Chromium](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39014594238/artifacts/12094183393), [macOS WebKit](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39014594238/artifacts/12094665065). 공개 산출물은 자동 검증·생성 사실을 확인했으며, 로컬로 내려받아 재열람한 것으로 표현하지 않는다.
- Linux WebKit 실패는 수정 완료가 아니다. 같은 테스트가 macOS에서 통과했다는 사실은 환경 의존성을 보여주지만 Linux 내부 미디어 스택의 정확한 원인을 확정하지 않는다. 제품 변경으로 모든 WebKit 환경을 고쳤다고 주장하지 않는다. 정기 점검의 5초 기준·과거 실패 기록도 그대로다.


## 여전히 남는 항목

- 무료 서버 최초 응답 시간의 상한은 보장하지 않는다. 10월 13일 전체 점검 약 54.037초 실패와 5초 기준을 유지한다. 그 실패의 원인은 미확정이다.
- Render 실제 서비스의 `healthCheckPath`를 이번에도 조회했으며 빈 문자열이었다. 기존 `render.yaml`의 `/health`와 불일치한다. 현재 연결 도구에는 해당 필드 수정 기능이 없어 반영하지 못했다. [서비스 Settings](https://dashboard.render.com/web/srv-db3rmj3ncjis73bi8fl0/settings)에서 Health Check Path를 `/health`로 지정하는 작업이 남는다. 유료 서비스 생성으로 대체하지 않는다.
- Linux CI Playwright WebKit 26.0의 영상 재생 실패는 남아 있다. macOS WebKit의 통과 범위와 구분한다.
- 실제 사용자 이해도 조사와 Apple 기기 Safari 검사는 아직 수행하지 않았다. 사용자 모집·응답이나 실기기 결과를 대신 만들어내지 않는다.
- 공개 캡처 ZIP 다운로드를 새 산출물로 다시 시도했지만 `CONNECT tunnel failed, response 403`으로 네트워크 프록시에서 차단됐다. 직접 열어 본 로컬 화면과 공개 자동 검사 결과를 구분한다. 공개 캡처 재열람이 가능해지면 별도로 기록한다.

재현 명령:

```sh
npm --prefix demo test
npm --prefix demo run build
python scripts/check_restoration_browser.py --base http://127.0.0.1:18766 --api http://127.0.0.1:18020 --browser-executable /usr/bin/chromium
# Playwright WebKit 및 OS 의존성이 설치된 환경:
python scripts/check_restoration_browser.py --base http://127.0.0.1:18766 --api http://127.0.0.1:18020 --engine webkit
```

브라우저 명령은 실제 UI·API·모델 서버를 먼저 실행한 환경이 필요하다. 공개 서버에 부하 실험을 추가하지 않았다.
