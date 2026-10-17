# 공개 ML 서비스 발표·화면 증거 심층 검토

조사일: 2026-10-17. 대상: 사용자가 지정한 **밥벌이(SKN27-FINAL-1Team)**, **Phoenix**, **Evidently**. 기존 9개 저장소 개요와 달리 실제 이미지·GIF 프레임, 화면 분기 코드, 평가 문서의 분모까지 확인했다. 이 조사 담당자는 원격 제품에 로그인하거나 업로드·추론·부하 시험을 실행하지 않았다. GIF는 공식 파일에서 지정 프레임을 추출해 보았으며 연속 재생·직접 클릭으로 집계하지 않는다. 다른 담당자의 로컬 실험과 별도 기록이다.

가장 직접적인 참고점은 Phoenix의 **Trace Status OK와 QA incorrect를 함께 보여주는 화면**, Evidently의 **전체 성공·실패 분모를 유지한 상태별 상세**, 밥벌이의 **사용자 과업→입력→검토→실제 저장 구분**이다. 상용 규모나 합격 실적을 의미하지 않는다. 세 프로젝트의 채용 합격 여부는 이번 근거에서 확인하지 않았다. Phoenix 최신 README는 Elastic License 2.0을 명시하므로 세 대상을 엄밀하게는 ‘공개 소스 참고 프로젝트’로 묶는다.

## 1. 근거 범위와 고정 버전

| 대상 | 이번 고정 버전 | 실제 확인 | 미확인 |
|---|---|---|---|
| 밥벌이 | `2eaca8d78c53ed0c88f1af76c27ba27e3dd58d1c` | README, Home/ReceiptOcr JSX·CSS, 평가 문서 2개, desktop/mobile hero 원본 이미지 | 실제 서비스 DOM·렌더링·로그인·OCR·추천, 공식 YouTube 재생, 모바일 실기 |
| Phoenix | 앱 `c9a3087027fedff23c32b083534d0a16bcce1a25`, 공식 asset `f5ab6367204da8393255359b7cbfb7d38f1374ce` | 공식 RAG GIF 5개 프레임, 평가 화면 PNG, 상세/loading/빈 결과/필터 오류 소스 | 현 버전 앱 상호작용, 추론 새 실행, 모바일, GIF와 현 소스의 UI 완전 일치 |
| Evidently | 앱 `34771fe41c08ca074d96a52aaf4a45cd640cbaf5`, README 연결 docs asset `eb1630cdd80d31d55921ff4d34fc7b5e6e9c9f90` | Report·Dashboard GIF 각 5개 프레임, loading/error/theme 소스 | 현 서버 클릭·평가 실행, 모바일, GIF와 현재 버전 동일성 |

공식 GIF·PNG는 과거 시점 UI일 수 있다. 최신 소스와 같은 파일로 취급하지 않았다. 특히 Evidently Dashboard GIF에는 **EVIDENTLY AI CLOUD**, 조직 선택·Upgrade·사용자 메뉴가 보인다. 공식 README의 제품 시각 자료이지만 OSS UI에서 해당 관리 기능을 모두 제공한다는 증거는 아니다.

## 2. 밥벌이: 사용자 과업의 연결과 실제 검증의 깊이

- 저장소: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN27-FINAL-1Team
- README 고정 링크: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN27-FINAL-1Team/blob/2eaca8d78c53ed0c88f1af76c27ba27e3dd58d1c/README.md
- README 공개 주소: `www.bobbeori.com` — 링크 확인만 했으며 이번 실행에서 방문하지 않음.
- 공식 시연: https://www.youtube.com/watch?v=HttAWapHMdk
- 공식 광고: https://www.youtube.com/watch?v=Q-JacxpNduw
- 공식 MCP 사용: https://www.youtube.com/watch?v=G3C5Ci9yciI

