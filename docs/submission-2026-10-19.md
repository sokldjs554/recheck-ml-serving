# 제출 기준과 마무리 기록

시작 기준: `fe5df9d84be0c5bb29fcfb9132a4d7dcea15ba1a`, 브랜치 `feat/project-introduction`. 원격 main과 같았고 미커밋 변경이 없었다. 시작 시 실제 Render live 커밋은 `2c3d10f07c2ef6094149345c9bc7d478add48fcc`였다. 이후 검사·문서 커밋은 백엔드 실행 코드를 변경하지 않았다.

제출 UI·코드 버전: [`b999cb9`](https://github.com/sokldjs554/recheck-ml-serving/commit/b999cb9fca31cb0bec2df956f54b45b99413ab87). [공개 데모](https://sokldjs554.github.io/recheck-ml-serving/?v=b999cb9#case). 후속 검증 기록 커밋은 문서·캡처만 갱신한다.

이번 범위는 첫 응답 근거 대조, 과거 측정 표시, 현재 설계 설명, 친구용 점검 준비다. 주제·모델·DB 구조·요청 처리 계약을 유지한다.

## 첫 응답 지연과 실제 배포 설정

2026-10-19에 연결된 Render 도구로 서비스 `srv-db3rmj3ncjis73bi8fl0`를 실제 조회했다. 무료 플랜, 시작 명령 `python scripts/serve_demo.py`, **실제 `healthCheckPath`는 빈 문자열**이었다. 저장소의 [render.yaml](../render.yaml)은 `/health`다. YAML 존재와 서비스 적용을 구분한다. [조회값·기존 점검 원자료](evidence/submission-2026-10-19/runtime-review.json).

수동 적용 위치: [Render 서비스 Settings](https://dashboard.render.com/web/srv-db3rmj3ncjis73bi8fl0/settings) → **Health Checks → Edit → Health Check Path `/health` → Save Changes**. 저장 후 경로가 유지되는지, 해당 배포가 live인지 확인한다. 현재 연결 도구에는 기존 서비스의 이 필드를 수정하는 기능이 없고 환경에 Render 관리 자격 증명도 없어 직접 적용하지 못했다. HTTP 경로가 없는 기본 TCP 검사와 HTTP 준비 검사는 다르다. [Render 공식 설정 설명](https://render.com/docs/health-checks).

### 기존 실패 표본과 준비된 표본

이번에 조회한 기존 [10월 18일 20:11 KST 점검](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39122204727)은 기능 3/3 성공이지만 5초 기준 2/3으로 실패했다. 첫 표본을 제외하지 않는다.

| 관측 경계 | 첫 표본 | 두 번째 | 세 번째 |
|---|---:|---:|---:|
| 전체 6요청 점검 | 73.986초 | 1.730초 | 1.678초 |
| 첫 `/health` 왕복 | 72.479초 | 0.239초 | 0.592초 |
| `/decisions` 요청 왕복 | 0.258초 | 0.608초 | 0.232초 |

첫 표본의 긴 지연은 추론 요청 자체보다 그 전에 실행한 health 왕복에 집중되어 있다. 같은 서비스 인스턴스 로그에는 다음이 남았다.

- 20:11:35.219 KST: `model_process_starting`
- 20:11:58.840 KST: `model_ready`, **프로세스 시작 이후 23.645초**
- 20:11:58.840 KST: `api_process_starting`
- 20:12:15.888 KST: API가 `0.0.0.0:10000`에 바인딩, **API 시작 로그 이후 약 17.047초**

모델 준비 시간에는 프로세스 생성·import·artifact 로딩 등이 함께 포함된다. API 시작~바인딩에도 import·DB 초기화·모델 해시 준비 등이 포함된다. 이를 순수 추론 시간이나 순수 DB 시간으로 이름 붙이지 않는다. 외부 요청 시작과 Render 로그는 다른 시스템의 시계이며, 나머지 시간을 플랫폼 대기·네트워크·DB 중 하나로 확정할 증거는 없다. `/health` 내부 DB 확인과 모델 확인의 개별 시간도 이 표본에는 없다.

뒤의 [23:36 KST 점검](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39136779184)은 전체 **2.487·1.732·1.558초**, 기능·5초 기준 3/3 성공이었다. 첫 표본 전에 API 바인딩 로그가 23:28 KST에 있었으므로 이미 준비된 인스턴스의 표본으로 구분한다. 이 성공이 앞선 실패를 없애지 않는다.

조회 범위의 세 시작에서 모델 준비는 23.645·24.988·26.355초였다. 90초의 기존 시작 대기를 유지했고, 이 범위에서 모델이 준비되기 전에 종료된 로그는 없었다. `test_hosted_startup.py`는 35초 지연 준비·90초 초과·프로세스 조기 종료·종료 신호를 검사한다. 이 테스트의 가상 시계는 운영 성능 측정이 아니다.

[Render 무료 운영 문서](https://render.com/docs/free)는 유휴 후 내려간 서비스의 재시작을 설명한다. 이 호스팅 제약과 로그의 시작 시간을 확인했지만, 과거 **10월 13일 54.037초**, **10월 18일 84.815초** 실패에 원인을 소급해 확정하지 않는다. [이전 기록](release-2026-10-18.md#4-운영-기록-대조).

### 무료 운영에서 유지한 처리

준비되지 않은 서비스를 정상으로 표시하지 않고, 실제 health 확인 뒤 체험을 진행한다. 기존 첫 연결 응답 대기 90초와 실패 후 명시적 재시도·저장된 시연을 유지한다. 대기 시간을 늘려 5초 기준을 통과시키거나 첫 표본을 워밍업으로 버리지 않는다. 추가 유료 서비스나 상시 깨우기 요청은 만들지 않았다. 원인별 비용이 계측되지 않은 초기화 로직을 추정으로 재작성하지 않았다.

## 수치와 현재 코드의 관계

[측정 출처 목록](measurement-provenance.md)에 README·데모의 주요 저장 결과 11개를 연결했다. 7개 자료는 원본에 포함된 소스 해시를 고정 커밋과 대조했고, 나머지는 자료 보관 커밋만 표시한다. 화면과 README의 수치 가까이에 날짜·코드/보관 링크·과거 실험 표시를 추가했다. 120건/s 투입 목표와 약 67.6건/s 유효 응답을 구분한다.

이번에는 처리량을 재측정하지 않았다. 현재 코드의 성능 수치나 개선율로 제시하지 않는다. 실제 공개 체험과 새 기능 회귀 결과는 과거 저장 실험과 별도다. [설계 선택·비용·코드](decisions.md)에는 잠금, JSON 저장, 프로세스 격리, 수용 제한, 저장 후 응답 실패를 현재 구현 기준으로 설명했다.

## 사람의 관찰 대기

[친구용 세 과제](usability-protocol.md)와 [빈 기록 양식](usability-record.md)을 준비했다. 상태는 **사용성 점검 준비 완료**다. 아직 참여자의 기록이 없으므로 사용성 결과·성공률·인용 발언을 작성하지 않았다.

관찰 기반 문구·동선 수정은 대기한다. 실제 기록을 받으면 문제 ID → 발언·행동 → 변경 파일·커밋 → 같은 과제 재확인으로 연결한다. 이번 출처 표시는 기술 자료 대조에 따른 정정이며 사람의 이해도 개선이 입증됐다는 뜻이 아니다. 기존 명사형 제목과 대표 체험 동선은 유지했다.

## 검증과 제출 버전

변경된 출처 표시의 빌드·반응형·원본 링크, 대표 체험과 복원, 기존 시작·취소·슬롯 계약을 확인했다. 아래 검사는 이번에 실행한 결과이며 앞의 기존 정기 점검 조회와 구분한다.

| 검증 | 결과 | 근거 |
|---|---|---|
| 로컬 기존 시작·모니터·실행 관측·CPU 슬롯 계약 | 30개 통과, 5.84초 | [로컬 요약](evidence/submission-2026-10-19/local-verification.json) |
| 로컬 프런트·production build | 61개 통과·빌드 성공 | 같은 요약 |
| 로컬 실제 API·SQLite·Chromium | 화면·미디어·결과·출처의 7개 검사 그룹 통과 | [상세](evidence/submission-2026-10-19/local-presentation.json) |
| PostgreSQL 전체 CI | 159개 통과·SQLite 전용 1개 제외, 51.72초 | [최종 CI](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39144572841), [발췌·범위](evidence/submission-2026-10-19/ci.json) |
| 현재 코드 동시 요청 계약·두 DB 비교 | 반복 계약 8개 통과·1개 제외 ×3, 두 비교 스크립트 성공 | 같은 CI |
| 프런트·과거 자료·정적 번들 | 61개 통과, 세 자료 생성기 검증·번들 일치 성공 | 같은 CI |
| 공개 배포 후 Chromium·macOS WebKit | 78개 확인 통과(69+9), page error 0 | [Pages·공개 검사](https://github.com/sokldjs554/recheck-ml-serving/actions/runs/39144572842), [항목별 결과·캡처 artifact](evidence/submission-2026-10-19/public-browser.json) |

CI 제외 항목은 `test_database.py::test_session_capacity_and_expired_session_cleanup`이다. SQLite 전용 fixture이며 [10월 18일 로컬 160개 통과](evidence/release-2026-10-18/local-validation.json)에 포함돼 있다. 백엔드가 그대로임을 대조해 이 별도 근거를 재사용했으며 오늘 다시 실행했다고 표시하지 않는다.

Render 배포 `dep-dbaf3mqvcj2c73a5mc4g`는 **2026-10-19 01:22:51 KST live**였다. 이번 시작에서 모델 준비는 26.553초, API 시작 로그부터 포트 바인딩까지 약 21.245초였다. 초기화 중 조기 종료는 없었다. 실제 health 경로는 배포 후 재조회에서도 빈 문자열이었다. [배포 설정·시작 로그](evidence/submission-2026-10-19/deployment.json). 이 배포 성공과 준비된 서버의 기능 검증을 무료 서버 첫 요청 5초 달성으로 표현하지 않는다.

공개 검사에서 상단·기존 버튼의 단일 실행, 오래된 답변 차단 → 새 작업 기록 → 동일 키의 같은 작업 반환, 진행 중/완료 후 화면 이동, 중간·완료 새로고침 복원, 명시적 초기화·만료 안내를 확인했다. 출처 날짜·고정 커밋 링크와 과거 실험 표시도 확인했다. 1440·768·390·320px의 로그·ID·표·펼침 영역을 검사했으며 브라우저의 화면 크기 모사와 실제 기기 검사를 구분한다. 저장된 시연 영상은 10월 18일 촬영분을 재사용했고 두 엔진에서 재생을 확인했다.

실제 배포 화면: [모델 부하·데스크톱](evidence/submission-2026-10-19/public-serving-1440.png) · [모델 부하·모바일](evidence/submission-2026-10-19/public-serving-390.png) · [복구 근거](evidence/submission-2026-10-19/public-recovery-1440.png) · [완료 기록 복원·모바일](evidence/submission-2026-10-19/public-case-restored-390.png). 공개 API에 연결한 WebKit 검사 artifact에서 그대로 가져왔다.

## 본인 역할과 종료 범위

사용자의 역할은 주제·방향 최종 결정, 기능 추가·범위 조정, 구체적인 수정 요구와 결과 검토다. 코드 작성과 데모 제작은 AI가 주로 담당했다. 기술 결과를 지원자의 직접 구현·실험 경력으로 바꾸지 않는다. 이번 작업은 프로젝트와 근거 문서에 한정하고 자소서·포트폴리오는 작성하지 않는다.

종료 시 남기는 항목은 Render HTTP health 경로의 수동 적용, 첫 응답의 미분리 지연과 무료 호스팅 제약, 사람의 실제 관찰 결과다. 실제 고객 확보·상용 SLA·모든 기기 지원을 이 작업의 종료 조건으로 추가하지 않는다.

**이번 기술 보완·문서 정리·배포 검증은 종료한다.** 친구에게 실제 과제를 진행한 기록이 오기 전까지 관찰 기반 UI 수정은 별도 대기다. 제출 시 README·데모·이 문서와 측정 출처 목록을 사용하며, 과거 처리량을 현재 코드의 재측정값으로 바꾸지 않는다.
