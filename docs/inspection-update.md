# 실행 결과 탐색과 점검 계측 보완

2026-10-17 KST · 시작 기준 `4bddddad771b7f70bd60f6870673ce3217d0f1a0`

[9개 프로젝트 비교와 외부 데모의 확인 수준](comparative-research-2026-10.md)을 바탕으로 기존 세 경로를 보완했다. 모델·서버·DB 구조와 무료 운영 조건은 유지한다.

## 화면에서 바뀐 점

| 이전 | 변경 | 확인 경로 |
|---|---|---|
| 실행 로그의 응답 JSON을 각각 열어 작업 ID를 찾아야 함 | 전체 / 실행 차단 / 기록·재시도 필터. 차단 사유·작업 ID·신규/과거 기록을 바로 표시하고 원본은 펼쳐 확인 | [실행 재현](https://sokldjs554.github.io/recheck-ml-serving/#case) → 전체 과정 실행 → 실행 로그 |
| 6개 부하 막대와 긴 상세 표 | 30초 구간 선택 → 해당 구간의 예정 요청·유효 응답·전송/완료/유효 요청률·보류·거절·지연·최대 대기 확인 | [모델 부하](https://sokldjs554.github.io/recheck-ml-serving/#serving) → 막대 선택 |
| 실패의 4단계 설명과 외부 원본 링크 | 실제 실패/오류 해제 trace 선택 → span별 시간·서비스·부모 ID·예외 확인 → 같은 응답의 API 로그·SQL 기록 대조 | [장애 복구](https://sokldjs554.github.io/recheck-ml-serving/#recovery) → 요청 한 건의 내부 흐름 |

필터·구간·span 선택은 읽기 전용이며 추가 API 요청을 보내지 않는다. 실행 세션·진행·로그·작업 ID는 기존 `CaseFlow`가 소유한다. 필터 선택 자체는 화면 재진입 시 초기화될 수 있지만 원본 실행 결과는 유지한다.

[실행 로그 화면](evidence/inspection-case.png) · [부하 화면](evidence/inspection-serving.png) · [추적 화면](evidence/inspection-recovery.png) · [부하 모바일](evidence/inspection-serving-mobile.png) · [추적 모바일](evidence/inspection-recovery-mobile.png)

## 관측 결과와 계측 범위

- 부하 화면은 기존 180초·2사이클·300ms 예산의 로컬 CPU 실험을 재사용한다. 목표 **120 req/s**와 과부하 유효 응답 **약 67.6 req/s**를 구분한다. 구간별 전송/완료/유효율의 분모는 해당 구간 요청의 마지막 완료까지 관측한 시간이다. 고정 30초 창의 수치는 원본 JSON에 별도로 있다.
- 추적 화면은 2026-10-12 로컬 lightweight 장애 실험의 실제 OTLP를 재사용한다. CPU 부하 실험이나 상담 체험과 같은 요청이 아니다. 나노초 epoch의 차이는 Python 정수로 계산한 뒤 ms로 내보낸다. 부모/자식 시간이 겹치므로 합산하지 않는다.
- `fence.commit`은 SQL 커밋 시간이 아니다. 독립 PostgreSQL 조회와 receipt 일치로 저장을 확인하며 네이티브 SQL span이 없다는 한계를 표시한다. OpenTelemetry의 UNSET도 성공으로 바꾸지 않고 ‘오류 표시 없음’으로 표시한다.
- 정기 점검은 기존 여섯 HTTP 요청 각각의 클라이언트 왕복 시간·method·status와 실패 시 exception 종류를 추가로 기록한다. URL·body·credentials는 추가 로그에 넣지 않는다. 응답 파싱·내용 검증은 전체 과정 시간에는 포함되지만 개별 HTTP 왕복 시간과 구분한다.

실제 로컬 Python API·SQLite·lightweight 모델에 새 점검을 3회 실행했다. 전체 과정은 **38.049 / 22.133 / 30.661ms**였고 6단계가 각각 기록되었다. 이는 계측 동작 확인이며 공개 호스트 성능·처리 용량·SLA 측정이 아니다. [원본](evidence/inspection-local-verification.json).

[2026-10-13 공개 점검](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38328704268)은 **기능 3/3, 5초 내 2/3**으로 실패했다. 전체 과정은 약 **54.037 / 2.135 / 1.630초**다. [당시 배포 검증 성공](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/38228371606)과 구분한다. 과거 단계별 시간이 없어 원인은 미확정이며, 이번 계측으로 과거 원인을 진단했다고 주장하지 않는다. 기준·분모·실패 기록은 유지했다.

## 시연과 검증

- 실제 로컬 API·SQLite에서 6단계, 차단/기록 로그 선택, 비교 화면 왕복을 다시 촬영했다. 화면·응답 합성이나 배속 없이 **42.2초 WebM**, MP4 fallback, 최신 포스터를 제공한다.
- 백엔드 **145개 통과**, SQLite 조건 및 실제 loopback HTTP 검사 포함. `PYTHONPATH=backend RECHECK_NETWORK_TESTS=1 OTEL_TRACES_SAMPLER=always_on` 사용. PostgreSQL 검증은 기존 GitHub CI의 독립 서비스에서 수행한다.
- 프런트 **46개 통과**, TypeScript·Vite 빌드 및 측정 요약 원본 대조 통과.
- 로컬 Chromium **60개 검사 통과**: 기본 18·근거 변경 12·실행 사례 10·SQL 비교 7·서빙 6·영상/탐색/반응형 7. 기존 버튼과 상단 버튼의 동시 클릭, 실행 중/완료 후 이동, 만료·재시작·불확실한 응답 재시도 검사 포함.
- 새 검사에서는 로그 필터의 원본 보존, 여섯 구간 모두의 키보드 선택과 원본 수치, 실패/복구 span·SQL ID, 탐색 중 추가 API 요청 없음, 320/390/768/1440px 배치와 실제 영상 decode를 확인한다.
- 화면 캡처를 실제로 열어 확인했다. 개발 중 발견한 모바일 원본 JSON 펼침의 grid 너비 문제와 선택 버튼으로 바뀐 막대의 0 너비 문제를 수정하고 회귀 검사에 포함했다.

코드 리뷰에서 펼침 표시가 사라진 부분을 복구했고, 일부 구간만 선택하던 검사도 여섯 구간 전체로 보완했다. [로컬 실행·촬영 검증 JSON](evidence/inspection-local-verification.json).

## 재현

로컬 API·모델·UI 실행은 [README](../README.md#실행-방법)를 따른다. 브라우저 검사는 실행 중인 로컬 서버에 연결한다.

```bash
PYTHONPATH=backend RECHECK_NETWORK_TESTS=1 OTEL_TRACES_SAMPLER=always_on python -m pytest backend/tests -q
npm --prefix demo test
python scripts/build_serving_summary.py --check
python scripts/check_presentation_browser.py --base http://127.0.0.1:5178 --api http://127.0.0.1:8023
python scripts/synthetic_monitor.py --base http://127.0.0.1:8023 --count 3 --interval 1 --budget-ms 5000
```

공개 반영에는 기존 [검증 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/workflows/ci.yml)와 [Pages·공개 브라우저 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/workflows/pages.yml)를 사용한다. 공개 점검은 [별도 workflow](https://github.com/sokldjs554/recheck-ml-serving/actions/workflows/synthetic-monitor.yml)이며 배포 성공과 시간 예산 충족은 같은 결론이 아니다.

## 남은 한계

외부 데모 조사는 공개 페이지 내용·공식 캡처·소스 확인을 포함하지만 새 원격 조작·영상 재생은 미검증이다. RECHECK는 무료 서버 시작 지연 가능성, 새로고침 후 클라이언트 상태 복원 미지원, 실기기 Safari·실제 사용자 이해도 미검증을 유지한다. 저장된 결과를 탐색하기 쉬워졌다는 구현 의도와 이해도 개선이 실증됐다는 주장은 다르다. 새 은행 운영 경험·장기 SLA·사업 성과를 만들었다고 표현하지 않는다.