README 최상단은 캐릭터 로고→서비스 한 문장→스택 배지→**광고/시연/MCP 3개 동등 폭 썸네일**→목차→팀 역할→문제→기능→구조→평가 순서다. ‘영수증→재고→요리→장보기’로 사용자의 일이 어떻게 이어지는지 먼저 설명한다. 팀원별 기술 이름뿐 아니라 배포, OCR 품질, 백엔드 라우팅, GraphDB, ML 추천 책임이 분리되어 있다. 다만 스택 배지가 길고, 기능별 화면 및 하단 ‘화면 구성’에는 삽입용 HTML 주석이 남아 있다. **상단 실제 영상 링크가 있으므로 ‘시연 자료 없음’은 틀린 결론이다.** 영상으로 이동하지 않고 README만 읽는 독자는 화면별 성공·실패 상태를 한눈에 비교하기 어렵다.

### 2.1 첫 화면부터 복구까지: 소스에서 확인한 경로

| 단계 | 구체적 근거 | 확인 수준 |
|---|---|---|
| 홈 첫 화면 | `HeroSection` activeIndex=0: ‘냉장고 관리 / 재고와 소비기한을 한눈에 / 내 냉장고 보기’. 다음 슬라이드는 ‘영수증 한 장으로 재료를 한 번에 / 영수증 등록하기’. 6초 순환, 앞뒤·점 선택·포인터 스와이프 | JSX 읽음. 실제 애니메이션·클릭 미검증 |
| 영수증 진입 | 비로그인 시 ‘로그인이 필요해요’와 ‘로그인하고 영수증 등록하기’. 홈 진입과 실제 분석의 인증 경계가 다름 | JSX 읽음. 인증 서비스 미검증 |
| 입력 | JPEG/PNG/WebP, 최대 5장, 장당 10MB, 총 25MB 제한 상수. 다중 이미지 순서 검토와 수동 crop 분기 | 소스 읽음. 실제 파일 검증·업로드 안 함 |
| 진행 | UPLOAD→ANALYZE→CONFIRM→STOCK 4단계, 업로드 직후 기존 결과 비움. ‘영수증을 분석하고 있어요 / 품목과 금액을 읽는 중’과 스피너·스캔 상태, 처리 중 재업로드/영역조정 비활성화 | 소스 읽음. SSE 속도·진행표시의 실제 타이밍 미검증 |
| 결과 검토 | 왼쪽 업로드 영수증, 오른쪽 분석된 식재료 수와 원재료명/표준명·수량·보관방법 등 편집. 매장·구매일 수정, 전체 확인·품목 추가. OCR 완료와 냉장고 입고가 별도 | JSX 읽음. 렌더링·저장 성공 미검증 |
| 빈 결과 | ‘인식된 품목이 없어요.’ 아래 ‘카드전표처럼 품목 리스트가 없는 영수증일 수 있어요. 필요한 품목은 아래에서 직접 추가해주세요.’ | 소스 문구 확인. 추론 실패라고 자동 판정하지 않음 |
| 낮은 품질 | manual_crop 요청은 영역 수정, needs_reupload 요청은 재촬영·다른 이미지 첨부 안내. 단순 범용 에러와 구분 | 소스 읽음 |
| 오류/취소 | SSE error·HTTP 오류→분석 실패 dialog, UPLOAD로 복귀; 저장 실패는 별도 dialog. `uploadRunIdRef` 검사로 새 업로드/취소 뒤 이전 결과 반영을 막는 코드 | 소스 읽음. 경쟁 상황 재현 안 함 |

소스: [HeroSection.jsx](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN27-FINAL-1Team/blob/2eaca8d78c53ed0c88f1af76c27ba27e3dd58d1c/app/frontend/pages/home/sections/HeroSection.jsx), [ReceiptOcr.jsx](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN27-FINAL-1Team/blob/2eaca8d78c53ed0c88f1af76c27ba27e3dd58d1c/app/frontend/pages/receipt_ocr/ReceiptOcr.jsx). 주요 줄: 상수 31–43, 업로드 1043–1208, stepper/분기 1848 이후, 빈 결과 2174 이후. 실제 버전의 줄 번호에만 해당한다.

### 2.2 색·글자·여백: 이미지 관찰과 CSS 사실 분리

