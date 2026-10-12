# 학습 산출물을 서버로 넘기는 경계

기존 서버는 두 합성 모델을 시작 시점마다 학습했다. 모델 파일을 내보내는 CLI는 있었지만 서버는 그 파일을 소비하지 않았다. 같은 시드로 얻는 점수만으로는 **학습한 산출물이 실제 서빙에 사용되는지**를 확인할 수 없었다.

지금은 학습 프로세스가 전처리와 추론기를 함께 내보내고, 서버는 배포물의 파일·입력 규격·런타임 버전과 기준 예측을 검사한다. 설정한 산출물이 없거나 검사에 실패하면 시작에 실패한다. 몰래 재학습해서 성공처럼 응답하지 않는다.

## 재현

```bash
# 저장소 루트, backend/.venv 설치 후
PYTHONPATH=backend backend/.venv/bin/python -m recheck.model --output work/release-a
RECHECK_MODEL_BUNDLE="$PWD/work/release-a" backend/.venv/bin/python scripts/serve_demo.py
# 다른 터미널: model_source=bundle, bundle_sha256 확인
curl http://127.0.0.1:8000/health

# 새 프로세스에서 정상 인계와 다섯 가지 실패를 재현
backend/.venv/bin/python scripts/verify_model_handoff.py --output work/model-handoff.json
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_model_bundle.py -q
```

CPU 앙상블은 `--workload cpu-ensemble`로 **별도 디렉터리**에 내보낸다. 실행 시 `RECHECK_WORKLOAD=cpu-ensemble`과 해당 `RECHECK_MODEL_BUNDLE`을 함께 지정한다. 모델 이름만 바꾸고 다른 연산을 실행하지 않도록 workload가 다르면 시작을 막는다.

## 계약과 실패 처리

| 검사 | 막는 실수 | 검사 시점 |
|---|---|---|
| 두 파일의 SHA-256 | 손상·누락·잘못 복사한 파일 | 두 파일 모두 역직렬화 전 |
| 입력 이름·순서·자료형·범위 | 전처리와 서빙의 규격 차이 | 역직렬화 전 |
| Python 주·부 버전, sklearn/numpy/scipy/joblib 정확 버전 | 직렬화 호환성을 확인하지 않은 런타임 변경 | 역직렬화 전 |
| 파라미터 기반 모델 해시 | 모델 버전과 파라미터 불일치 | 로딩 후, 준비 전 |
| 고정 입력의 기준 점수 3개 | 재로딩 후 예측 불일치 | 로딩 후, 준비 전 |

파일은 검증한 바이트를 메모리에서 읽어 경로를 재개방하는 사이의 변경을 피한다. 프로세스는 한 번 검증한 릴리스를 고정해서 사용한다. 디렉터리를 실행 중 덮어쓰는 방식의 교체는 지원하지 않는다. 새 배포물로 프로세스를 교체한다. 데모의 risk-v1/v2/v3 전환은 두 기반 모델을 순환하는 실험이며 모델 레지스트리 제품을 구현했다는 의미가 아니다.

`joblib`은 신뢰할 수 없는 객체에 안전한 형식이 아니다. 이 저장소/빌드에서 만든 산출물만 배포하며 업로드 API는 없다. 체크섬과 manifest를 함께 바꿀 수 있는 공격자를 막는 서명 검증은 구현하지 않았다. 해시는 손상 검출과 동일성 확인이지 출처 인증이 아니다.

## 실행 결과와 배포

[원본 실행 기록](evidence/model-handoff.json): 학습 함수가 호출되면 즉시 실패하도록 한 **별도 Python 프로세스**에서 3개 입력 × 3개 배포 버전의 점수 9개가 학습 결과와 일치했다. risk-v3는 같은 점수를 내도 risk-v1과 다른 해시를 사용한다. 파일 손상·특징 순서 변경·라이브러리 불일치·파일 누락·기준 점수 변경은 각각 시작이 차단됐다.

이 기록은 새 worker 프로세스 안의 ASGI HTTP 호출이다. 실제 외부 네트워크나 공개 Render 서버의 지연 측정이 아니다. 추가 회귀 테스트는 process 실행 모드의 자식 프로세스에서 추론값을 확인한다. 세 기준 입력은 모델의 모든 입력에 대한 정확성·일반화 검증을 대신하지 않는다.

- 공개 Python 실행기는 `backend/model_artifacts`의 작은 두 모델을 기본으로 사용한다. 버전 고정한 의존성으로 생성한 파일을 저장소에 포함해 무료 Render도 추가 빌드 설정 없이 받는다.
- Docker는 이미지 빌드 때 해당 환경에서 같은 산출물을 다시 만들며, 실행 단계에서는 학습하지 않는다.
- 직접 `uvicorn recheck.worker:app`를 실행하면서 bundle을 지정하지 않은 로컬 실험은 기존 학습 경로를 유지한다. `/health`는 이를 `startup-training`으로 구분한다.
- CI는 배포용으로 포함한 산출물을 실제 로딩하고 정상/실패 인계 실험을 재실행한다. 공개 `/health`에서 `model_source=bundle`과 manifest 해시로 배포 적용 여부를 확인할 수 있다.

## 조사에서 가져온 기준

토스의 [DS·MLE 협업](https://toss.tech/article/ds-mle-cowork)에서 확인한 공통 모델 인터페이스·학습 산출물의 전달 문제를 이 프로젝트의 크기에 맞춰 적용했다. Daniel Choi의 [공개 OCR 실험](https://github.com/SangbumChoi/OCR)에서처럼 조건·실패·재현 명령을 함께 둔다. 해당 프로젝트의 성능이나 채용 성과를 RECHECK의 실적으로 옮기지 않는다.
