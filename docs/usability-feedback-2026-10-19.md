# 전달받은 사용 피드백과 화면 보완

## 입력과 확인 범위

2026-10-19 KST에 프로젝트 작성자가 전달한 지인 1명의 체험 후 답변을 근거로 삼았습니다. 관찰자가 실시간으로 행동을 기록한 연구나 실제 은행 고객의 이용 실적은 아닙니다. 실제 체험 일시, 기기·브라우저, 도움 제공 여부, 소요 시간은 확인되지 않았습니다. 점검 당시 배포 버전도 응답만으로 확정하지 않습니다.

| 문항 | 전달받은 답변 | 해석 |
|---|---|---|
| 1 | 그냥 은행이랑 비슷하게 송금 하는 내용인것 같음 | 은행·송금 상황은 인식했지만, 상담 기록 검증 체험의 목적을 설명하지는 않음 |
| 2 | 한도가 100만원으로 바뀐 결과를 봄 / 검증 결과를 봤지만 뭔지 모르겠음 | 한도 변경은 인식했지만 검증 결과의 의미를 이해하지 못했다고 보고함 |
| 3 | 새로고침을 했을 때 아까 결과 그대로 나옴 | 새로고침 뒤 같은 결과를 보았다고 보고함. 재검증·중복 방지의 기술 검증으로 해석하지 않음 |

답변 3개를 과제 성공 3/3으로 집계하지 않습니다. 실제 행동과 실패 원인은 이 답변만으로 확정할 수 없습니다.

## 1차 변경 범위 (`2e41e27`)

기준 커밋: `f62ec35bec77c9477a2f0509e4e0c4d13eddde8e`.

- 첫 화면 제목을 **한도 변경 후 이전 답변 차단**으로 바꾸고, 가상 은행 상담 사례이며 실제 송금은 없다는 설명을 붙였습니다.
- 이번 실행 결과를 상세 재현·로그보다 위에 배치했습니다. 이전 답변 차단의 이유, 새 답변 기록, 동일 요청 재시도를 나누어 설명합니다. 성공 응답을 확인하기 전에는 기록 완료로 표시하지 않습니다.
- 완료 후 **이번 실행 결과** 버튼은 같은 화면의 결과에 스크롤·키보드 초점을 옮깁니다. 기존 버튼은 별도의 과거 비교 실험 화면으로 이동했습니다. **세 방식 비교**는 별도 버튼으로 유지합니다.
- 새로고침 화면에 **이전 실행 기록**을 표시하고, 복원 자체가 새 실행이나 현재 서버 상태 확인은 아니라는 설명을 붙였습니다.
- 기존 시연 영상은 이전 화면의 촬영본임을 표시합니다. 영상의 API 실행 근거는 유지합니다.

서버의 기록·재시도 처리, 성능 측정 결과, 모델 구성은 변경하지 않았습니다. 차단은 금액의 크기를 비교하는 송금 심사가 아니라, 인용한 문서의 변경을 기록 직전에 검증하는 동작입니다.

## 검증과 후속 확인

로컬 프런트 테스트 **61개 통과**, 빌드 성공, 실제 Python API·SQLite를 이용한 Chromium 체험·복원·화면 검사가 통과했습니다. [검증 범위와 초기 환경 설정 실패](evidence/usability-2026-10-19/local-checks.json), [새로고침 검사](evidence/usability-2026-10-19/restoration.json), [화면·영상 검사](evidence/usability-2026-10-19/presentation.json)를 보존합니다. 공개 환경의 결과는 해당 배포 커밋의 워크플로와 구분해 확인합니다. 이번 보완에는 실제 API 체험의 완료 버튼 이동, 차단 직후 미완료 단계 표시, 응답 유실 시 완료 오표시 방지 검사를 포함합니다.

**사람을 대상으로 한 수정 후 재확인은 아직 하지 않았습니다.** 이해도 향상, 성공률 개선, 고객 이용 또는 비즈니스 성과로 기재하지 않습니다.

다시 확인할 때는 답을 먼저 설명하지 않고 다음 두 가지를 요청합니다.

1. 이 페이지가 무엇을 확인하는 곳인지 본인의 말로 설명해 주세요.
2. 실행을 마친 뒤, 어떤 답변이 기록되거나 차단됐고 왜 그런지 화면을 근거로 설명해 주세요.

