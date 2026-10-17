# Langfuse / promptfoo UI 심층 감사 — 2026-10-17

이 조사의 핵심은 ‘로그에 필터를 붙이면 좋은 UI가 된다’가 아니다. Langfuse는 **요청 → 부모/자식 span → 시간 중첩 → 선택한 관측의 상세**를 연결한다. promptfoo는 **같은 입력 → 후보별 결과 → 판정 근거 → 수정/재실행**을 연결한다. 필터는 이 관계를 탐색하는 입구이며, 관계 자체를 대신하지 않는다.

## 확인한 범위와 확인하지 못한 범위

- 실제 확인: 아래 SHA에 고정한 UI·hook·CSS 소스 11개, 테스트/벤치마크 소스 8개, 문서 1개를 GitHub 연결 도구로 읽었다. 별도 목록은 `trace-eval-sources.json`이다. 원본 내용을 메모리에 읽었으며 프로젝트 파일을 변경하지 않았다.
- 실제 시각 확인: 공식 저장소의 promptfoo viewer PNG(49,629 bytes)와 Langfuse timeline PNG(356,847 bytes)를 내려받아 `view_image`로 직접 보았다. 이들은 **공식 예시 이미지**이고 이번에 실행한 브라우저 캡처가 아니다. 이미지가 가리키는 제품 빌드와 현재 소스 SHA가 일치한다는 보장은 없다.
- 공개 페이지 확인: Langfuse 데모 소개/지역 선택 페이지, promptfoo viewer 문서와 공개 o4-mini 보안 보고서의 내용을 무료 웹 도구로 읽었다. Langfuse EU 데모는 sign-up 경로와 Loading으로 이어졌고 README의 공개 trace URL은 도구에서 접근하지 못했다.
- 미확인: 두 앱의 설치/실행, 브라우저 클릭, 모바일 실기기 조작, 테스트 실행, UI FPS/INP/로딩 시간/부하의 독립 측정. 테스트 파일을 읽었다는 것은 통과를 확인했다는 뜻이 아니다. 유료 Tinyfish는 사용하지 않았다.

고정 버전:

| 프로젝트 | 확인한 커밋 | 커밋 시각 |
|---|---|---|
| Langfuse | `e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3` | 2026-10-16 21:31:04 UTC |
| promptfoo | `79011700b4cb544ddd9267565571a1d42d3a3051` | 2026-10-16 21:23:27 UTC |
| Langfuse docs 이미지 | `cf74ffeaa5280b943f7aba4c4b655b8cb39b702f` | 이번 조회에서 고정한 docs HEAD |

## 1. Langfuse: 트리와 시간축은 같은 선택 상태를 보여주는 두 표현

### 실제 본 화면