**실제 열어 본 원본 이미지** `hero_3.png`는 넓은 가로 구도다. 왼쪽은 크림·살구빛 주방 벽과 빈 공간, 오른쪽은 열린 냉장고와 정돈된 재료, 아래는 숟가락을 든 감자와 밥 캐릭터다. 냉장고 재료에 초록 체크와 노란 느낌표를 얹어 관리의 의미를 미리 전달한다. `hero_3_mobile.png`는 세로 구도로 냉장고가 가운데를 채우고 캐릭터가 아래로 모인다. **이것은 배경 아트이며 완성된 화면 캡처가 아니다.** 문구·버튼 겹침이나 읽기 쉬움은 원본만으로 검증할 수 없다.

**소스 수치**는 단순 ‘초록색 친환경 디자인’ 요약을 반박한다. index.css에는 green 토큰도 있지만 실제 body는 `--figma-bg: #fff`, 글자 `#2e1b12`, 보조 `#6f4b36`, coral `#ff6b74`를 참조한다. 최종 hero CSS는 배경 `#fff3ec`, eyebrow `#c74650`, CTA `#b43d46`/흰 글자다. 폰트는 로컬 Pretendard 400/500/600/700 선언. hero 제목은 34–48px clamp, 줄높이 1.18, -0.04em; CTA 최소높이 48px·radius12px·상단간격20px; 콘텐츠 padding30/42/32/30px. 이미지가 따뜻한 톤을 만들고 텍스트·버튼은 진한 갈색/붉은 계열로 대비를 준다는 **소스 기반 설명**이다. CSS에 weight900을 요청하지만 선언된 Pretendard 파일은 최대700이므로 실제 굵기 렌더링은 별도 확인이 필요하다.

모바일은 `<picture>` 680px/1080px 분기와 별도 아트가 있다. 주간 레시피는 680px 이하에서 최소270px 또는82vw 카드의 수평 스크롤을 사용한다. 모바일 구현 의도는 확인했지만 수평 잘림·터치 대상·화면회전·키보드 동작은 검증하지 않았다. 별도 모바일 이미지가 있다는 사실을 모바일 사용성 통과로 바꾸지 않는다.

### 2.3 성능·정확도: README 숫자 뒤 문서가 더 유용하다

README의 200발화/17intent 비교는 Rule66.5%·0.0001s, LLM75.0%·1.4833s, Hybrid88.5%·1.5380s다. OCR은 GPT-5.4 mini3.17s·$0.0033·88.9% 등을 제시한다. **모두 저자 보고이며 이번에 재현하지 않았다.** OCR의 표본 크기·이미지 조건·정확도 정의·가격 산정 시점은 읽은 README 표만으로 확정할 수 없다. 평균 지연을 p95나 현재 배포 지연으로 바꾸어 쓰지 않는다.

반면 [agent_evaluation_results.md](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN27-FINAL-1Team/blob/2eaca8d78c53ed0c88f1af76c27ba27e3dd58d1c/docs/agent_evaluation_results.md)는 2026-07-28의 별도 실험을 훨씬 구체적으로 적는다.

- 240개 도메인 문항+실패 회귀4=244; 초기·최종 공통 Alarm 외부 연동 오류16제외, **228개 채점**.
- gpt-4.1-mini·temperature0, 관련성4+유용성4+완결성2. 초기커밋`e50c918` 대비 최종 작업 코드의 품질73.9→86.0/100.
- 분류197/244=80.7%, 라우팅216/244=88.5%, 쓰기Action45/73=61.6%, Argument223/228=97.8%, 엄격TaskCompletion122/228=53.5%.
- TaskCompletion은 **실제 DB 변경 성공률이 아니라 응답 계약 완료율**이라고 직접 한계를 명시한다. 실행 전후 DB는 별도 기능시험 대상으로 둔다.
- 7/26 이전 결과·인프라 오류18건·평가 시드 미준비로 보류한 회귀사례도 남겼다. ‘0점’의 원인이 실제 모델 실패인지 실행기의 상태 준비 부족인지 구분한다.

README의 **200개88.5%**와 평가문서의 **216/24488.5%**는 동일 실험이라고 합치면 안 된다. `agent_evaluation_metrics.md`의 p95 8초/도구 없는 조회4초는 ‘초기 목표’이며 실측 성공 수치가 아니다. README의 테스트 총388과 항목209+97+55+27+15=403도 단순 합이 일치하지 않는다. 카테고리 중복 여부를 확인하지 않았으므로 허위라고 단정할 수 없지만 그대로 검증완료 숫자로 인용하면 안 된다.