같은 사람이 재확인하면 이미 체험한 학습 효과가 있으므로 첫 방문자의 이해도를 입증하는 자료로 일반화하지 않습니다. 실제 답변과 도움 제공 여부를 그대로 남깁니다.

## 1차 수정 화면

[첫 화면](evidence/usability-2026-10-19/entry-desktop.png) · [완료 결과](evidence/usability-2026-10-19/complete-1440.png) · [모바일 완료 결과](evidence/usability-2026-10-19/complete-390.png) · [새로고침 복원](evidence/usability-2026-10-19/restored-320.png)


## 후속 수정: 소개 화면에서 상담 작업 화면으로

같은 세 답변과 사용자의 추가 요구(출시된 서비스처럼 큰 제목·설명 제거)를 반영한 수정이다. 새로운 참여자나 수정 후 관찰 결과가 추가된 것은 아니다. 시작 기준은 `2e41e2786db4f246df58568654055d026ceb16ae`이며 기존 결과 요약·복원·단일 실행 컨트롤러는 보존했다.

| 확인된 문제 / 요구 | 수정 | 재확인할 내용 |
|---|---|---|
| 송금 상황만 기억하고 실제 목적을 설명하지 못함 | 큰 소개 제목·긴 설명·영문 표어·한도 변화 강조 숫자를 제거. 작은 ‘상담 기록’ 화면명, ‘답변 확인 시작’, 안내 문서·상담 답변·기록 처리로 첫 화면 구성 | 첫 화면을 보고 어떤 업무를 처리하는지 본인의 말로 설명 |
| 무엇을 확인하고 왜 차단했는지 알지 못함 | CSS로 숨겨졌던 확인 대상·차단 이유를 표시. 인용한 문서의 변경과 답변 유효기간을 기록 조건으로 명시. 300만 원 이전 답변과 100만 원 현재 안내를 결과 옆에 표시 | 어떤 답변이 기록되지 않았으며 그 이유는 무엇인지 화면을 근거로 설명 |
| 새로고침 뒤 같은 결과를 봄 | 이전 기록·브라우저 저장본·서버 확인 전 표시와 자동 재요청 없는 복원 유지 | 복원된 기록과 새로 실행한 결과를 어떻게 구분하는지 설명 |
| 발표용 화면처럼 큰 제목과 설명이 앞섬 | 모델 부하·장애 복구도 작은 화면명으로 변경. 저장된 실험 표시와 수치 출처는 유지. 실행 화면에서 실험 수치 홍보 영역 제거 | 바로 할 수 있는 작업을 찾는지 확인 |

서버의 버전 검증을 ‘두 금액을 비교하는 송금 심사’로 변경하지 않았다. 표시의 근거는 같은 문서 변경 사례이며 새 모델·인프라·API 계약 변경은 없다. 실제 금융 기능을 새로 제공하거나 상용 출시했다고 주장하지 않는다.

6단계 진행 표시는 접어서 볼 수 있고, 안내 문서·답변·처리 결과를 그 앞에 둔다. 두 실행 버튼은 기존 동일 컨트롤러를 사용한다. 키보드 이동도 화면 순서(이전 답변 → 처리 단계 → 다음 처리)와 일치하게 검사했다.

### 이번 실행 근거

- 프런트 61개 통과, 빌드 성공.
- 실제 로컬 Python API·SQLite에서 대표 흐름 13개, 복원 9개, 화면·영상 7개, 부하·복구 화면 6개 검사 통과. [범위·초기 검사 실패 기록](evidence/product-ui-2026-10-19/local.json)
- [대표 흐름](evidence/product-ui-2026-10-19/case.json) · [복원](evidence/product-ui-2026-10-19/restoration.json) · [화면 검사](evidence/product-ui-2026-10-19/presentation.json)
- 로컬 캡처: [첫 화면 PC](evidence/product-ui-2026-10-19/entry-1440.png) · [첫 화면 모바일](evidence/product-ui-2026-10-19/entry-390.png) · [차단 결과](evidence/product-ui-2026-10-19/blocked-1440.png) · [완료 모바일](evidence/product-ui-2026-10-19/complete-390.png)

