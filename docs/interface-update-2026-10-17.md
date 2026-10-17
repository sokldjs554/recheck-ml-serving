# 실행 화면과 프로젝트 소개 개편

기준 커밋: `b27a6d74e2955b6ab3d4a1e588a9f83ce335b2bf`.

첫 화면의 제목을 ‘답변과 실행 사이, 한 번 더 확인합니다.’로 바꾸고, 남색 내비게이션·흰 본문·코발트 실행 버튼으로 세 경로의 표현을 통일했다. 기존 3열 사례 화면은 원문·답변 비교와 전체 너비의 서버 판단 영역으로 재배치했다. 단계별 실행은 비교 영역 위에, 로그·기록 결과는 아래에 둔다.

![개편된 실제 실행 화면](../demo/public/media/recheck-screen.png)

[변경 전 화면](evidence/interface-2026-10-17/before.png). 새 UI는 `demo/src/interface.css`, `App.tsx`, `CaseStudy.tsx`, `ServingEvidence.tsx`에 구현했다. 기존 CaseFlow와 API 계약을 재사용한다.

README의 반복적인 한계 목록은 간결한 검증·실행 안내로 정리했다. 데모에는 실시간 API와 저장된 측정의 구분, 수치 옆의 환경·시간 조건, 연결 대기 안내를 남겼다. 기존 실험 실패·운영 점검 원본은 각 상세 문서에 보존한다.

40.44초 시연은 새 UI에서 실제 로컬 Python API·SQLite를 사용해 다시 촬영했다. 이전 답변 차단, 새 기록, 같은 키 재시도, 로그 필터와 비교 화면 왕복을 포함한다. [촬영 시각·실제 요청·작업 ID](evidence/interface-2026-10-17/recording.json). README 대표 화면도 새 실제 실행 화면으로 교체했다.

검증:

- 프런트 58개와 TypeScript/Vite 빌드 통과.
- 실제 API 대표 체험 10개·새로고침 복원 9개·부하/복구 화면 6개 통과. [대표 체험 원본](evidence/interface-2026-10-17/case-browser.json) · [복원 원본](evidence/interface-2026-10-17/restoration-browser.json).
- 전달·영상 검사 7개에서 320/390/768/1440px의 펼친 영상·JSON 원본·상세 자료와 새 영상 디코딩을 확인했다. [원본 결과](evidence/interface-2026-10-17/presentation-browser.json) · [부하·복구 화면](evidence/interface-2026-10-17/serving-browser.json).
- 펼친 JSON의 긴 문자열이 모바일 로그 그리드를 623px로 늘리던 문제를 재현하고, 그리드 최소 너비·원본 줄바꿈을 수정했다.
- 보조 글자의 대비를 높였고, 부하 화면의 레이아웃·선택 동작 전환 폭을 1000px로 일치시켰다. 1024/1080px에서 선택한 결과가 화면 밖에 남는 문제를 수정했다.

적용 커밋은 `3d3507ea50b17d5dd5836efb8079f54d23ee0fdd`다. [CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39017725161): 백엔드 151개 통과·SQLite 전용 1개 제외, 프런트 58개 통과. [Pages 배포·공개 검증](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39017725123): 기존 60개 + Chromium 복원 9개 + macOS WebKit 복원 9개, 총 78개 통과.

[공개 Chromium 원본](evidence/interface-2026-10-17/public-chromium.json) · [공개 macOS WebKit 원본](evidence/interface-2026-10-17/public-webkit-macos.json). 두 브라우저 모두 새 영상의 40.44초 길이·1280×1080 해상도와 실제 재생 진행을 확인했다.

Render 배포 `dep-db9j511srm7s739jg950`도 같은 커밋으로 2026-10-17 08:33:59 UTC에 live가 됐다. 공개 검사는 `/assets/index-DdWcXTXW.js`가 Python 서버에 반영된 것을 확인한 뒤 실행했다.
