# 조사 이후 데모 화면과 근거 연결 개선

시작 기준 `96e3fef0e20502643030a14d04fe095047c59064`. [10개 프로젝트 심층 조사](deep-comparative-research-2026-10-17.md)에서 확인한 화면 우선순위·모바일 글자·근거 연결 문제를 기존 세 경로 안에서 수정했다. 백엔드 전체 재작성, 새 모델·부하 실험·인프라 추가는 없다.

## 무엇이 달라졌는가

| 기존 | 변경 | 확인 |
|---|---|---|
| 포괄적인 제목과 소개·3경로 설명이 첫 화면을 크게 차지 | ‘문서가 바뀌면, 이전 답변은 멈춰야 합니다’로 대표 문제를 특정하고 실행 버튼·저장 시연·보조 경로를 옆에 배치 | [실행 첫 화면](evidence/workspace-upgrade/case-entry.png) |
| 목표/유효 막대6개 아래에 보류·거절 설명이 이어짐 | 구간 목록과 선택한 구간의 유효·보류·거절·504 건수/분모를 나란히 표시. 막대는 처리율이 아닌 요청 구성비로 명시 | [부하 PC](evidence/workspace-upgrade/serving-desktop.png) |
| 모바일6열에서9px 라벨 | 12px 이상 주요 라벨, 모바일 구간 선택은 native select. 선택한 상세를 전체 구간 목록보다 먼저 배치 | [부하 모바일](evidence/workspace-upgrade/serving-mobile.png) |
| 저장 후504 한 건을 설명문으로만 언급 | 바로가기로 해당 구간을 선택해 실제 응답·요청 키·최종SQL행·DB의trace ID를 대조 | `모델 부하 → 저장 후 응답 실패 1건` |
| 장애 과정 설명을 지나야 trace 도구가 등장 | HTTP응답·모델판단·SQL일치를 선택한 요청에 맞춰 먼저 표시하고 바로 아래에 시간축·예외·상세 배치 | [장애 PC](evidence/workspace-upgrade/recovery-desktop.png) |
| 실패/복구마다 다른 축, name으로span선택 | 두trace에 공통 상대 시간축. span_id로 선택. 현재 선택한 span ID와 상세의 일치를 검사 | [장애 모바일](evidence/workspace-upgrade/recovery-mobile.png) |
| 작은 모바일 trace라벨8px | 12px 보조 라벨, 이름/소요와 시간막대를 두 줄로 분리 | 화면 폭을 줄여도 정보 축소 대신 배치 변경 |

그림자·장식 카드·애니메이션을 늘리지 않았다. 상태색은 유효(녹색), 보류(황갈색), 거절(회색), 시간초과(적색)로 나누고 단어·건수를 함께 표시한다. 이해도 개선은 실제 사용자 조사로 검증하지 않았다.

## 설계 선택과 비용

- CaseFlow가 소유하는 실행 수명은 유지했다. 상단·기존 실행 버튼은 같은 상태를 사용한다. 화면을 이동해도 실행·로그·작업ID가 보존된다.
- 저장 부하 구간/trace 탐색은 읽기 전용이다. 선택 변경과 상세 열기로 추가 API 요청을 보내지 않는지 검사했다.
- 원본 `fullpath-sustained.json.gz`의 SHA256을 확인한 뒤, 원본이 기록한 `committed_without_200_keys`로 요청과SQL행을 결합한다. 새 가상 요청이나 가상trace를 만들지 않았다. 한 건의 추가 상세만 프런트 JSON에 포함하고 전체 원본은 기존docs로 연결한다.
- 504의 재시도를 이 부하 실험에서 실행했다고 주장하지 않는다. 실패·복구 화면의 lightweight trace와도 다른 실행이다. 상담 `/evidence/.../execute`, CPU `/decisions`, lightweight 실패 주입, Kubernetes DB복구의 경계를 유지했다.
- 120req/s는 투입 목표, 약67.6req/s는300ms내 유효 응답이다. 구간별 비율은 예정 요청건수, 응답률은 해당구간 마지막완료까지의 시간을 분모로 쓴다. 전체지연과유효응답지연을 별도로 보여준다.
- 공통trace축 때문에 짧은span의 막대는 작아진다. 별도 소요시간 숫자를 유지한다. 네이티브SQLspan이 없으며 fence.commit이 SQL커밋시간이 아니라는 설명도 유지했다.

## 실제 검증

- 프런트 전체 **48개 통과**, TypeScript/Vite 빌드 통과.
- 로컬 백엔드 전체 **150개 통과·2개 제외**. 제외된 항목은 `RECHECK_NETWORK_TESTS`가 꺼져 있던 실제 HTTP 프로세스 검사 두 개다. 설정을 켠 별도 실행에서 **2개 모두 통과**했다. 이 로컬 실행은 SQLite 기준이다.
- 로컬 브라우저 **60개 명명된 검사**: [기본 18](evidence/workspace-upgrade/base.json), [근거 12](evidence/workspace-upgrade/evidence.json), [대표 체험 10](evidence/workspace-upgrade/case.json), [비교 7](evidence/workspace-upgrade/comparison.json), [서빙 6](evidence/workspace-upgrade/serving.json), [전달·신규 상호작용 7](evidence/workspace-upgrade/presentation.json). 각 항목에 복수 assertion이 있으며, 사용자 수나 독립 실험 수가 아니다.
- 상단·기존 버튼을 동시에 눌러도 세션은 하나였다. 이전 답변 차단 → 새 답변 기록 → 같은 키 재시도, 완료 후 이동, 진행 중 이동, 응답 유실 후 동일 키 재시도, 명시적 재시작, 통제된 HTTP 404 만료를 확인했다. 404 검사는 실제 TTL이 경과했다는 주장이 아니다.
- 320/390/768/1440px에서 펼친 원본·표·영상의 문서 넘침, 실제 글자 크기, 키보드 구간 선택, 각 span 선택, 실패·복구의 공통 축과 판정 전환, 504 원본 연결을 검사했다. 주요 화면 캡처도 직접 열어 확인했다.
- 코드 리뷰에서 504 상세를 닫은 뒤 바로가기로 다시 열리지 않는 결함을 재현했다. native details 상태를 동기화하고, 매번 열기·초점·스크롤을 수행하도록 수정했다. 반복 열기 회귀 검사가 통과했다.
- 초기 운영 기록 검사는 로컬 API의 관측 설정이 꺼져 `/api/operations`를 조회하지 못해 실패했다. `RECHECK_OBSERVE=1`로 로컬 설정을 맞춘 뒤 통과했다. 이를 공개 서비스 장애로 기록하지 않는다.