[공식 timeline 이미지](https://raw.githubusercontent.com/langfuse/langfuse-docs/cf74ffeaa5280b943f7aba4c4b655b8cb39b702f/public/images/blog/2026-08-31-langfuse-august-update/responsive-timeline.png)는 상단에서 trace 이름/ID를 크게 고정하고, 그 아래 검색과 Tree/Timeline 전환, 확대/축소/Fit, 공통 시간축, 마지막에 들여쓰기된 span을 배치한다. 흰 바탕과 옅은 회색 경계로 도구 영역을 나누며, 분홍/보라/주황/남보라의 막대는 span 유형을 구별한다. 선택 행은 연보라 가로 배경에 선택 막대의 테두리를 더한다. 선택 색과 유형 색을 별개로 유지해 ‘어떤 종류인지’가 선택 후에도 남는다. 트리 연결선과 동일한 시간축 덕분에 부모의 긴 구간 안에서 LLM → tool → 다음 step 관계를 읽을 수 있다. 이 이미지의 20초 이상의 trace에서 짧은 준비 작업 막대는 거의 선처럼 보인다. 이는 작은 막대에 더 많은 숫자를 붙이는 것보다 확대/집중 보기가 필요한 구체적인 이유다.

### 실제 소스에서 확인한 연결

1. [TraceTree.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/components/TraceTree.tsx#L72): 데이터, 선택, collapse 상태, hover prefetch를 분리한 context/hook에서 받아 조립한다. 로딩도 일반 spinner 하나가 아니라 여러 깊이의 가짜 트리 행으로 표현한다. 스켈레톤이 완료 후의 공간 구조를 예고한다.
2. [VirtualizedTree.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/components/VirtualizedTree.tsx#L47): 모든 행을 DOM에 그리는 대신 가상화한다. overscan은 16행, 기본 예상 높이는 37px이다. 측정 캐시는 index가 아니라 node ID를 사용한다. 코드 주석은 기존 index 캐시가 collapse 이후 다른 높이의 행과 섞여 겹침을 일으켰던 이유를 설명한다. 그래프 등 다른 곳에서 span을 선택하면 해당 트리 행으로 최소한만 scroll하며, 아직 접힌 아래에 있으면 펼쳐질 때까지 이동을 보류한다. 좁은 컨테이너에서는 깊이별 들여쓰기를 제한한다.
3. [TimelineDense.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/components/TraceTimelineDense/TimelineDense.tsx#L1): 축소 상태에서는 이름을 없애고 모양을 보여주다가 확대하면서 이름과 duration을 복원한다. wheel/pinch/drag/double-tap 처리와 frame 단위 누적이 구현되어 있다. `touch-action: none`을 사용하므로 앱이 손가락 pinch/pan을 직접 책임진다. 이 파일에 구현됐다는 근거이며 실제 기기에서 매끄러웠다는 관측은 아니다.
4. [SearchContext.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/contexts/SearchContext.tsx#L34)는 입력과 적용 쿼리를 분리해 500ms debounce를 둔다. Enter/프로그램 호출은 즉시 적용한다. [검색 테스트](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/fns/timeline/searchMatches.clienttest.ts#L26)는 일치하는 자손으로 가는 조상만 펼치고, 다른 branch의 collapse 상태와 일치 행 자신의 자식 collapse를 유지하는 계약을 확인한다. 단순 행 필터와 달리 ‘결과에 도달할 경로’를 보존한다.
5. [MobileFiltersSheet.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/events/components/MobileFiltersSheet.tsx#L65): 모바일은 데스크톱 필터를 작게 압축하지 않고 검색·기간·preset·saved view·facet을 85svh bottom sheet 한 곳으로 재배치한다. 검색/헤더/결과 버튼은 고정하고 내용은 한 개의 scroll 영역을 쓴다. 결과 수를 모를 때 ‘0’으로 오인시키지 않고 수 없는 Show results를 렌더링한다. desktop과 같은 controller를 전달한다는 점이 중요하다.

### UI 테스트가 말해주는 것

- [layout.clienttest.ts](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/fns/timeline/layout.clienttest.ts#L31)는 320/480/768/1280/1920px 폭, 0 크기, 빈 trace, 라벨 경계, 긴 빈 구간의 압축/역변환을 다룬다. 10,000행 fixture에서 100~139번의 40행만 배치하는 테스트도 있다. **이는 좌표와 windowing의 단위 테스트이며 10,000행에서 60fps를 측정한 결과가 아니다.** 텍스트 측정도 실제 canvas 대신 결정적 fallback을 사용한다.
- [TraceReviewLayout.clienttest.tsx](https://github.com/langfuse/langfuse/blob/e3a2bee2a2c048adf29b8d8a18b29bd4a8bf8ac3/web/src/features/traces/components/TraceReviewLayout.clienttest.tsx#L124)는 패널을 접어도 입력 상태를 유지하고 숨긴 navigator를 inert로 만들며, 700px로 재배치했다 복구하거나 닫고 열어도 작성 중인 comment와 trace 편집이 보존되는지를 다룬다. resize/panel을 mock하므로 브라우저 레이아웃 측정으로 확대 해석하면 안 된다.

### 그대로 복제하면 생기는 비용

- 밀집 모드에서 이름을 감추는 선택은 전체 형태 탐색에는 강하지만 첫 방문자의 ‘지금 무슨 단계인가’에는 불리하다. 확대, 색 의미, 선택 상세의 존재를 알아야 한다. RECHECK의 5~6개 span에는 전체 맵 조작보다 항상 읽히는 단계명이 유리하다.
- touch gesture는 넓은 데이터 탐색을 가능하게 하지만 일반 페이지 스크롤과 다른 학습이 필요하다. 모바일에서 필터 sheet와 trace 상세를 분리한 정보 구조를 가져올 수는 있어도 모든 지도 gesture를 가져올 이유는 없다.
- virtualization은 단순 useMemo보다 큰 차이를 만들 수 있으나, 실제 코드는 높이 캐시 identity, collapse 후 위치, 선택 이동, 과도한 들여쓰기, overlay scrollbar까지 처리한다. ‘가상화 라이브러리 추가’만으로 완성되는 기능이 아니다.

## 2. promptfoo: 입력 하나를 후보별로 비교한 뒤 증거와 재실행으로 들어간다

### 실제 본 화면

[공식 viewer 이미지](https://raw.githubusercontent.com/promptfoo/promptfoo/79011700b4cb544ddd9267565571a1d42d3a3051/site/static/img/docs/web-ui-viewer.png)는 1400×850 화면에서 상단 navigation → eval 이름/ID/author → display/search/결과 수 → column/table/chart actions → 입력×후보 matrix → 하단 pagination 순서다. 왼쪽 변수 `answer=yes/no`는 같은 행에 고정되고 후보 열은 동일한 입력에 서로 다른 prompt 결과를 보여준다. 각 열 헤더는 전체 pass rate와 분모(예: 12/12)를, 각 cell은 assertion의 PASS/FAIL과 구체적인 기대값 차이를 먼저 보여준다. 빨강/초록만 쓰지 않고 PASS/FAIL 텍스트도 같이 쓴다. 후보별 pass rate와 개별 assertion failure는 같은 ‘빨강’이어도 수준이 다르므로 별개 위치에 놓여 있다.

평가는 장식적 카드보다 비교 matrix가 중심이다. 반대로 이 예시에는 header/toolbars가 약 화면 위쪽 절반을 차지해 긴 결과의 가시 행 수가 적다. cell마다 여러 icon action이 반복되며, 상세/평가 액션을 처음 보는 사람은 tooltip을 탐색해야 한다. 넓은 화면의 검토 도구로는 합리적이나 포트폴리오 첫 화면에 그대로 놓으면 진입이 무겁다. 이 판단은 예시 이미지에 대한 시각 평가이지 현재 버전의 실제 측정이 아니다.

### 실제 코드: 선택에서 상세·검증·재실행까지

1. [ResultsTable.tsx](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/ResultsTable.tsx#L2249): manualPagination이며 화면에 받은 row를 map한다. 검토한 테이블 컴포넌트는 virtualizer 방식이 아니다. column 크기 유지, sticky header, 하단 pagination, 검색/필터 변경 시 첫 페이지 복귀, cell 단위 ErrorBoundary를 구현한다. fetching 중에는 기존 표 위에 반투명 blur/spinner overlay를 놓고 상호작용을 가린다. 빈 필터 결과는 fetching이 아닐 때 따로 표시한다.
2. [동일 파일의 deep link 처리](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/ResultsTable.tsx#L2270)는 필터 후의 row 위치와 안정적인 test/prompt identity를 분리한다. `rowId`로 페이지를 찾아가고 hash로 실제 대상을 확인한다. 원본 test index를 필터 결과 index로 착각해 다른 행을 여는 문제를 피하기 위한 코드다. RECHECK도 필터 후 ‘3번째 로그’가 아니라 요청/receipt/span ID로 선택해야 하는 이유다.
3. [EvalOutputCell.tsx](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/EvalOutputCell.tsx#L1090)는 copy/share/highlight, pass/fail, score/comment, 상세 액션을 제공하고 상세에 output과 grading 근거를 넘긴다. 일부 확장 액션은 Shift 상태에 따른다. 이 방식은 밀도를 줄이지만 발견 가능성과 touch 접근을 따로 검증해야 한다.
4. 이름은 Dialog지만 [EvalOutputPromptDialog.tsx](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/EvalOutputPromptDialog.tsx#L339)는 오른쪽 Sheet다. 작은 화면은 full width, sm 이상은 85vw이며 Prompt & Output / Evaluation / Messages / Metadata / Traces를 데이터가 있는 경우에만 만든다. active tab이 없어지면 첫 탭으로 복귀한다. 재실행은 원본을 지우는 대신 edit-mode, replayLoading, replayOutput, replayError 상태를 따로 가진다.
5. [ResultsTable.css](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/ResultsTable.css#L9)는 표의 overflow와 고정 열 배치, cell wrapping, 코드/이미지 제한을 설정한다. responsive 대응의 의미는 ‘모든 열을 휴대폰에 다 우겨넣는다’보다 가로 탐색·열 선택·전체 화면 상세다. 동시에 상세 탭 5개의 좁은 폭 가독성은 실제 모바일 테스트 없이 보장할 수 없다.

### 구체적으로 발견한 결함/트레이드오프

**A. 문서와 구현의 URL 상태 키가 어긋난다.** [동일 SHA의 문서](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/site/docs/usage/web-ui.md)는 `?filterMode=failures&search=timeout`을 예시로 제시한다. [FilterModeProvider](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/FilterModeProvider.tsx#L34)는 `mode`를 읽는다. [관련 테스트](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/FilterModeProvider.test.tsx#L63)도 `?mode=failures`를 사용한다. 다른 route에서 호환 alias를 처리하는지까지 전수 조사하지 않았으므로 사이트 전체 장애로 단정하지 않지만, 이 세 파일 사이의 문서/구현 불일치는 직접 확인했다.

**B. invalid parameter 테스트가 invalid 값을 넣지 않는다.** [FilterModeProvider.test.tsx L50](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/FilterModeProvider.test.tsx#L50)의 이름은 잘못된 값의 fallback을 검증한다고 하지만 입력은 유효한 `?mode=all`이다. 실제 hook은 schema.safeParse를 사용하므로 곧바로 구현 결함이라는 뜻은 아니다. 다만 이 테스트가 invalid 경로를 보호한다는 주장은 성립하지 않는다.

**C. trace 없음과 trace 조회 실패가 같은 UI로 사라진다.** [상세 코드 L202~231](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/EvalOutputPromptDialog.tsx#L202)는 조회 실패 시 traces를 빈 배열로 만들고, 빈 배열이면 탭을 숨긴다. [테스트 L1160](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/EvalOutputPromptDialog.test.tsx#L1160)도 실패 시 탭이 없는 것을 기대한다. 실패를 화면 전체로 번지게 하지 않는 장점은 있지만, 사용자는 ‘수집 안 됨’과 ‘가져오기 실패’를 구분할 수 없다. 증거 검증이 핵심인 RECHECK에는 복제하지 말아야 할 부분이다.

**D. 테스트 존재와 실제 사용자 성능은 다르다.** [ResultsTable.test.tsx](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/pages/eval/components/ResultsTable.test.tsx)는 필터 적용분만 pagination fetch에 전달, server cap 이상의 페이지 크기 제한, 필터 지표와 전체 지표 구분, 공급자 오류에 따른 분모, 수동 판정의 원래 assertions 보존을 다룬다. 이는 상태와 숫자 의미의 중요한 계약이다. 파일을 읽었고 실행하지 않았으며, 브라우저 실제 overflow/성능 결과로 제시하지 않는다.

## 3. 성능: 제품 주장 / 코드 장치 / 검증된 결과를 분리

| 항목 | 직접 확인한 근거 | 이 조사에서 말할 수 없는 것 |
|---|---|---|
| Langfuse v4 | [공식 출시 글](https://langfuse.com/changelog/2026-08-17-langfuse-v4)은 큰 프로젝트의 초기 table load가 milliseconds, dashboard가 적어도 10배 빨라졌다고 주장한다. 배너는 최대 165배를 말한다. 본문은 immutable observation, join/dedup 제거를 이유로 든다. | 재현 환경/동일 데이터/반복 측정 없이 RECHECK보다 10배/165배 빠르다고 할 수 없다. API query 개선과 브라우저 frame 성능도 별개다. |
| Langfuse tree/timeline | ID 기반 가상화 cache, 16행 overscan, windowed layout, debounce, pointer event의 frame 배치가 코드에 존재한다. | 이 환경에서 체감이나 p95를 측정하지 않았다. 10k행 테스트가 존재해도 렌더 FPS/INP 보장은 아니다. |
| promptfoo React Compiler benchmark | [reactCompiler.test.tsx](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/src/app/src/__benchmarks__/reactCompiler.test.tsx)는 5개 목록과 1,000회 sqrt 계산의 toy component를 React Profiler로 측정하고 10회/5회 상태 변경 시간을 로그한다. | production ResultsTable 벤치마크가 아니다. 주요 assert는 `renderCount > 0`라서 일정 속도 향상/회귀 방지 기준을 통과했다고 말할 수 없다. 실행 결과도 없다. |
| promptfoo tracing performanceBenchmark | [파일 자체](https://github.com/promptfoo/promptfoo/blob/79011700b4cb544ddd9267565571a1d42d3a3051/test/tracing/performanceBenchmark.test.ts#L1)가 타이밍을 assert하지 않는 smoke test라고 밝힌다. concurrency 100의 span 생성/오류/속성을 검증한다. | 이 파일명을 보고 서비스 처리량이나 UI 성능 수치로 인용하면 안 된다. |

## 4. 공개 데모/보고서에서 실제로 읽힌 내용

[Langfuse demo](https://langfuse.com/docs/demo)는 생성 → trace 찾기 → 공유 프로젝트 탐색의 3단계 안내와 Chat/Voice/Image/Sentiment/RPS 모드를 제공한다. 이번에는 생성 버튼을 누르지 않았다. EU 지역 링크는 sign-up/Loading으로 이어졌고 특정 공개 trace는 무료 읽기 도구로 접근하지 못했다. 따라서 ‘트리를 클릭해 보았다’거나 ‘필터가 빨랐다’는 표현은 사용하지 않는다.

[promptfoo 공개 o4-mini 보고서](https://www.promptfoo.dev/models/reports/o4-mini)는 39개 category, severity/search/sort/reset 제어, category의 실패 비율과 전체 요약을 실제 페이지 텍스트로 제공한다. 이는 일반 eval matrix의 실사용 조작을 대신하지 못한다. 이 페이지의 ‘performance’는 보안 probe 성적이며 UI 속도가 아니다. 추출 내용에는 3 critical findings 요약과 뒤쪽 framework 설명의 ‘no critical vulnerabilities’가 함께 나타난다. 범주/프레임워크의 범위 차이가 가능한 만큼 이 둘을 단일 수치로 합치거나 모순만으로 성능 평가를 내리지 않는다. RECHECK에 가져올 교훈은 headline의 단위와 하위 판정의 단위를 드러내야 한다는 것이다.

## 5. RECHECK 소스에 대입한 판단

이번에 `demo/src/TraceExplorer.tsx`, `CaseJournal.tsx`, `MeasuredReview.tsx`, `evidenceInspector.css`를 읽었다. 기존 구현이 단순 로그만 있다는 평가는 부정확하다. 이미 다음을 갖고 있다: 2개 저장된 trace 선택, 깊이별 span과 waterfall, 오류/부모 ID/이벤트 원본 상세, receipt와 SQL payload 대조, 부하 phase 선택과 지표 상세, 전체/차단/기록·재시도 필터와 필터 빈 상태. 저장된 로컬 증거를 실시간 서비스와 구분하는 문구도 있다.

그러나 이 요소들은 여러 설명 문단 사이의 개별 섹션으로 놓여 있고, 선택이 다음 증거로 이어지는 경로는 제한적이다. 새로운 필터 버튼만으로 해결되지 않는 이유가 여기 있다.

| 현재 코드의 구체적 한계 | 다음 단계로 필요한 UI 연결 | 참고할 부분 |
|---|---|---|
| CaseJournal은 로그 분류와 raw JSON 펼치기까지만 제공한다. | 요청 한 건을 선택하면 같은 ID의 판정, receipt, SQL 확인, trace 단계가 한 workspace에서 함께 바뀌도록 한다. | Langfuse의 선택 context + navigator/detail 구조 |
| TraceExplorer는 span 이름을 selection key로 사용한다. 현재 fixture는 failed 5개/recovered 6개이고 이름 중복은 없다. 일반화하면 같은 model call/retry 이름이 여러 번 나타날 수 있다. | 안정적인 span ID로 선택하고, 실패→복구 비교는 동일 이름이 아니라 대응 단계 관계로 연결한다. 이름 충돌은 현재 재현된 오류가 아니라 확장 시 코드 위험이다. | Langfuse node ID cache, promptfoo test/prompt hash |
| 실패/복구 trace를 바꾸면 각각의 최대 시간으로 scale을 다시 계산한다. | 전/후 시간이 비교 목적이면 공통 축 또는 서로 다른 축임을 명시한다. 현재는 두 요청의 각 모양을 읽기 좋지만 같은 막대 길이로 duration을 비교할 수 없다. | promptfoo의 동일 입력·같은 비교 열, Langfuse의 공통 time axis |
| TraceExplorer는 입력 fixture 전체를 직접 map하고 계층은 padding으로 표현한다. 5~6행에서는 합리적이다. | 먼저 parent relation과 선택 경로를 명확히 하고, 실제 대량 데이터가 생긴 후 collapse/search/windowing을 추가한다. 현재 규모에 복잡한 virtualization은 우선순위가 낮다. | Langfuse의 search ancestor 보존 |
| 480px 이하에서 service 보조 텍스트가 8px, duration 9px로 줄어든다. | 좁은 화면에서는 한 행의 내용량을 줄이고 선택 상세에 service/숫자를 옮긴다. 단순 축소보다 재배치가 필요하다. 실기기 가독성/접근성 실패를 재현했다고 말하지는 않는다. | Langfuse mobile sheet, promptfoo full-width detail |
| SustainedReview는 phase를 누르면 아래 지표가 바뀌지만 특정 504의 증거로 직접 이어지지 않는다. | 과부하 구간 → 결과 cohort → 504 한 건 → DB 저장/응답 실패 경계를 한 흐름으로 연결한다. 집계 차이와 원인을 사용자가 스스로 대조할 수 있어야 한다. | 분모를 가진 matrix + 세부 판정 drawer |

### 권장 화면의 최소 구성

첫 화면의 문장과 대표 결과는 유지하되, 주된 탐색 영역은 한 개의 ‘요청 검토’ workspace로 만든다. 왼쪽에는 대표 실패/복구/과부하 결과 목록, 가운데에는 공통 단계/시간축, 오른쪽에는 선택한 요청 또는 span의 판정과 근거를 둔다. desktop은 master/detail, mobile은 목록→상세의 한 단계 전환으로 정리한다. 선택한 trace/receipt ID, 데이터가 저장된 측정인지 현재 실행인지, 그 시각과 실험 조건을 상단에 붙인다.

검색/필터 추가는 이 다음이다. 필터가 걸려도 선택 요청의 식별자가 흔들리지 않아야 하고, ‘해당 결과 없음’, ‘아직 실행 안 됨’, ‘조회 실패’, ‘이 증거는 수집하지 않음’은 서로 다른 상태여야 한다. 재실행을 제공할 때는 원래 결과와 새 실행을 나란히 남기고, UI에서 기록을 다시 보여주는 playback과 실제 API 실행을 구분해야 한다. promptfoo의 edit/replay 분리 상태는 참고할 만하지만 trace-fetch 실패를 숨기는 동작은 복제하지 않는다.

완료 기준도 ‘버튼 작동’보다 사용자의 검토 과정을 기준으로 잡는다: 504 한 건이 SQL 기록을 남겼는지, 실패 span의 부모가 무엇인지, 복구 후 어떤 단계가 추가됐는지, 필터를 적용한 집계의 분모가 무엇인지, 링크를 열어 같은 근거에 도착하는지. 이 과정이 연결되면 UI 수준이 달라진다. 이번 감사는 그 설계 근거를 제공하며 해당 개편을 구현하거나 검증한 보고서는 아니다.
