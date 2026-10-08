# 합성 모델 카드

목적은 실제 학습 산출물의 버전·해시·추론 경계를 검증하는 것이다. 실제 금융 사기 탐지, 신용 평가, 계좌 차단에 사용하지 않는다.

- 알고리즘: StandardScaler + scikit-learn LogisticRegression.
- 입력: 금액 비율, 낯선 수취인 정도, 최근 정보 변경, 요청 빈도 비율의 4개 합성 특징.
- 데이터: 시드 660065, 총 4,000건 중 학습 3,000건·평가 1,000건. 개인정보와 외부 거래 자료 없음.
- 평가: risk-v1 holdout ROC AUC 0.8601128472, risk-v2 0.8600868056. 생성기의 가정 아래에서만 의미가 있으며 실제 금융 데이터에 일반화되었다는 근거가 아니다.
- 재현: `cd backend && .venv/bin/python -m recheck.model --output artifacts`.
- 식별: 파라미터·시드·배포 epoch 기반 SHA-256, 직렬화 파일의 SHA-256은 별도. 해시는 디지털 서명이 아니다.
- 배포: 서버 시작 시 작은 두 모델을 결정적으로 학습한다. 임의 pickle을 역직렬화하지 않는다. 교체 시 epoch는 단조 증가하며 두 기반 모델을 번갈아 사용한다.

브라우저 모드의 점수는 별도 로컬 규칙이다. 그 타임라인과 주입 지연은 Python 모델 속도나 OpenTelemetry 실측이 아니다. CPU의 작은 동기 추론은 보유한 슬롯 안에서 끝내며, 무거운 모델을 위한 격리 프로세스 풀·GPU 메모리 계획은 구현 범위 밖이다.

학습 코드와 정확한 해시: [model.py](../backend/recheck/model.py), [실행 기록](../backend/IMPLEMENTATION.md).
