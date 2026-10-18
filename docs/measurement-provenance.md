# 측정 수치의 출처와 현재 코드

2026-10-19 점검. README·모델 부하·장애 복구·세 방식 비교의 저장 수치는 **과거 실험**이다. 이번 제출 코드의 처리량을 재측정하지 않았다. 기능 회귀가 통과해도 과거 성능이 동일하다는 뜻은 아니다.

- **소스 대조:** 원본에 기록된 source_sha256을 해당 고정 커밋의 파일 바이트와 모두 비교했다. 코드 전체·호스트 상태를 그 커밋 하나로 완전히 복원했다는 의미는 아니다.
- **자료 보관:** 해당 원본의 보관 커밋만 확인된다. 실행 당시 코드 전체를 식별하는 해시가 없으므로 ‘측정 커밋’이라고 부르지 않는다.
- 아래 시간은 원본의 시작/측정 타임스탬프를 KST로 변환한 값이다. 오늘 날짜로 덮어쓰지 않는다.

| 화면의 자료 | 측정 시점 (KST) | 코드·자료 연결 | 핵심 조건·수치 |
|---|---|---|---|
| [짧은 전체 경로 부하](evidence/fullpath-load.json) | 2026-10-12 00:33 | [976ebb7](https://github.com/sokldjs554/recheck-ml-serving/tree/976ebb74e022238a0b6cc49a61e2352e09d95bc3) · 소스 16개 해시 대조 | API→CPU 2프로세스→PostgreSQL, 요청률별 5초×2회, 500ms 기준. 같은 DB의 다른 검증과 경합한 오류 1건 포함 |
| [별도 과부하 회귀](evidence/fullpath-saturation.json.gz) | 2026-10-12 01:00 | [e8c6b67](https://github.com/sokldjs554/recheck-ml-serving/tree/e8c6b677d4b2c4e8b8f06a7791b5d1b39ee993f4) · 소스 16개 해시 대조 | 전용 로컬 DB, 60·120 req/s 각각 2초×2회, 500ms 기준. 120 투입 480건 중 유효 250건 |
| [180초 지속 부하](evidence/fullpath-sustained.json.gz) | 2026-10-12 14:59 | [0b99e35](https://github.com/sokldjs554/recheck-ml-serving/tree/0b99e35cf7d59f624cbc8eab5c31bc1359ca4108) · 소스 18개 해시 대조 | 공유 호스트 CPU quota 4코어, 5초 워밍업 제외, 10→120→10 req/s 두 번. 예정 시점부터 300ms 이내 유효 응답 약 67.6 req/s |
| [정합성 비용](evidence/consistency-costs.json.gz) | 2026-10-12 15:08 | [0b99e35](https://github.com/sokldjs554/recheck-ml-serving/tree/0b99e35cf7d59f624cbc8eab5c31bc1359ca4108) · 소스 3개 해시 대조 | 로컬 PostgreSQL 직접 호출, 54조건×3회×4 wave. 동시 8·큰 상태·변경 없음: 같은 세션 91.89건/s, 다른 세션 111.43건/s |
| [실패 trace·SQL](evidence/failure-trace-proof.json) | 2026-10-12 14:55 | [0b99e35](https://github.com/sokldjs554/recheck-ml-serving/tree/0b99e35cf7d59f624cbc8eab5c31bc1359ca4108) · 소스 17개 해시 대조 | 로컬 /decisions, lightweight 모델 오류 주입 후 해제. 실제 OTLP·별도 SQL 대조. 처리량 실험과 별도 |
| [kind 복구](evidence/kubernetes-proof.json) | 2026-10-09 01:28 | [1843bfb](https://github.com/sokldjs554/recheck-ml-serving/tree/1843bfb452d4a1acf43be35c107ef351ae467131) · 자료 보관 | 단일 노드, DB Pod 교체 후 첫 실패→첫 성공 2.502초; 단계 32.717초. 최신 CI 재실행의 시간이 아님 |
| [worker 단독 30 req/s](evidence/compute-capacity-summary.json) | 2026-10-09 01:03 | [5b0b150](https://github.com/sokldjs554/recheck-ml-serving/tree/5b0b150218e8d238e70a82af20b21f709fb830b7) · 자료 보관 | 직접 모델 HTTP, CPU 2프로세스, 30초·900건 중 896건이 200ms 이내. API·DB 제외 |
| [worker 단독 60 req/s](evidence/compute-sustained-summary.json) | 2026-10-09 00:59 | [5b0b150](https://github.com/sokldjs554/recheck-ml-serving/tree/5b0b150218e8d238e70a82af20b21f709fb830b7) · 자료 보관 | 직접 모델 HTTP, CPU 2프로세스, 60초·3,600건 중 2,572건이 200ms 이내. 앞 실험과 시간도 다름 |
| [추적·알림](evidence/observability-latest.json) | 2026-10-09 01:16 | [5b0b150](https://github.com/sokldjs554/recheck-ml-serving/tree/5b0b150218e8d238e70a82af20b21f709fb830b7) · 자료 보관 | 로컬 서비스 중단과 정상화, Jaeger·Prometheus·알림 수신. 실제 사업 장애율 아님 |
| [세 방식 비교](evidence/safety-evaluation.json) | 2026-10-12 00:34 | [976ebb7](https://github.com/sokldjs554/recheck-ml-serving/tree/976ebb74e022238a0b6cc49a61e2352e09d95bc3) · 소스 4개 해시 대조 | 각 DB 동일 9개 사건, 오래된 결과 허용 6/6·5/6·0/6. 준비된 사건 결과이며 운영 사고율 아님 |
| [동시 실행 비교](evidence/action-workloads.json) | 2026-10-12 00:34 | [976ebb7](https://github.com/sokldjs554/recheck-ml-serving/tree/976ebb74e022238a0b6cc49a61e2352e09d95bc3) · 소스 5개 해시 대조 | SQLite·PostgreSQL의 같은 키/다른 키/변경/재시도/잠금 시간 초과. HTTP 부하가 아닌 SQL 경합·정상 경로 별도 측정 |

[이번 대조 원자료](evidence/submission-2026-10-19/measurement-audit.json). 화면에서도 같은 JSON을 읽어 날짜와 소스 대조/자료 보관을 표시한다. 원본 실험 수치·날짜·파일은 수정하지 않았다.

<details>
<summary>고정 커밋의 소스 해시 대조 재현</summary>

전체 Git 이력을 받은 저장소 루트에서 실행한다. 해시가 없는 자료를 소스가 검증된 것으로 처리하지 않는다.

```sh
python - <<'PY'
import gzip, json
from pathlib import Path
from scripts.evidence_provenance import verify_sources
root = Path.cwd()
records = json.loads((root / 'docs/evidence/submission-2026-10-19/measurement-audit.json').read_text())
for entry in records:
    if not entry['matching_revisions']:
        print('자료 보관만 확인:', entry['file'])
        continue
    path = root / 'docs/evidence' / entry['file']
    raw = path.read_bytes()
    report = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    verify_sources(root, report, entry['matching_revisions'][0])
    print('소스 해시 일치:', entry['file'])
PY
```

</details>

## 현재 검증과 다른 숫자

- 공개 상담 TF-IDF 체험의 실시간 결과·작업 ID·로그는 현재 API 응답이다. 브라우저 복원 기록은 그 과거 응답이며 재조회로 표시하지 않는다.
- 상담에서 새로 평가한 작은 검색 fixture의 Recall·p95는 해당 세션의 실시간 평가다. LLM 품질이나 대표적인 은행 질의의 성능으로 사용하지 않는다.
- 모델 artifact의 학습 평가 수치는 bundle의 저장된 평가이며 배포 시 모델 인계 검증과 구분한다.
- CI에서 현재 코드로 수행하는 짧은 정합성·모델 인계·기능 회귀는 그 실행의 artifact로 보존한다. 화면의 과거 180초 결과나 kind 복구 시간을 CI 숫자로 교체하지 않는다.
- 공개 정기 점검의 health·추론 요청 왕복 시간은 무료 서비스에서 얻은 표본이다. 로컬 처리량·장기 SLA와 합산하지 않는다.

**120건/s는 목표 투입량**, 약 **67.6건/s는 해당 과부하 조건에서 시간 기준을 만족한 유효 응답률**이다. 200ms worker 직접 호출, 300ms 전체 경로, 500ms 짧은 회귀는 기준·경로·기간이 달라 개선율을 계산하지 않는다.

현재 실행·배포와 제출 주장 검증은 [최종 제출 기록](submission-2026-10-19.md)을 따른다.