## 공개 배포 후 확인

구현 커밋은 [`101a49ab27945ba83590cb5ede7f49deb6a33352`](https://github.com/sokldjs554/recheck-ml-serving/commit/101a49ab27945ba83590cb5ede7f49deb6a33352)이다.

- [CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39009816359): PostgreSQL 환경 백엔드 **151개 통과·1개 제외**, 프런트 **48개 통과**, 생성 요약·번들 일치 통과. 제외된 `test_session_capacity_and_expired_session_cleanup`은 격리 SQLite가 필요한 fixture이며 위 로컬 전체 실행의 150개에 포함되어 통과했다.
- [Pages 배포와 공개 브라우저 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39009816353): **60개 명명된 검사 통과**. 공개 API에서 대표 체험·멱등 재시도·화면 이동을 실행했고, 통제된 네트워크 실패/404 검사는 별도로 구분한다. 저장 결과 탐색·320/390/768/1440px 배치·실제 WebM 재생도 통과했다. MP4와 WebM 모두 HTTP 200이며 이 Chromium 실행에서 디코딩한 형식은 VP9 WebM이다.
- Render 무료 서비스의 같은 커밋이 2026-10-17 **06:27:00 UTC**에 `live`가 됐다. 배포 ID는 `dep-db9h9dflk1mc73buonp0`. 공개 검사 시작 전 서버 번들 `/assets/index-Bi7_JpZ_.js` 일치도 확인했다.
- [기존 Kubernetes 복구 workflow](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39009816351)도 같은 커밋에서 통과했다. GitHub Actions의 격리된 kind 검사이며 공개 Render 서비스의 장애·복구를 일으킨 것은 아니다.
- [공개 검사 산출물](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39009816353/artifacts/12092750668)과 [로그에서 추출한 검사 목록·배포 정보](evidence/workspace-upgrade/public-verification.json)를 연결했다. 산출물 ZIP을 이 작업환경에 내려받는 요청은 HTTP 403으로 막혀 공개 캡처를 여기서 다시 열지는 못했다. 로컬 동일 버전 캡처의 직접 열람과 공개 환경 자동 검사 결과를 구분한다. Actions 산출물에는 보관 기한이 있다.

이 배포 검사 성공이 기존 정기 점검 실패를 취소하지 않는다. 10월 13일 세 번 모두 기능 검증은 성공했지만, 첫 전체 점검은 약 54.037초로 5초 기준을 넘겼고 이후 약 2.13초·1.63초였다. 원인은 미확정이며 서버 시작 지연으로 단정하지 않는다.

## 실제 시연

[40.24초 시연](https://sokldjs554.github.io/recheck-ml-serving/media/recheck-walkthrough.mp4)은 새 상담 화면에서 **실제 로컬 Python API·SQLite**를 사용해 촬영했다. 6단계 실행, 차단·기록 로그, 비교 화면 왕복 후 같은 작업 ID를 확인한다. HTTP 응답 모킹·합성 프레임·배속은 없으며 앞 1초만 잘랐다. [촬영 시각·요청 상태·작업 ID](evidence/workspace-upgrade/recording.json)를 남겼다. 공개 서버의 현재 실행 상태와 구분해 표시한다.

## 재현

```bash
npm --prefix demo test
npm --prefix demo run build
PYTHONPATH=backend RECHECK_NETWORK_TESTS=1 python -m pytest backend/tests -q
python scripts/build_serving_summary.py --check
python scripts/check_case_browser.py --base http://127.0.0.1:18766 --api http://127.0.0.1:18020
python scripts/check_presentation_browser.py --base http://127.0.0.1:18766 --api http://127.0.0.1:18020
```

브라우저 검사는 실행 중인 UI·Python API·모델 서버가 필요하다. 로컬 운영 기록까지 확인하려면 `RECHECK_OBSERVE=1`과 UI origin의 CORS 설정이 필요하다. 공개 배포는 기존 GitHub Pages/Render 절차와 배포 후 브라우저 workflow를 사용한다.

## 남은 한계

무료 서버 시작 지연, 새로고침 후 클라이언트 상태 복원 미지원, 실기기 Safari·사용자 이해도 미검증은 남아 있다. 기존 180초 측정은 장기 SLA나 공개 서버 처리량이 아니다. 10월 13일의 54.037초 점검 실패와 10월 17일 운영 기록은 보존했고 5초 기준을 완화하지 않았다. 지원자 개인 기여나 은행 운영 경력을 새로 추가하지 않았다.
