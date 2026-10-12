# README·데모 소개 개선

기준: `da7a26f` 이후, 2026-10-12. 기존 백엔드와 측정 자료를 재사용하며 새로운 모델·부하 실험·인프라를 추가하지 않았다.

## 무엇을 바꿨는가

- README 상단에 실제 화면·공개 데모·시연 영상을 배치했다. 문제와 대표 상황 다음에 전체 구조, 설계 선택과 측정, 본인 역할, 실행 방법, 한계를 설명한다. 중복 Docker 명령을 없앴다.
- 본인 역할은 사용자가 확인한 주제·방향 결정, 요구사항 제시·조정, 예시를 통한 수정 요청, 결과 검토로 한정했다. 코드·데모 제작은 AI가 주로 담당했음을 명시했다.
- 첫 화면 상단과 기존 실행 버튼은 같은 `CaseFlow`를 구독하는 `CaseRunButton`을 사용한다. 진행·완료·오류·세션 만료 상태를 공유한다. 기존 동기식 중복 요청 방지와 앱 단위 상태 수명은 유지했다.
- 부하·복구 화면은 실험 질문과 핵심 환경·수치·도식을 먼저 보여준다. 긴 조건, 설계 설명, 상세 한계와 원본 로그는 펼쳐 볼 수 있다. 120 req/s 목표 요청률과 약 67.6 req/s 유효 응답률, 로컬 측정과 공개 상담 체험은 계속 구분한다.
- 기다리는 동안 볼 수 있는 저장 시연을 첫 화면에 제공한다. 영상 재생으로 현재 실행 상태를 바꾸지 않는다. `preload="none"`으로 열기 전 영상 다운로드를 피하고 기본 HTML 영상 제어를 사용한다.

이 변경은 정보 접근 순서와 조작 위치를 개선하려는 선택이다. 실제 사용자 조사를 하지 않았으므로 이해도 향상이 입증됐다고 주장하지 않는다.

## 실제 시연

[영상](https://sokldjs554.github.io/recheck-ml-serving/media/recheck-walkthrough.mp4) · [대표 화면](../demo/public/media/recheck-poster.webp) · [촬영 시각·HTTP 상태·사건 기록·파일 SHA-256](evidence/introduction-media.json)

- 현재 React 화면 → 로컬 Python API·SQLite. HTTP 응답을 가로채거나 결과를 합성하지 않았다.
- 6단계를 한 단계씩 실행하고, 세 방식 비교로 이동한 뒤 같은 작업 ID가 남아 있는 것을 확인했다.
- 1280×1080, 36.36초, 음성 없음, H.264 MP4와 VP9 WebM. 브라우저 시작의 빈 화면 1초만 제거했으며 재생 속도나 실행 결과는 바꾸지 않았다.
- 공개 환경은 PostgreSQL이며 이 영상과 다른 실행이다. 현재 공개 서비스 상태·지연을 입증하는 영상이 아니다.
- GitHub Pages 정적 파일로 제공한다. YouTube 업로드나 유료 서비스는 사용하지 않는다.

로컬 API와 프런트를 실행한 뒤 촬영을 재현할 수 있다. Playwright와 ffmpeg가 필요하다. 프런트·API 주소는 실제 로컬 주소로 맞춘다.

```sh
backend/.venv/bin/python scripts/record_demo.py \
  --base http://127.0.0.1:5178 --api http://127.0.0.1:8023 \
  --output work/recording
```

## 회귀 검증

`check_case_browser.py`에 상단·기존 버튼을 **동일 JS 실행 안에서 연속 클릭**하는 검사를 추가했다. 세션 생성 1회와 최종 작업 1건을 독립 API 조회로 확인한다. 진행 중 이동, 완료 후 이동, 작업 ID·로그 보존, 차단→새 기록→같은 키 재시도, 명시적 초기화, 실패 응답·세션 만료 조건도 검사한다.

`check_presentation_browser.py`는 실제 health 요청을 잠시 보류한 동안 영상이 디코딩되는지 검사한다. 응답을 조작하는 시연이 아니라 **연결 대기 상태의 UI 회귀 조건**이며, 촬영 영상 자체는 가로채기 없이 별도 실행했다. 이후 보류한 실제 요청을 보내 체험을 완료한다. 1440·768·390·320px에서 영상·버튼·펼침·표 영역도 확인한다.

```sh
backend/.venv/bin/python scripts/check_case_browser.py \
  --base http://127.0.0.1:5178 --api http://127.0.0.1:8023
backend/.venv/bin/python scripts/check_presentation_browser.py \
  --base http://127.0.0.1:5178 --api http://127.0.0.1:8023
npm --prefix demo test
npm --prefix demo run build
```

공개 Pages 배포 절차에 같은 영상·반응형 검사를 추가했다. 같은 커밋의 Render 정적 번들이 확인된 뒤 공개 API 체험과 실제 영상 재생을 검사하고 `public-browser-evidence` 아티팩트에 결과·화면을 저장한다. [워크플로](../.github/workflows/pages.yml)

## 남는 한계

무료 서버의 시작 지연, 새로고침 이후 클라이언트 상태 소실, 가상 문서·합성 모델·단기 실험 범위는 그대로다. 영상은 데스크톱 Chromium 촬영이며 반응형 검증도 Chromium의 viewport 검사다. 실기기 Safari·Firefox·스크린리더와 실제 참여자 사용성은 이번 작업에서 검증하지 않았다.

## 배포 중 발견한 기존 CI 대기 제한

소개 화면 커밋 `fc59117`의 [전체 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38226653978)에서 `test_threaded_mutations_do_not_lose_version_increments`가 연결 풀 대기 시간 초과로 실패했다(138 통과·1 실패·1 제외). SQL 잠금과 statement의 정합성 테스트 예산은 이미 5초·10초였지만, checkout 이전의 연결 획득은 운영 기본값 300ms를 그대로 사용하고 있었다.

전용 로컬 PostgreSQL의 실제 연결 4개를 500ms 동안 점유하자 같은 `QueuePool ... timeout 0.30` 오류를 재현했다. 테스트 helper의 엔진 생성에만 pool 대기 5초를 적용한 뒤에는 동일 조건에서 버전 2 기록이 완료됐다. 동시성·버전 증가 검증을 제거하거나 재시도로 실패를 숨기지 않았다. 연결 개수 4, overflow 0, 실제 DB 잠금은 유지했다.

**운영 코드·설정은 변경하지 않았다.** 운영 잠금 시간 초과 테스트는 이 helper를 사용하지 않는다. 합성 pool timeout을 분류하는 테스트를 실제 300ms 운영 기한의 통합 검증으로 해석하지 않는다.

공개 검사용 Chromium에서 첫 MP4-only 검사의 영상 준비 상태가 0·network 상태가 3으로 남아 재생되지 않았다. 기본 `play()` promise의 무제한 대기를 없애고 20초 제한·브라우저 상태 진단을 추가했다. 동일 촬영본의 WebM을 우선 제공하고 MP4를 대체 형식으로 유지했다. 최종 검사는 두 파일의 HTTP 상태·MIME과 브라우저의 실제 디코딩을 각각 확인한다.
