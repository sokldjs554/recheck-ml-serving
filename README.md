# RECHECK

**모델 연산의 과부하와 결과 기록의 불일치를 다루는 Python 백엔드입니다.** 실행 시점의 근거 재검사, 동일 요청의 중복 기록 방지, CPU 모델의 수용 제한·시간 예산, 실패 추적을 구현했습니다.

[공개 화면 열기](https://sokldjs554.github.io/recheck-ml-serving/) · [현재 화면의 실제 시연 영상](https://sokldjs554.github.io/recheck-ml-serving/media/recheck-workbench-20261020.mp4)

[![기록하려던 답변과 서버에 실제 저장된 작업 기록](docs/evidence/outcome-workbench-2026-10-20/replayed.jpg)](https://sokldjs554.github.io/recheck-ml-serving/)

**준비한 답변과 실제 저장된 작업 기록을 같은 작업 화면에서 대조합니다.** 인용한 문서가 바뀐 답변은 기록하지 않고, 최신 답변을 기록한 뒤 같은 요청을 다시 보내도 기존 기록을 반환합니다. 문서 변경과 작업 기록을 같은 세션 잠금·SQL 트랜잭션 경계에서 처리하고, 같은 요청 키의 재시도에는 기존 작업을 반환합니다.

상단 캡처와 2026-10-20 KST 영상은 **로컬 Python API·SQLite**에서 실제 실행한 화면입니다. 기록이 거절된 답변, GET으로 확인한 답변 한 건, 같은 요청 재시도 뒤 유지되는 기록을 보여줍니다. 현재 방문자의 실행 결과가 아닌 저장된 시연입니다. [화면·API 대조·검증 기록](docs/usability-feedback-2026-10-19.md#프로젝트-목적과-작업-결과-정리)

## 확인할 수 있는 동작

답변을 준비한 후 원문이 바뀌거나, 저장은 됐는데 HTTP 응답을 받지 못할 수 있습니다. RECHECK는 **오래된 답변의 기록 차단**과 **응답 유실 뒤 중복 기록 없는 재시도**를 다룹니다. 공개 경로는 가상 안내 문서의 TF-IDF 검색·근거 발췌이며 실제 송금·메시지 발송이나 LLM 생성은 하지 않습니다.

| 사용 경로 | 할 수 있는 일 | 확인할 결과 |
|---|---|---|
| **대표 흐름** | 답변 불러오기 또는 단계별 진행 | 준비한 답변 확인 → 기록 거절 뒤 결과 확인 → 갱신한 답변 저장·확인 → 같은 요청 재시도와 동일 기록 확인 |
| **직접 구성** | 이체 한도·결제 취소·카드 재발급·대출 서류 선택, 질문·원문 수정/삭제, 답변/체크리스트 준비, 모델·인덱스 후보 평가 | 직접 만든 답변의 실제 기록 요청, 실패 이유, 동일 키 재시도, 서버 저장 기록 조회 |
| **모델 부하** | 과거 실험의 정상·과부하·복귀 구간 선택 | 투입 목표와 유효 응답률, 보류·거절·시간 초과, 저장된 504의 SQL 행 |
| **장애 복구** | 실패·복구 요청과 개별 span 선택 | API→모델의 실패 위치, 복구 후 추론·SQL 기록, 별도 공개 운영 기록 조회 |

대표 흐름의 이체 한도는 변경 전·후를 비교하기 위한 **한 가지 예시 문서**입니다. 직접 구성에서는 다른 문서와 질문으로 같은 API를 실행할 수 있습니다. 읽기 전용 사용 가능 검사는 작업 기록과 구분하며, 실제 기록 요청에서 서버가 다시 검사합니다.

화면의 **기록할 답변**은 준비된 검색 결과, **근거 대조**는 그 답변의 인용 원문과 현재 원문, **저장된 작업**은 서버 GET으로 확인한 실제 저장 내역입니다. “준비”는 작업 저장이 아닙니다. 문서 변경은 예시 조건이며, 돈을 보내는 기능은 없습니다.

**저장된 작업**은 세션 시작과 기록 요청·재시도 뒤에 서버 저장 내역을 자동으로 GET 조회합니다. 목록·건수는 이 응답에서만 가져오고, 기록 요청 응답과 이후 조회 결과를 구분합니다. 조회 전에는 0건이라고 표시하지 않으며, 조회 실패 시 마지막 확인 기록임을 표시합니다. 같은 요청 키·반환된 작업 ID·재시도 응답을 대조한 경우에만 추가된 기록이 없다고 표시합니다. 수동 조회는 보조 기능입니다.

응답 유실은 저장 실패가 아닙니다. 저장 여부가 불분명하면 같은 요청 키를 유지하고 실제 조회·재시도로 확인합니다. 새 답변 준비는 미확정 요청이 해소될 때까지 막습니다. 대표 흐름은 차단 결과와 새 기록을 각각 확인한 뒤 다음 행동으로 넘어갑니다. 원본 키·HTTP 실패·trace ID는 상세 근거에서 확인할 수 있습니다.

대표 흐름과 직접 구성은 서로 다른 세션입니다. 화면 이동 중에는 각각의 진행·입력·결과를 유지하고, 부하 구간·trace 선택도 유지합니다. **새로고침 복원은 대표 흐름만 지원**합니다. 같은 탭의 과거 응답을 복원할 뿐 자동 API 재검증을 하지 않습니다. 작업 기록의 GET 목록은 새로 조회해야 하며 조회 전 상태로 구분합니다. 직접 구성은 새로고침 시 초기화되며, 기록 요청 중에는 조건 변경과 중복 실행을 막습니다.

<details>
<summary>직접 구성·부하·복구 화면</summary>

![직접 구성의 준비한 답변과 서버 저장 기록](docs/evidence/outcome-workbench-2026-10-20/custom.jpg)

![과거 부하 구간과 유효 응답 상세](docs/evidence/workspace-upgrade-2026-10-19/serving.jpg)

![저장된 실패 trace의 구간별 확인](docs/evidence/workspace-upgrade-2026-10-19/recovery.jpg)

</details>

답변 기록 화면은 실제 API 결과입니다. 모델 부하·장애 복구는 저장된 로컬 실험이며, 추가 조건 실험의 브라우저 시뮬레이션은 별도로 표시합니다. 공개 체험의 `/evidence/…/execute`와 CPU 모델 실험의 `/decisions`는 다른 요청 경로입니다.

## 시스템 구조와 요청 흐름

**공개 답변 기록 체험과 CPU 모델 부하 실험은 서로 다른 경로입니다.** CPU 부하 수치를 답변 기록 체험의 응답 속도로 사용하지 않습니다.

```mermaid
flowchart TB
    subgraph public["공개 환경 · 무료 운영"]
        UI["GitHub Pages · React 데모"]
        API["Render · Python FastAPI"]
        Search["TF-IDF 근거 검색 · 모델/인덱스 평가"]
        Guard["/evidence/.../execute · 세션 잠금 · 검증 · 멱등성"]
        PG["Neon PostgreSQL · 세션 상태 · 내부 작업 기록"]
        UI -->|답변 기록 체험 HTTP| API
        API --> Search
        API --> Guard
        UI -->|GET 저장 기록 조회| API
        Search --> PG
        Guard -->|같은 SQL 트랜잭션| PG
    end
    subgraph local["격리된 로컬 실험 · 공개 서버에 부하를 보내지 않음"]
        Load["부하 생성기"]
        LocalAPI["FastAPI · /decisions · 시간 예산"]
        Model["HTTP 모델 서비스 · 수용 제한 · CPU 프로세스 풀"]
        LocalPG["로컬 PostgreSQL · 판단 기록"]
        Observe["OpenTelemetry / Jaeger · Prometheus / 알림"]
        Load --> LocalAPI
        LocalAPI --> Model
        LocalAPI -->|최종 검증 · 저장| LocalPG
        LocalAPI -.-> Observe
        Model -.-> Observe
        K8s["별도 단일 노드 kind · DB Pod 교체 복구 실험"]
    end
    Saved["저장된 측정 결과 · trace · SQL 대조"]
    local -.-> Saved
    Saved -.->|모델 부하 / 장애 복구 화면| UI
```

답변 기록 경로의 핵심은 [근거 검증·작업 기록](backend/recheck/evidence.py), CPU 경로의 핵심은 [API](backend/recheck/api.py)·[모델 서비스](backend/recheck/worker.py)·[최종 검증과 저장](backend/recheck/store.py)입니다. 관측 도구와 kind는 로컬 검증 구성입니다. 실패 추적에서는 OpenTelemetry SDK의 OTLP 출력을 수집했고, SQL 영속화는 별도 조회로 대조했습니다.

## 기술 선택과 비용

| 선택 | 현재 구현에서 얻는 효과 | 감수한 비용 |
|---|---|---|
| 세션 잠금 안에서 검사·기록 | 검사 직후 변경되는 틈을 막고 같은 키의 기존 작업 반환 | 같은 세션 요청의 직렬화, 잠금 대기·시간 초과 |
| 세션 전체 JSON 저장 | 작은 사례의 문서·답변·작업을 함께 재현 | 상태 복사·직렬화·쓰기량. 조회도 잠금 경로 사용 |
| API와 CPU 모델 프로세스 분리 | 무거운 계산과 요청 처리의 실행 경계 분리 | 프로세스 시작·모델 복제 메모리·HTTP/IPC 비용 |
| 실행·대기 슬롯과 시간 예산 제한 | 무한 대기열 억제. 응답이 끝나도 CPU 종료 전까지 슬롯 유지 | 수용 한도를 넘는 요청의 거절·보류. 실행 중 CPU 즉시 중단 불가 |
| 저장 결과와 HTTP 응답 구분 | 응답 유실·시간 초과 뒤 같은 키로 실제 기록 확인 | 키 보존, 불명 상태·세션 만료 처리 필요 |

설명은 현재 코드의 선택을 분석한 것이며 지원자의 과거 의사결정을 추정하지 않습니다. [코드 위치·대안·제약](docs/decisions.md) · [공개 상담의 잠금·저장·취소 관측](docs/evidence-execution-observation.md)

## 측정 결과와 조건

아래는 **과거 실험**입니다. 이번 UI 변경에서 처리량을 재측정하지 않았습니다. 날짜는 KST이며, 소스 대조 커밋과 자료 보관 커밋은 [측정 출처](docs/measurement-provenance.md)에서 구분합니다.

| 질문 | 조건·측정 시점·소스 대조 | 관측 결과와 원본 |
|---|---|---|
| 검사와 기록을 묶으면 무엇이 달라지는가? | 2026-10-12 00:34, `976ebb7`. SQLite·PostgreSQL 각각 고정 사건 순서 | 오래된 근거 6회 중 별도 검사·기록은 5회 허용, 동일 트랜잭션은 0회. 준비된 사례 결과이며 운영 사고율 아님. [세 방식 비교](docs/safety-case-study.md) |
| 세션 경합의 비용은? | 2026-10-12 15:08, `0b99e35`. PostgreSQL 직접 호출, 동시 8개·큰 상태·문서 변경 없음 | 같은 세션 91.89건/s·p95 86.87ms, 서로 다른 세션 111.43건/s·p95 78.64ms. HTTP 처리량 아님. [54조건 × 3회 비용 측정](docs/consistency-costs.md) |
| 과부하에서 얼마를 유효하게 처리했는가? | 2026-10-12 14:59, `0b99e35`. 공유 호스트 CPU quota 4코어, CPU worker 2개→PostgreSQL. 5초 워밍업 후 180초, 30초씩 정상10→과부하120→정상10 req/s를 2회 | 과부하 **목표 투입 120 req/s**, 예정 시점부터 **300ms 이내 유효 응답 약 67.6 req/s**. 과부하 7,200건=유효4,072+보류2,983+429 144+504 1. [전체 요청·자원·SQL](docs/fullpath-sustained.md) |
| 응답 실패는 저장 실패인가? | 위 부하 실험의 504 1건, 워밍업 포함 SQL 대조 | 504도 이미 저장되어 SQL 8,306건, HTTP 200 기록은 8,305건. 중복·누락·불일치·pending 0. 해당 부하 실험에서 재시도는 실행하지 않음. [원본 요청 키와 SQL](docs/fullpath-sustained.md) |
| 모델 장애 위치와 복구를 확인할 수 있는가? | 2026-10-12 14:55, `0b99e35`. 로컬 오류 주입 후 해제 | 실패 API→모델 trace·예외 로그·SQL 대조 후 정상 추론·저장 확인. `fence.commit`은 실제 SQL commit 시간이 아님. [실패부터 복구까지](docs/failure-walkthrough.md) |

180초 실험의 정상·복귀 네 구간은 각 300/300건이 유효했습니다. 복귀 후 5초 창 두 개를 확인한 **10초 시점**은 회복 확인 시점이지 정확한 회복 소요 시간이 아닙니다. API·모델 최대 합산 RSS 652.6 MiB, 유효 응답당 CPU 41.0ms는 DB와 부하 생성기를 제외한 비용입니다. 장기 처리 용량이나 SLA를 의미하지 않습니다.

[프로세스 격리의 별도 비교](docs/compute-experiments.md) · [단일 노드 kind 복구](docs/kubernetes.md) · [관측 도구 구성](docs/operations.md). kind의 2.502초는 **2026-10-09 01:28~01:30 KST 과거 실험의 첫 실패~첫 성공 관측 간격**이며 상용 고가용성 실적이 아닙니다.

## 실행·재현

```sh
git clone https://github.com/sokldjs554/recheck-ml-serving.git
cd recheck-ml-serving
docker compose up --build
# http://localhost:8000
```

<details>
<summary>Docker 없이 실행 · 프런트 개발 · 테스트</summary>

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python scripts/serve_demo.py
# http://localhost:8000
```

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix demo ci
npm --prefix demo test
npm --prefix demo run dev
```

프런트 수정 후 Node 24에서 `python scripts/build_demo.py`로 서버용 정적 번들을 갱신합니다. CI는 PostgreSQL·프런트 테스트, 번들 일치, 공개 주소의 브라우저 동작을 확인합니다. [검증 명령과 기록](docs/verification.md)

</details>

부하 실험은 위 상세 문서의 명령으로 격리된 로컬 환경에서만 재현합니다. **공개 무료 서버에는 부하를 보내지 않습니다.**

| 확인할 자료 | 바로가기 |
|---|---|
| 이번 UI 변경 전후·배포 버전·브라우저 검사·재확인 과제 | [화면과 검증 근거](docs/usability-feedback-2026-10-19.md#프로젝트-목적과-작업-결과-정리) |
| 서버 설계·서빙·추적 요구와 구현 위치 | [공고 대응](docs/job-coverage.md) |
| 동일 키·동시 요청·잠금 실패 | [정합성 계약](docs/action-contract.md) · [동시성 비교](docs/action-comparison-audit.md) |
| 검증 실행 방법과 기존 운영 기록 | [검증 명령](docs/verification.md) · [공개 운영 점검](docs/public-runtime.md) |

## 본인 역할과 AI 활용

AI와 주제 후보를 비교한 뒤 최종 주제와 방향을 결정했습니다. 요구사항을 구체화하고 기능 추가·범위 조정·수정 요청을 했으며, 관련 프로젝트와 예시를 전달하고 변경 결과의 반영 여부를 검토했습니다.

**코드 작성과 데모 제작은 AI가 주로 담당했습니다.** 프로젝트에 구현된 기술과 기록된 실험은 위에서 설명한 역할과 구분하며, 확인되지 않은 직접 설계·코딩·실험 경험을 개인 기여에 포함하지 않습니다.

## 현재 범위

- 무료 API는 첫 응답이 지연될 수 있습니다. 실제 Render HTTP health 경로는 미적용 상태이며 [적용 위치와 조회 근거](docs/usability-feedback-2026-10-19.md#프로젝트-목적과-작업-결과-정리)를 남겼습니다. 배포 검증과 이후 정기 점검은 구분하며 [실패 표본도 보존](docs/public-runtime.md)합니다.
- 공개 체험은 가상 데이터·내부 작업 기록이며 세션은 생성 후 1시간입니다. 대표 흐름의 새로고침 복원은 같은 탭의 브라우저 저장 범위입니다. 직접 구성의 기록 요청 키는 화면 이동에는 유지되지만 새로고침에는 유지되지 않습니다.
- 자동화 검사는 기능 회귀 근거입니다. **비전공자 친구 1명의 답변을 반영했으며 수정 후 사람의 재확인은 대기 중**입니다. 성공률·이해도 향상·고객 실적으로 확대하지 않습니다.
- 브라우저 자동화의 모바일 크기·WebKit 검사는 실제 iPhone Safari 기기 검사와 다릅니다.
