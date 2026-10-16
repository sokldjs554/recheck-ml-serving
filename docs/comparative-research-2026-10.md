# 유사 ML 백엔드·데모 비교와 반영

조사일: 2026-10-17 KST. 작업 시작 시 원격 `4bddddad771b7f70bd60f6870673ce3217d0f1a0`을 반영했다.
`1e16dc3`의 제목·시연·상태 설명 개편과 `4bdddda`의 README 변경을 유지한다.

## 조사 질문과 범위

[토스뱅크 ML Backend Engineer 공고](https://toss.im/career/job-detail?job_id=6600650003)를 다시 읽었다.
모델 종류보다 Python 서버의 안정성, 무거운 연산의 응답 속도와 처리량, 분산 추적, 복잡도와 구현 비용의 선택이 중요하다.
이번에는 프레임워크 3개, 관측·평가 프로젝트 4개, 개인 백엔드 프로젝트 2개를 비교했다.
채용 합격 프로젝트라고 확인한 목록이 아니며, 기존 [합격 후기 조사](research.md)와 구분한다.

**확인 수준:** 소스 = 명시한 파일을 읽음 / 공개 화면 내용 = JavaScript 렌더링 결과를 읽기 전용으로 추출 / 화면 이미지 = 공식 캡처를 실제로 열어 확인 / 조작 = 브라우저에서 버튼·입력·결과를 직접 실행.
이번 외부 조사에서 **새로운 원격 클릭·입력 조작 및 영상 연속 재생은 수행하지 못했다.**
로컬 실행 환경은 외부 데모 도메인을 허용하지 않고, 유료 원격 자동화의 추가 결제는 사용자가 거절한 상태다.
아래 공개 화면 내용과 공식 캡처를 실제 기능 실행 성공으로 바꾸어 표현하지 않는다.

## 프로젝트 비교

| 프로젝트 / GitHub | 기능·설계에서 확인한 것 | 데모·화면 확인 | RECHECK에 대한 판단 |
|---|---|---|---|
| [BentoML](https://github.com/bentoml/BentoML) | Python 모델 API, adaptive batching, 동시 실행 제한. `src/bentoml/_internal/marshal/dispatcher.py`의 대기열·지연 예산·semaphore·batch dispatch 확인 | [공식 배포 화면](https://github.com/bentoml/BentoML/blob/main/docs/source/_static/img/get-started/cloud-deployment/first-bento-on-bentocloud.png)을 열어 확인. endpoint·입력·결과·반환 시간을 나란히 배치. BentoCloud 실제 추론 미실행 | 입력과 결과를 연결하는 방식은 참고. RECHECK의 현재 작은 CPU 작업에 batching이 유리하다는 측정이 없어 도입하지 않음 |
| [Ray Serve](https://github.com/ray-project/ray) | `python/ray/serve/_private/router.py`의 queue 상한, `BackPressureError`, 취소 시 queue counter 정리. [공식 부하 거절 예제](https://docs.ray.io/en/latest/serve/production-guide/best-practices.html) | 문서의 2개 실행·2개 대기·추가 거절 예제와 로그 확인. Ray cluster/dashboard 직접 실행하지 않음 | 목표 요청률·전송률·유효 응답·거절을 구별. 기존 RECHECK 수용 제한을 재구현하지 않고 측정 구간 선택으로 연결 |
| [MLServer](https://github.com/SeldonIO/MLServer) | V2 inference API, multi-model·parallel inference·batching. `mlserver/parallel/pool.py`의 multiprocess worker, 종료 callback, registry와 재시작 확인 | README의 [공식 소개 영상](https://www.youtube.com/watch?v=aZHe3z-8C_w) 주소 확인. 영상 재생·서버 실행 미검증 | 프로세스 분리 자체보다 실패 후 무슨 결과를 남기는지 설명해야 함. 기존 실행 풀을 교체하지 않음 |
| [Langfuse](https://github.com/langfuse/langfuse) | trace·prompt·evaluation·playground의 연결. README와 [공식 데모 안내](https://langfuse.com/docs/demo) 확인 | [공개 trace](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/db22d0a442216b485abd83cc9df6d9ee)의 렌더링 내용에서 Tree/Timeline/Graph, main·geography-teacher·poet 단계와 개별 지연, Preview/Attributes/Scores 확인. 직접 탭 조작은 하지 않음 | 실행 결과에서 개별 단계의 원본으로 이동하는 방식을 적용. LLM token/cost 기능은 RECHECK와 맞지 않아 추가하지 않음 |
| [Phoenix](https://github.com/Arize-ai/phoenix) | OpenTelemetry 기반 trace, 평가·실험·playground. README와 [공식 프로젝트](https://phoenix-demo.arize.com/) 확인 | 공개 프로젝트 목록 → [demo_agents](https://phoenix-demo.arize.com/projects/UHJvamVjdDoy?timeRangeKey=7d)의 렌더링 내용을 읽음. 30개 trace, latency·input/output·status 열 확인. trace 상세 URL도 열었으나 추출 결과는 목록과 같아 상세 drawer 확인으로 세지 않음 | 합계 수치 뒤에 요청 한 건을 확인할 수 있어야 함. RECHECK는 기존 실패/복구 두 trace로 범위를 제한 |
| [Jaeger / HotROD](https://github.com/jaegertracing/jaeger/tree/main/examples/hotrod) | 분산 서비스에서 trace로 요청의 경로를 찾는 예제. README의 실행 구조 확인 | [HotROD](https://demo.jaegertracing.io/hotrod)의 고객 4개와 차량 요청 안내, [Jaeger](https://demo.jaegertracing.io/jaeger/)의 service·duration·attribute 검색 화면 내용 확인. 직접 차량 요청 미실행. service만 붙인 검색 URL은 `Failed to fetch trace summaries: 400` 반환 | 오류와 접근 실패도 조사 기록에 남김. 추적 화면은 trace ID·부모 span·서비스·예외를 연결하고 DB 기록은 별도 증거로 표시 |
| [promptfoo](https://github.com/promptfoo/promptfoo) | 평가 결과 matrix, 실패/차이 필터, 원본 상세·내보내기. [Web UI 문서](https://www.promptfoo.dev/docs/usage/web-ui/) 확인 | [공식 결과 화면](https://github.com/promptfoo/promptfoo/blob/main/site/static/img/claude-vs-gpt-example@2x.png)을 열어 확인. 조건·pass 비율·분모·지연·결과 행이 같은 화면에 있음. 평가 실행·필터 직접 조작 미실행 | 현재 실행 로그에서 차단과 기록/재시도를 필터링하고 전체 원본은 유지. 외부 모델 점수표를 모방하지 않음 |
| [ml-inference-service](https://github.com/kevin-sparkflow/ml-inference-service) | README와 `src/inference_service/gateway/app.py` 확인. FastAPI gateway/worker 분리, Redis WATCH/MULTI/EXEC 수용 제한, 202 작업 ID, 큐 포화 503, 제한된 파일 읽기 | 공개 UI 대신 로컬 API·Locust 실행법 제공. 외부 공개 UI 주소를 확인하지 못했고 로컬 스택도 실행하지 않음 | 작업 ID와 결과의 관계를 분명히 보여주는 방식 참고. 별도 Redis 큐·이미지 모델을 넣는 것은 다른 제품 문제이므로 제외 |
| [fastapi-ml-platform](https://github.com/DiogoRibeiro7/fastapi-ml-platform) | README와 `app/main.py` 확인. fraud scoring, batch jobs, model registry, drift, correlation ID, 선택적 OTel, 앱 수명에 따른 scheduler 정리 | README의 API·Swagger·로컬 실행법 확인. 공개 배포 UI 주소를 확인하지 못했으며 저자의 운영·성능 주장은 독립 재현하지 않음 | HTTP 성공과 업무 결과를 구분하고 요청 단위 진단을 보강. 인증·drift·모델 registry 기능 수 채우기는 하지 않음 |

추가 후보 [Evidently](https://github.com/evidentlyai/evidently)의 `https://demo.evidentlyai.com/`는 두 번 시간 초과되어 UI 검토 완료 목록에서 제외했다. 저장소 전체 검토나 모든 기능 조사를 끝냈다는 뜻이 아니다.

Langfuse의 [공식 timeline 캡처](https://github.com/langfuse/langfuse-docs/blob/main/public/images/blog/2024-10-observability-multi-step-llm-systems/trace-timeline-multi-step-llm-blogpost.png)도 실제로 열어 계층·상대 시간축·겹치는 span 배치를 확인했다. 공식 이미지 확인은 BentoML·promptfoo·Langfuse 세 개이며 원격 상호작용과는 구분한다. [공개 페이지 접근 기록](evidence/comparative-demo-access.json).

## 데모를 비교한 기준

| 확인 질문 | 외부에서 확인한 패턴 | RECHECK의 기존 상태 | 반영 방향 |
|---|---|---|---|
| 첫 행동과 결과가 연결되는가 | BentoCloud의 API 입력·반환 결과, Langfuse의 demo → trace 경로 | 상단 실행·6단계·현재 원문/답변/기록 구분은 이미 있음 | 상단과 실행 수명은 유지 |
| 실패를 전체 성공률에서 숨기지 않는가 | promptfoo의 실패 필터와 결과 분모, Phoenix의 status와 개별 지연 | 차단·기록·재시도가 로그 JSON 안에 섞임 | 차단 사유와 작업 ID를 로그에서 바로 읽고 결과별 필터 제공 |
| 합계 뒤의 개별 조건을 볼 수 있는가 | 평가 matrix의 조건·결과 행, Ray의 실행·대기·거절 구분 | 6개 부하 구간 막대는 있으나 자세한 조건은 긴 표에 있음 | 막대에서 30초 구간을 선택해 전송·완료·유효·보류·거절·지연 확인 |
| 어느 서비스에서 실패했는가 | Langfuse의 단계별 trace, Jaeger의 service/attribute 검색 | 실제 OTLP 원본은 저장되어 있지만 화면은 4단계 설명에 머묾 | 실패/오류 해제 요청을 선택하고 실제 span 시간·부모·예외·로그·SQL 확인 |
| 실제 지연의 원인을 설명할 수 있는가 | 관측 도구들은 요청 전체와 하위 구간을 나눔 | 정기 점검은 6개 HTTP 요청 전체 시간만 기록 | 단계별 클라이언트 왕복 시간을 추가. 서버 내부 시간이나 근본 원인으로 단정하지 않음 |

## 선택과 비용

이번 개선은 기존 세 경로와 수명·API·DB 구조를 유지하는 제한된 변경이다. 새로운 모델·프레임워크·유료 인프라를 추가하지 않는다.

- **화면 선택은 읽기 전용.** 로그 필터·부하 구간·trace 선택 때문에 추가 API 요청이 발생하지 않는다. 실행 결과와 작업 ID는 기존 CaseFlow가 소유한다.
- **관측 원본 재사용.** 180초 CPU 실험과 저장된 두 OTLP 요청을 그대로 사용한다. 나노초 epoch는 Python 정수로 차이를 계산한 뒤 화면용 ms로 변환해 JavaScript 정수 정밀도 손실을 피한다.
- **시간 경계 명시.** 겹치는 span은 합산하지 않는다. `fence.commit`은 네이티브 SQL span이 아니며 ORM commit 전 종료된다. DB 반영은 독립 SQL 조회로 확인한다.
- **점검 비용.** 기존 요청 6개에 monotonic clock 측정과 작은 JSON 항목을 추가한다. 새 요청·재시도·수집 서버는 추가하지 않는다. 네트워크·연결·서버 처리가 합쳐진 클라이언트 관측값이다.
- **별도 경로 유지.** 상담 `/evidence/.../execute`, 부하 `/decisions` CPU, 실패 trace `/decisions` lightweight는 서로 다른 조건이다. 각 화면에서 경계를 유지한다.

## 과거 정기 점검 실패 보존

[2026-10-13 KST 정기 점검](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38328704268)은 세 번 모두 기능 검증은 성공했지만 전체 과정이 **54.037초 / 2.135초 / 1.630초**였다.
첫 표본이 5초 기준을 넘겨 점검은 실패했다. 이는 [c93 배포 검증 성공](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38228371606)과 별도다.
과거 기록에는 단계별 시간이 없으므로 서버 시작 지연이라고 단정할 수 없다. 새 계측으로 과거 원인이 밝혀졌다고 주장하지 않는다.
기준 완화·실패 삭제·성공한 재시도만 집계하는 변경은 하지 않는다.

## 검증 해석

외부 소스·화면의 장점을 참고했지만 RECHECK가 해당 제품과 동등한 운영 규모나 성능을 갖췄다는 의미는 아니다.
외부 프로젝트의 기능을 모두 실행한 것도 아니다. 새로운 사용자 이해도 조사·실기기 Safari 검증·은행 운영 실적은 없다.
지원자 역할과 AI 작성 범위는 [README](../README.md#본인-역할과-ai-활용)의 확인된 사실을 유지한다.
구현·검증 결과는 [이번 반영 기록](inspection-update.md)에 별도로 남긴다.