수정 후 사람의 재확인은 아직 없다. 위 세 과제를 버튼이나 정답을 미리 설명하지 않고 다시 진행하고, 실제 발언·도움 여부를 기존 [기록 양식](usability-record.md)에 남긴다. 자동 검사는 이해도 개선을 입증하지 않는다.


### 공개 캡처에서 발견한 색 대비 보완

첫 수정 `5518507`은 [전체 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39206909242)와 [공개 브라우저 검사 80개](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39206909276)를 통과했다. 그 뒤 실제 배포 캡처를 눈으로 검토하면서, 차단 상태의 보조 문구에 기존 높은 선택자 우선순위의 연한 글자색이 남은 것을 발견했다. 자동 기능 통과와 시각 검토를 구분한다.

`interface.css`의 차단 상태 글자색을 어두운 갈색으로 수정하고, `check_case_browser.py`에 실제 계산 스타일의 텍스트/배경 대비 4.5:1 이상 검사를 추가했다. 로컬 API 대표 흐름 13개를 다시 통과했다. 이전 배포 원본은 [초기 공개 검사](evidence/product-ui-2026-10-19/initial-public.json)에 보존한다.

### 최종 공개 버전

- 구현 커밋: [`a9637b4`](https://github.com/sokldjs554/recheck-ml-serving/commit/a9637b482aaddf8eb65741552ae29ffdbde12c96). [현재 화면](https://sokldjs554.github.io/recheck-ml-serving/?v=a9637b4#case)
- [최종 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39207582696): 백엔드 159개 통과·SQLite 전용 1개 제외, 프런트 61개 통과, production build·자료 생성기·정적 번들 일치 확인. 백엔드와 실행 컨트롤러는 기준 커밋에서 변경하지 않았다.
- [최종 공개 브라우저 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39207582691): 81개 통과(Chromium 72개, macOS WebKit 9개). 대표 처리, 이중 클릭, 화면 이동, 중간·완료 복원, 명시적 초기화, 저장된 영상, 원본 근거, 키보드·반응형 배치를 확인했다. 차단 사유의 실제 텍스트 대비는 7.03:1이다.
- Render `dep-dbar4i8ae00c73a2fmgg`: 2026-10-19 15:03:54 KST live. [배포·CI 근거](evidence/product-ui-2026-10-19/final-deployment.json) · [공개 검사 항목·artifact](evidence/product-ui-2026-10-19/public.json)
- 최종 공개 캡처: [첫 화면](evidence/product-ui-2026-10-19/public-entry-1440.png) · [이전 답변 차단](evidence/product-ui-2026-10-19/public-blocked-1440.png) · [모바일 완료](evidence/product-ui-2026-10-19/public-complete-390.png) · [모바일 복원](evidence/product-ui-2026-10-19/public-restored-390.png)

이번 화면 수정과 배포 검증은 완료했다. 친구가 수정 후 화면을 다시 사용한 결과는 아직 없으며, 기존 발언을 재검증·중복 방지의 기술 검증으로 해석하지 않는다. 공개 검사는 저장 처리의 기능 확인이며 무료 서버의 첫 응답 지연이나 SLA 개선을 주장하는 자료가 아니다.

## 작업 흐름 재구성

시작 상태는 `feat/project-introduction`의 `08fb9d2e60bf2e77f553ac98ef56a2a0bc7cc077`이며 당시 미커밋 변경이 없고 `origin/main`과 같았다. 위의 1차·후속 변경을 되돌리지 않고 이어서 수정했다. 이번 입력도 같은 비전공자 친구 1명의 세 답변이며, 새로운 관찰 결과나 정량 조사 결과는 아니다.

### 확인한 참고 자료

2026-10-19 KST에 접근한 범위와 참고 목적을 구분한다. 아래 자료는 합격자 프로젝트 목록이 아니며, 코드·문장·디자인 자산·성능 수치를 가져오지 않았다.

| 자료 | 실제 확인한 범위 | 이번 작업에 적용한 원칙 |
|---|---|---|
| [공식 ML Backend Engineer 공고](https://toss.im/career/job-detail?job_id=6600650003) | 서버 설계·구현, 모델 응답 속도·처리량, 대규모 트래픽, MSA 추적, Kubernetes 및 선택의 비용 | 기술을 새로 늘리지 않고 기존 서버 구조·서빙·추적·비용 근거를 README에서 연결 |
| [Bank of Anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos) | README, [실제 frontend 템플릿](https://github.com/GoogleCloudPlatform/bank-of-anthos/blob/main/src/frontend/templates/index.html)의 잔액·작업·거래 기록 구조. [공개 사이트](https://cymbal-bank.fsi.cymbal.dev/)는 로그인 화면만 읽음 | 사용 화면에서는 작업과 상태를 먼저, 저장소에서는 아키텍처를 설명. 로그인 후 거래 조작은 미실행 |
| [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) | README와 [공식 메모리 누수 진단 시나리오](https://opentelemetry.io/docs/demo/feature-flags/recommendation-cache/): flag 활성화→metrics→지연 trace→속성 확인 | 저장된 실패·복구 trace와 SQL 대조를 이어서 읽도록 유지. 타 프로젝트를 직접 배포하거나 장애 주입하지 않음 |
| [BentoSentenceTransformers](https://github.com/bentoml/BentoSentenceTransformers) | README, `service.py`, `locustfile.py` 실제 소스. `/encode`, batchable API, 가변 문장 개수와 Locust 대기 범위 | API 목적·실행 명령·부하 재현 코드를 연결. 해당 모델의 실행·성능 측정은 하지 않음 |
| [HARI](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN22-Final-4Team-WEB) | 공개 README의 대표 이미지 참조, 기능, 구조도 참조와 개발·배포 설명 | README 상단 화면과 기능→구조→실행 순서 참고. 공개 앱 조작이나 영상 시청을 확인했다고 쓰지 않음 |
| [함종현 공개 이력서](https://refresh.cv/jh.ham) | 공개 경력 설명과 프로젝트/기술 글 연결 | 짧은 문제·결과 뒤 상세 근거 연결. 개인 성과 수치를 재사용하거나 채용 원인으로 해석하지 않음 |

### 변경 전 문제와 선택

| 코드·화면에서 확인한 문제 | 변경 내용 | 유지한 동작 / 비용 |
|---|---|---|
| 상단·하단의 동일 자동 실행 버튼과 단계 버튼이 서로 경쟁함. ‘답변 확인 시작’이 실제로는 전체 여섯 단계를 실행 | 자동 실행은 상단의 보조 버튼 하나로. 답변 아래에는 현재 단계에 해당하는 행동 버튼을 주 행동으로 배치 | 두 진입점은 App 소유 `CaseFlow`의 busy/running 방어 공유. 한 단계씩 읽으면 자동 실행보다 클릭 수가 많음 |
| 비슷한 너비의 원문·답변 영역 뒤에 전체 너비 처리 결과가 떨어져 있음 | 현재 안내를 좁은 참고 영역에, 준비 답변·처리 이유·다음 행동을 넓은 작업 영역에 묶음. 모바일은 원문→답변→처리 순서 | 문서 v2와 답변 인용 v1을 동시에 보존. 금액 비교로 서버 계약을 바꾸지 않음 |
| 완료 요약이 작업 영역 앞에 나타나며 동작을 밀어내고, 동일 결과가 상태 줄에도 반복 | 현재 작업을 먼저, 누적 결과를 아래 배치. 완료 버튼은 결과로 스크롤·초점 이동. 성공 상태의 aria-live 안내는 스크린리더에 유지 | 차단 후 미실행 단계는 ‘기록 확인 전’. 응답 유실 시 성공으로 표시하지 않음 |
| 원문 전문·요청 로그가 기본 화면을 길게 차지함 | 원문과 요청별 응답을 펼침 영역으로 이동. 결과 요약·작업 ID·다음 행동은 접지 않음 | JSON 다운로드·차단/기록 필터 유지. 원본을 읽으려면 한 번 펼쳐야 함 |
| 긴 설명보다 시각적 구별과 행동 연결이 필요 | 짙은 녹색은 주 행동·정상 처리, 갈색은 차단, 회색은 대기. 문구·구분선·상태 표시도 함께 사용. 짧은 화면명 유지 | 색상만으로 상태를 전달하지 않음. 사람의 이해도 개선 여부는 후속 확인 필요 |

변경 코드: [CaseStudy](../demo/src/CaseStudy.tsx), [자동 실행 버튼](../demo/src/CaseRunButton.tsx), [작업 화면 스타일](../demo/src/interface.css). API 계약·세션 소유 구조·멱등 키·백엔드·성능 실험은 변경하지 않았다. 누적되던 `interface.css`의 중복 덮어쓰기 규칙을 정리해 작업·결과·상세 근거의 순서로 재구성했다.

README는 기능 소개→화면→실행 흐름→구조→선택의 비용→조건을 붙인 과거 측정→재현→역할·한계 순서로 재구성했다. 구조도는 공개 상담 `/evidence/.../execute`와 로컬 CPU `/decisions`를 구분한다. 사용성 상태의 오래된 ‘관찰 대기’ 문구도 ‘첫 답변 수신, 수정 후 재확인 대기’로 바로잡았다.

### 검증 범위

로컬 Python API·SQLite에서 프런트 61개, 대표 흐름 13개, 새로고침 복원 9개, 화면·영상·저장 근거 검사 7개를 확인했다. 실제 차단 사유의 대비는 7.32:1로 측정했다. 320/390/768/1440 너비, 키보드 초점 순서, 긴 작업 ID와 펼친 표·도식의 문서 가로 넘침을 검사했다. 모델 부하·trace 선택은 저장된 데이터를 읽으며 API를 호출하지 않는지 확인했다.

초기 검사에서 삭제한 하단 자동 버튼을 찾는 렌더링 테스트와 접힌 로그의 다운로드 버튼을 찾는 브라우저 검사가 실패했다. 최종 화면 구조에 맞춰 상단 자동 버튼과 단계 버튼의 동시 클릭, 로그 펼침 후 다운로드로 변경하고 다시 실행했다. 실제 동작 검증 조건을 없애지 않았다. 복원 검사 종료 시 Playwright route callback의 `CancelledError`가 로그에 남았지만, 9개 검사·프로세스 종료 코드 0·page error 0을 별도로 확인했다.

### 친구에게 다시 부탁할 과제

버튼 이름·위치·예상 결과를 설명하지 않은 채 요청한다.

1. 처음 화면을 보고 어떤 일을 할 수 있는 곳인지 본인의 말로 설명해 주세요.
2. 화면에서 가능한 작업을 진행한 뒤, 무엇이 달라졌는지 화면을 보면서 설명해 주세요.
3. 페이지를 새로고침한 뒤, 남아 있는 정보가 무엇인지 설명해 주세요.

[관찰 양식](usability-record.md)에 익명 참여자·기기/브라우저·완료 여부·도움 제공·막힌 지점·실제 발언을 기록한다. 동일 참여자의 학습 효과를 구분하고, 답변이 도착하기 전에는 재확인 완료·이해도 향상이라고 쓰지 않는다.


### 배포 코드와 제출 자료 연결

- 이번 실행 코드: [`0678cca`](https://github.com/sokldjs554/recheck-ml-serving/commit/0678cca1166d44f2a0ad083afebb002db3b83e7c). [공개 화면](https://sokldjs554.github.io/recheck-ml-serving/?v=0678cca#case).
- [기존 필수 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39216074604): 백엔드 159개 통과·SQLite 전용 1개 제외, 프런트 61개, 두 DB의 정합성 비교·경합 워크로드, 정적 번들·저장 근거 일치 검사 성공. 이번 UI 수정에서 백엔드 동작은 변경하지 않았다.
- [배포 확인](evidence/ui-workflow-2026-10-19/deployment.json): Render `dep-dbasck3m8hqs73bnvt00`, 같은 코드가 2026-10-19 16:29:26 KST에 live 상태로 전환. 기존 무료 플랜 유지.
- [로컬 요약](evidence/ui-workflow-2026-10-19/local.json), [체험](evidence/ui-workflow-2026-10-19/local-case.json), [복원](evidence/ui-workflow-2026-10-19/local-restoration.json), [화면·영상](evidence/ui-workflow-2026-10-19/local-presentation.json).
- 구조도는 [README 시스템 구조](../README.md#시스템-구조와-요청-흐름), 설계 이유·비용·코드 위치는 [현재 설계](decisions.md), 조건·날짜·소스 커밋이 있는 측정값은 [측정 출처](measurement-provenance.md)를 사용한다. 기존 자료를 중복 작성하지 않는다.
- 본인 역할은 주제·방향 결정, 요구 구체화, 기능·범위 조정, 수정 요청과 결과 검토다. AI가 주로 작성한 코드·데모와 구분한다. 자기소개서·제출용 포트폴리오는 이번에 수정하지 않았다.


공개 검증: [배포·브라우저 워크플로](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39216074601) 성공. **Chromium 72개 + macOS WebKit 9개 = 81개 검사 항목**이다. [공개 API 검사와 캡처 출처](evidence/ui-workflow-2026-10-19/public.json), [WebKit 실행 결과](evidence/ui-workflow-2026-10-19/public-webkit.json). 기능·표시 회귀의 검사 개수이며 사람이 화면을 이해했다는 측정값이 아니다.

### 변경 전후 화면과 원본

아래 변경 후 이미지는 로컬 목업이 아니라 `0678cca`가 배포된 Pages·공개 Python API를 사용한 CI의 원본 캡처다. 첫 화면은 요청 전, 차단·기록 화면은 실제 응답 이후다. 모바일 결과는 390px 너비의 결과 영역을 캡처해 글자를 읽을 수 있게 했다. ID는 가상 세션의 작업 ID이며 개인정보는 없다.

| 자료 | 변경 전 | 변경 후 |
|---|---|---|
| 첫 화면 | [이전 공개 화면](evidence/product-ui-2026-10-19/public-entry-1440.png) | [현재 공개 화면](evidence/ui-workflow-2026-10-19/public-entry-1440.png) |
| 이전 답변 차단 | [이전 차단 화면](evidence/product-ui-2026-10-19/public-blocked-1440.png) | [현재 조건·이전 답변·차단 이유와 다음 행동](evidence/ui-workflow-2026-10-19/public-blocked-1440.png) |
| 기록과 재시도 | [이전 모바일](evidence/product-ui-2026-10-19/public-complete-390.png) | [데스크톱](evidence/ui-workflow-2026-10-19/public-record-1440.png) · [모바일 결과](evidence/ui-workflow-2026-10-19/public-record-390.png) |
| 새로고침 복원 | [이전 복원](evidence/product-ui-2026-10-19/public-restored-390.png) | [현재 복원](evidence/ui-workflow-2026-10-19/public-restored-390.png) |
| 기술 근거 | 기존 측정 재사용 | [모델 부하](evidence/ui-workflow-2026-10-19/public-serving-1440.png) · [실패 trace·SQL·복구](evidence/ui-workflow-2026-10-19/public-recovery-1440.png) |

남은 범위: 수정 후 친구의 실제 재확인, 실기기 Safari 검사는 미실시다. 무료 서버 첫 응답 지연과 실제 Health Check Path 설정은 [기존 운영 기록](submission-2026-10-19.md#첫-응답-지연과-실제-배포-설정)에 남아 있으며 이번 UI 변경으로 해결했다고 주장하지 않는다. 시연 영상은 이전 UI임을 표시했고, 과거 성능 측정을 현재 코드의 재측정으로 바꾸지 않았다. 이번 UI·README 작업은 공개 배포와 회귀 검증까지 완료했으며, 다음 사람 관찰 결과는 별도의 후속 수정 근거로 받는다.

## 실행 작업과 근거 탐색 보완

시작 기준은 `b340ba6`(브랜치 `feat/project-introduction`, 시작 시 미커밋 변경 없음)이다. 이 항목은 앞선 영상·UI 보완 이후의 작업이다. 기존 구현과 과거 실험을 보존하고 다음 공백을 연결했다. 외부 사례의 확인 범위는 [14개 저장소·공식 화면·접근 제한 기록](research/2026-10-19/README.md)에 있다. 합격자 성과나 다른 프로젝트의 성능을 RECHECK 근거로 사용하지 않는다.

### 문제와 변경

| 확인한 문제 | 변경과 확인 경로 |
|---|---|
| 첫 화면에서 한도 금액이 과하게 강조되고, 실제 작업 결과는 아래에 묻힘 | 금액을 원문 조건으로 낮추고 이전 답변 차단·새 작업·같은 요청 상태를 앞에 배치. 원문과 실행할 답변을 나란히 비교 |
| 직접 문서를 바꾸는 화면이 상세 메뉴에 숨고, 읽기 전용 검증까지만 연결됨 | 실행 기록의 `대표 흐름 / 직접 구성`으로 연결. 기존 4개 문서·질문·답변/체크리스트·모델 교체 기능에서 실제 `/execute`와 같은 키 재시도까지 연결 |
| 직접 구성은 메뉴를 나가면 세션·입력·결과를 잃음 | 방문한 화면을 유지하고 표시만 전환. 진행 중 요청이 같은 세션에서 한 번 완료되고 화면 복귀가 재요청하지 않음 |
| 응답 유실 뒤 화면에서 저장 내역을 확인하기 어려움 | 명시적 GET `서버 기록 조회` 추가. 마지막 조회 시각·개수·작업 ID 대조 표시. 조회 후 새 실행이 생기면 재조회 필요 안내 |
| 부하 구간·실패/복구 선택이 메뉴 이동 뒤 초기화됨 | 부하·복구 화면의 선택과 펼침 상태 유지. 선택 구간의 결과 해석을 가까이에 배치하고 긴 세션 경합 비용은 펼침 영역으로 이동 |
| 이전 UI 영상과 현재 화면이 불일치 | 이전 MP4/WebM/poster를 현재 트리에서 제거. 현재 UI의 57.64초 실제 로컬 API 시연으로 교체 |

변경 전: [이전 공개 화면](evidence/ui-workflow-2026-10-19/public-entry-1440.png). 변경 후: [원문 변경과 차단](evidence/workspace-upgrade-2026-10-19/step-3.jpg) · [작업 완료](evidence/workspace-upgrade-2026-10-19/step-6.jpg) · [결제 취소 문서의 직접 기록](evidence/workspace-upgrade-2026-10-19/custom.jpg) · [모바일 직접 구성](evidence/workspace-upgrade-2026-10-19/custom-mobile.jpg).

### 설계 선택과 비용

- `App.tsx`는 방문한 직접 구성·부하·복구 화면을 unmount하지 않고 `hidden`으로 전환한다. 입력·조회 결과·선택 상태를 유지하는 대신 최대 세 화면의 DOM·메모리를 유지한다. 숨긴 화면에 자동 API 조회는 없다. 직접 구성의 만료 표시용 타이머는 유지된다.
- `TaskExecution.tsx`는 준비한 답변마다 요청 키 하나를 보존한다. 부모 문서 변경과 같은 ref 잠금을 공유해 기록 도중 새 답변·원문 수정·세션 재시작을 막는다. 쓰기 도중 조건 변경을 허용하는 UI보다 동시성이 낮지만 한 작업의 결과를 다른 답변에 잘못 붙이는 상황을 피한다.
- HTTP 성공 형식을 검증한 뒤에만 작업 기록으로 표시한다. 응답 유실은 저장 실패로 단정하지 않는다. 같은 답변의 같은 키 재시도와 별도의 서버 조회로 확인한다. 새 답변 준비는 새 작업 키를 만든다.
- `ServerRecords.tsx`의 조회는 사용자 요청 시만 실행한다. 원본 응답·브라우저 복원본과 현재 서버 조회를 구분하지만 자동 동기화는 하지 않는다. 조회 자체도 기존 세션 저장소의 잠금 경로를 사용한다. 화면 이동 때 대표 흐름의 조회 목록은 다시 조회해야 하며, 원래 실행 기록·작업 ID·로그는 유지된다.
- 직접 구성의 요청 키는 탭 내 화면 이동까지 유지하며 **새로고침 복원은 지원하지 않는다**. 대표 흐름의 기존 새로고침 복원은 그대로 유지한다. 서버 트랜잭션·멱등성 계약, CPU 슬롯·프로세스 설계, 성능 실험은 변경하지 않았다.

### 직접 재현할 사례

로컬 Python API와 Vite를 실행한 뒤 아래 명령을 사용한다. 테스트는 실제 로컬 API의 저장을 완료시킨 후 브라우저 응답만 끊어 미확정 상태를 만든다. 서버에 장애나 부하를 주입하지 않는다.

```sh
python scripts/check_evidence_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8025 --output work/custom-check
python scripts/check_case_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8025 --output work/case-check
python scripts/check_restoration_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8025 --output work/restore-check
python scripts/check_serving_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8025 --expected-storage sqlite --output work/serving-check
```

Python Playwright·Chromium 필요. 시스템 브라우저를 사용할 때 `--browser-executable /usr/bin/chromium`을 추가한다. 공개 배포의 기능 회귀는 같은 스크립트로 수행하되 부하 실험은 실행하지 않는다.

저장 후 응답 유실 → 완료로 표시하지 않음 → 서버 조회에서 1건 → 메뉴 왕복 → 같은 키 두 번 연속 클릭 → POST 1회 → 같은 작업 ID 반환 → 서버 1건 유지의 순서로 검증했다. 원문 변경 뒤 `/execute` 거절과 서버 0건도 별도로 확인했다. [직접 구성 검사](evidence/workspace-upgrade-2026-10-19/custom-acceptance.json). 코드 위치: [기록 UI](../demo/src/TaskExecution.tsx), [조회 UI](../demo/src/ServerRecords.tsx), [API 응답 검증](../demo/src/caseApi.ts), [기존 원자적 기록](../backend/recheck/evidence.py).

### 이번 검증과 자료

- 프런트 62개 통과. 새 검사는 서버 조회 응답의 형식·세션 만료를 다룬다.
- 로컬 Chromium: 대표 흐름 13개, 직접 구성 14개, 복원 9개, 화면·영상·자료 탐색 7개, 부하·복구 탐색 7개 검사 그룹 통과. [대표 흐름](evidence/workspace-upgrade-2026-10-19/case-browser.json) · [복원](evidence/workspace-upgrade-2026-10-19/restoration-results.json) · [화면·영상](evidence/workspace-upgrade-2026-10-19/presentation-results.json) · [부하·복구 탐색](evidence/workspace-upgrade-2026-10-19/serving-results.json). 기존 상태와 새 동작의 회귀 검사이며 사용자 이해도 측정이 아니다.
- 320·390·768·1440px에서 주요 버튼·로그·영상·표의 문서 가로 넘침을 검사했다. 직접 구성은 390·768·1440px에서 확인했다. 키보드 구간 선택과 포커스 이동은 화면·자료 검사에 포함된다.
- 복원 검사의 첫 실행은 브라우저 경로 미지정으로 시작하지 못했다. 설치된 Chromium을 명시한 실행은 9개 검사·page error 0·종료 코드 0이었다. 종료 시 기존 route callback의 `CancelledError`가 별도로 출력됐다.
- [현재 영상](https://sokldjs554.github.io/recheck-ml-serving/media/recheck-workspace-20261019.mp4)은 로컬 API·SQLite 실제 응답으로 촬영했다. [소스/미디어 해시와 HTTP 목록](evidence/workspace-upgrade-2026-10-19/capture.json), [대표 흐름 원본](evidence/workspace-upgrade-2026-10-19/case.json), [직접 구성 기록](evidence/workspace-upgrade-2026-10-19/custom-action.json).
- README의 구조도·기술 선택·수치 조건을 유지하고 실제 사용 경로를 먼저 설명했다. 과거 120 req/s 투입 목표·약 67.6 req/s 유효 처리량을 새 측정으로 바꾸지 않았다.

### 친구에게 다시 부탁할 과제

처음 화면을 보고 어떤 일을 할 수 있는지 자유롭게 설명해 주세요. 한 번 사용한 뒤 어떤 결과가 남았는지, 원하는 작업이 처리됐다고 판단한 근거가 무엇인지 이야기해 주세요. 다른 화면을 살펴보고 돌아오거나 새로고침한 뒤, 이전 내용을 어디까지 확인할 수 있는지 찾아 주세요.

버튼 위치·정답은 미리 알려주지 않는다. 진행 경로·도움 여부·막힌 지점·실제 발언을 [기존 양식](usability-record.md)에 기록한다. 수정 후 사람의 재확인은 아직 없으며 기능 검사 통과를 이해도 개선으로 해석하지 않는다. 사용자의 요구·수정 요청·결과 검토와 AI의 코드·데모 제작을 구분한다. 자소서·포트폴리오는 수정하지 않았다.