**RECHECK에 유효한 점:** 과업이 끝났는지를 ‘답변 생성’, ‘검토’, ‘DB 반영’으로 구분하고, 좋은 총점과 낮은 엄격완료율을 함께 공개하는 방식이다. 전면 캐릭터·자동 캐러셀·로그인 경계를 그대로 복제할 이유는 없다. 면접 시연은 첫 현상까지 짧아야 하므로 6초마다 바뀌는 첫 행동보다 고정된 핵심 행동 하나가 더 적합하다는 설계 판단이다.

## 3. Phoenix: 요청 성공과 판단 품질을 같은 화면에서 분리

공식 README: https://github.com/Arize-ai/phoenix/blob/c9a3087027fedff23c32b083534d0a16bcce1a25/README.md

공식 파일을 다운로드한 뒤 직접 연 이미지:

- [RAG trace GIF](https://raw.githubusercontent.com/Arize-ai/phoenix-assets/f5ab6367204da8393255359b7cbfb7d38f1374ce/gifs/llama_index_rag_tracing.gif): 884×480,85프레임,메타데이터 기준8.50초. 프레임0/21/42/63/84를 검토.
- [document evals 화면](https://raw.githubusercontent.com/Arize-ai/phoenix-assets/f5ab6367204da8393255359b7cbfb7d38f1374ce/images/screenshots/document_evals_on_traces.png): 3804×1900. UI 위의 청록색 화살표·설명 상자는 편집된 주석이며 제품 기능이 아니다.

### 3.1 GIF에서 실제 관찰한 순서

| 시점 | 관찰 | 해석 제한 |
|---|---|---|
| 0.0초 | 어두운 표 화면. 요청 이름·입력/출력·시작/지연/상태 열 | 앱의 최초 onboarding 화면이 아니라 이미 데이터가 있는 목록 |
| 2.1초 | Trace Details. 왼쪽 query→retrieve→embedding/synthesize 계층, retrieve 선택; 오른쪽 Documents와 검색 문서 카드 | 저자 녹화에서 선택 결과가 보임. 내가 클릭한 기록 아님 |
| 4.2초 | 왼쪽 embedding 선택; 오른쪽 text-embedding-ada-002와 입력 질문 카드 | 실행중 화면이 아니라 이미 저장된 span 검사 |
| 6.3초 | templating 선택; Attributes의 구조화 텍스트 | 작은 원본으로 모든 속성값 판독하지 않음 |
| 8.4초 | llm 선택; Messages/Invocation Parameters, 보라색 system·중성 user·초록 Output. 질문은 Arize training data 관련, 답변은 지원한다는 한 문장 | 모델 정답·현재 기능 여부를 독립 검증한 것은 아님 |

색은 거의 검정에 가까운 청회색 바탕, 얇은 중성 경계선, 선택 span의 밝은 외곽선, retriever 청록/embedding 보라/llm 주황의 **종류별 보조표식**이다. 줄기 선과 들여쓰기가 부모자식을 설명한다. 일반 레이블은 sans serif, 메시지·속성 본문은 monospace로 구분된다. 왼쪽은 좁은 탐색/시간 맥락, 오른쪽은 넓은 근거 카드로 나뉘며 선택을 바꿔도 원래 요청 경로가 남는다. 정확한 CSS 픽셀·폰트 가족은 과거 GIF에서 추정하지 않았다.

평가 PNG는 특히 중요하다. 상단에 **Trace Status OK, Latency2.13s**가 있고, 동시에 **Hallucination hallucinated, QA Correctness incorrect** 배지가 있다. 선택된 retrieval 문서에는 score0.78과, 별도의 Relevance `irrelevant`/score0.00 및 설명이 있다. 검색 점수와 평가 점수까지 다른 의미로 표시한다. ‘API가 정상 종료했으니 답도 안전하다’는 오해를 실제 화면 구조로 막는다. RECHECK의 실행 성공/시점 유효성/실제 기록 여부도 이런 식으로 각각 이름 붙여야 한다.

### 3.2 현재 소스에서만 확인한 loading·오류·빈 결과

- [TracePage.tsx](https://github.com/Arize-ai/phoenix/blob/c9a3087027fedff23c32b083534d0a16bcce1a25/js/app/src/pages/trace/TracePage.tsx): Suspense fallback Loading. 과거 GIF에서 이 loading을 직접 보지는 않았다.
- [ProjectTableEmpty.tsx](https://github.com/Arize-ai/phoenix/blob/c9a3087027fedff23c32b083534d0a16bcce1a25/js/app/src/pages/project/ProjectTableEmpty.tsx): ‘No traces found that match the selected filters’. 데이터 부재와 필터 조건을 연결한다.
- [DSLFilterErrorFallback.tsx](https://github.com/Arize-ai/phoenix/blob/c9a3087027fedff23c32b083534d0a16bcce1a25/js/app/src/pages/project/DSLFilterErrorFallback.tsx): 필터 입력을 계속 보여주고 ‘Editing the filter above reloads the view.’ 오류를 수정할 행동이 같은 위치에 있다. 상세 오류는200자로 제한.

첫 화면→입력→loading→결과→오류를 **한 버전의 연속 실험으로 검증하지 못했다**. 목록→상세·span검사는 공식 녹화 프레임으로, loading/오류/empty는 현재 소스로만 확인했다. 모바일은 미검증. 0.87s·2.13s 등 화면 속 값은 개별 녹화/캡처 데이터이며 서비스 성능 benchmark가 아니다.

## 4. Evidently: 분모·조건·실패 원문을 한 문맥에서 유지

공식 README: https://github.com/evidentlyai/evidently/blob/34771fe41c08ca074d96a52aaf4a45cd640cbaf5/README.md

README가 연결한 파일을 그대로 다운로드했다.

- [Report GIF](https://raw.githubusercontent.com/evidentlyai/docs/eb1630cdd80d31d55921ff4d34fc7b5e6e9c9f90/images/concepts/report_test_preview.gif): 1436×870,60프레임,6.16초. 0/15/30/45/59검토.
- [Dashboard GIF](https://raw.githubusercontent.com/evidentlyai/docs/eb1630cdd80d31d55921ff4d34fc7b5e6e9c9f90/images/dashboard_llm_tabs.gif): 1438×818,49프레임,6.56초. 0/12/24/36/48검토. 화면은 Cloud로 식별됨.

### 4.1 Report: 결과에서 실패의 실제값까지

0.00초 Metrics의 Dataset Summary는 Metric/Current/Reference 열을 보인다. 1.76초에는 Age/Salary의 두 데이터 통계와 빨강current/회색reference 분포 막대를 함께 둔다. 3.36초 Tests로 이동한 상태에는 **20 SUCCESS /0 WARNING /9 FAIL /0 ERROR**가 넓은 한 줄로 유지된다. 4.72초에는 ‘All tests’ 아래 ‘By test status’ 선택지가 펼쳐져 있다. 5.84초에는 ‘Failed tests’ 섹션과 빨간 윤곽 느낌표·연분홍 행이 보인다.

마지막 프레임에서 `Quantile 0.25 of Age`는 Actual36.0과 Expected26.75±2.675를 함께 보여준다. 표의 실패값이 단순 ‘틀림’ 표시로 끝나지 않는다. FAILURE와 ERROR는 별개 카운트다. 시험 조건 불충족과 실행 실패를 분리하는 사고방식이 화면에도 이어진다. 필터를 바꿔도 상단 전체 분모가 남아 실패만 본다는 맥락을 잃지 않는다.

시각적으로 흰 바탕·얇은 회색 card 경계·검은 타이포에 빨강 탭 밑줄만 강한 강조를 준다. 상단 큰 숫자는 네 등분되어 읽히며, 아래 항목은 제목 한 줄+작은 실제/기대 설명 한 줄로 반복된다. 연분홍/연초록 채움에 아이콘·텍스트를 함께 써 색만으로 결과를 전달하지 않는다. 반면 과도하게 긴 소수점(예: 2.6750000000000003)은 사람에게 읽기 불편하다. RECHECK의 표시값은 적절히 반올림하고 JSON 원문 정밀도는 보존하는 개선 판단이 가능하다.

### 4.2 Dashboard: 동일 범위에서 지표를 바꿈

0.00초는 Recipe chatbot 프로젝트의 Tests 탭이다. 상단 날짜범위, `Show in order`, 탭 줄이 남고 본문만 바뀐다. 시간 네 열×시험 행의 녹색/빨강 matrix와 SKIPPED/SUCCESS/WARNING/FAIL/ERROR 범례가 있다. 1.44초 Hallucinations는 ‘Do the responses contradict the context?’, 3.04초 Denials는 ‘Does the chatbot deny a response?’, 4.48초 Text Length는 ‘What is the conversation length?’, 6.00초 Sentiment는 ‘Sentiment for answer: values in time’ 차트다.

지표 이름을 클릭했을 때 차트 제목이 **그 지표가 답하는 질문**으로 바뀐다. RECHECK의 ‘p95’,‘유효 응답’,‘보류’를 설명할 때도 기술명만 적기보다 ‘요청 대부분이 이 시간 안에 끝났는가’,‘답이 사용 시점에 유효했는가’와 연결하는 편이 읽기 쉽다. 다만 chart의 빨강이 current분포에도 쓰이고 실패에도 쓰이므로 시각자료만 떼어내면 의미가 혼동될 수 있다. 항상 범례/맥락과 묶어 읽어야 한다.

### 4.3 현재 소스와 실행 범위

[RenderPanelByDataFetchGeneralComponent.tsx](https://github.com/evidentlyai/evidently/blob/34771fe41c08ca074d96a52aaf4a45cd640cbaf5/ui/packages/evidently-ui-lib/src/components/Dashboard/GeneralHelpers/RenderPanelByDataFetchGeneralComponent.tsx)는 데이터가 없을 때 제목·부제·높이를 유지하는 skeleton을 반환한다. [error.tsx](https://github.com/evidentlyai/evidently/blob/34771fe41c08ca074d96a52aaf4a45cd640cbaf5/ui/packages/evidently-ui-lib/src/router-utils/components/error.tsx)는 페이지 오류에서 ‘Something went wrong’과 상태코드/상세를, action오류에서 닫을 수 있는 snackbar를 보여준다. 이 오류를 이번에 실제 일으키지 않았다.

[theme/index.tsx](https://github.com/evidentlyai/evidently/blob/34771fe41c08ca074d96a52aaf4a45cd640cbaf5/ui/packages/evidently-ui-lib/src/theme/index.tsx)는 현재 버전의 accent`#ed0500`, light text`#09090b`, radius5px, tabs gap10px, OS sans font stack, Paper 그림자 제거·1px테두리를 명시한다. 현재 소스 사실이며 GIF의 모든 픽셀을 이 값으로 설명하지 않는다.

두 GIF는 **완성된 데이터의 탐색**을 담는다. 데이터 업로드→평가 계산→loading→결과의 종단 경로가 아니므로 ‘ML 평가를 실행했다’고 말할 수 없다. 앱 입력 오류·서버 실패·empty와 모바일은 미검증이다. Report의20/9 카운트는 예제 데이터이지 제품 품질·성능을 평가한 수치가 아니다.

### 4.4 로컬 상호작용을 위한 공식 저장 보고서 발견

현재 main tree에는 export보고서HTML이 없고 앱 index파일만 있었다. 과거 공식 tag **v0.4.40**, commit`8d50976ad34a30417e51801503af8b0eab574c93`에서 다음 저장 보고서를 찾았다. 부모 담당자에게 URL 전달했으며 이 보고서에서는 직접 실행 완료로 세지 않는다.

https://raw.githubusercontent.com/evidentlyai/evidently/8d50976ad34a30417e51801503af8b0eab574c93/examples/integrations/streamlit_dashboard/projects/bike-sharing/reports/2011-02-12_2011-02-18/data_drift.html

동일 폴더에 data_quality.html(2.85MB),model_performance.html(3.33MB),target_drift.html(3.09MB)이 있다. data_drift.html은2.88MB다. 원본HTML을 로컬에서 열어 필터·차트 조작을 하면 ‘공식 저장 보고서 로컬 조작’ 근거를 추가할 수 있지만 현재 Evidently 서버 실행·새 평가 계산으로 표현하면 안 된다.

## 5. RECHECK에서 구체적으로 바꿀 만한 표현·검증 기준

이는 외부 프로젝트의 장점을 근거로 제안한 설계 판단이며 사용성 실험으로 우위를 증명한 결과는 아니다.

1. **첫 현상과 증거를 붙인다.** ‘오래된 판단 재현’ 바로 아래에 지금 바뀐 정보와 생성 당시 정보, 현재 수용 여부를 함께 둔다. Phoenix의 선택 span→근거 패널처럼 결과에서 원문으로 이동할 때 요청 문맥을 남긴다.
2. **성공의 축을 나눈다.** 요청 완료/판단 유효/최종 기록을 독립된 상태로 이름 붙인다. Phoenix의 OK+incorrect 화면과 밥벌이의 OCR완료→검토→입고 경계가 직접적인 근거다.
3. **전체 분모를 고정한다.** 차단·보류·거절만 보는 필터를 켜도 총요청/분모를 숨기지 않는다. Evidently의20/9와 오류별 분류처럼 사용자에게 지금 무엇만 보고 있는지 알려준다.
4. **loading은 결과 자리에서 보여준다.** 확정 안 된 답은 결과처럼 먼저 보여주지 말고 ‘추론 중/검증 중/기록 중’의 실제 상태를 표시한다. 서버가 보내지 않은 세부단계나 퍼센트를 UI 타이머로 사실처럼 꾸미지 않는다.
5. **빈 결과와 장애를 다르게 안내한다.** ‘선택한 조건에 해당 요청 없음’에는 필터 해제, 입력으로 만들 수 없는 결과에는 입력 수정, 장애에는 재시도와 진단ID를 붙인다. Phoenix는 오류 뒤 필터를 유지하고 밥벌이는 인식품목0개에서 수동추가를 제시한다.
6. **성능을 다른 문제와 섞지 않는다.** 평균/백분위, 성공만/전체, 저장보고서/새실행, 응답계약/DB상태를 각각 명시한다. README 숫자와 보고서 분모가 다를 때 같은 benchmark로 합치지 않는다.
7. **작은 화면에서 남길 것을 정한다.** 관측 도구의 전체 dense table을 그대로 줄이지 않는다. 입력 변경·현재 결과·한 개 증거 링크를 먼저 유지하고 세부 trace는 별도로 연다. 이것은 이번 모바일 미검증을 보완하기 위한 제안이며 모바일 통과 판정이 아니다.

## 6. 실제 시각 검토 목록과 재검증 절차

원본과 SHA256·규격·검토 프레임은 `asset-manifest.json`에 기록했다. 이미지를 다른 사이트 자료로 재게시한 것이 아니라 조사용 로컬 보관이다. 사용자가 완성물에 재사용하려면 프로젝트 라이선스/asset 권한은 별도 확인해야 한다.

- 밥벌이 hero desktop/mobile2개: 원본을 열어 관찰. 배경 아트만, 화면캡처 아님.
- Phoenix GIF프레임0/21/42/63/84: 5개 contact sheet로 확인; 마지막84는 별도로 원본 해상도 열람.
- Phoenix evaluation PNG1개: 전체 화면을 열어 OK/incorrect와 relevance조건 확인.
- Evidently Report프레임0/15/30/45/59: 5개 contact sheet로 확인; 마지막59 별도 원본 해상도 열람.
- Evidently Dashboard프레임0/12/24/36/48: 5개 contact sheet로 확인; 첫0 별도 원본 해상도 열람.

이상 원본 **6개(정지3+GIF3)**, GIF 샘플 **15프레임**의 실제 시각 검사다. 접촉시트의 회색 여백과 타임스탬프는 조사자가 생성한 외곽이며 원래 제품 UI가 아니다. 파일 다운로드·프레임 추출은 공용 원본을 읽기만 했고 유료 원격 자동화·지갑·공개 서버 부하 시험은 사용하지 않았다.
