import handoff from './model-handoff.json';

const labels: Record<string, string> = {none: '정상 모델 인계', checksum: '파일에 바이트 추가', feature_order: '입력 특징 순서 변경', runtime: '라이브러리 버전 변경', missing: '두 번째 모델 파일 삭제', prediction: '기준 예측값 변경'};
const root = 'https://github.com/sokldjs554/recheck-ml-serving/blob/main/';

export default function ModelHandoff() {
  return <section className="model-handoff" aria-label="학습 모델 인계 검증">
    <div className="handoff-intro"><h2>학습 모델과 서빙 모델의 일치 검증</h2><p>이전에는 서버가 켜질 때마다 다시 학습했습니다. 이제 배포물에 담긴 모델을 검사하고, 통과한 파일로 추론합니다.</p></div>
    <div className="handoff-contract"><span>학습 산출물</span><span aria-hidden="true">→</span><span>파일 · 입력 · 버전 검사</span><span aria-hidden="true">→</span><span>기준 예측 대조</span><span aria-hidden="true">→</span><span>서빙 시작</span></div>
    <div className="recovery-table-scroll" role="region" aria-label="모델 인계 실험 결과" tabIndex={0}><table className="recovery-table"><thead><tr><th>같은 산출물에 가한 변화</th><th>새 프로세스의 결과</th><th>관측값</th></tr></thead><tbody>{handoff.cases.map(row => <tr key={row.case}><th>{labels[row.case]}</th><td>{row.state === 'served' ? '추론 응답' : '시작 차단'}</td><td>{row.state === 'served' ? `${row.predictions?.length}개 예측 일치 · 재학습 금지` : row.reason}</td></tr>)}</tbody></table></div>
    <details><summary>어떤 값으로 대조했는지 보기</summary><p>합성 입력 [0.2, 0, 1, 0.4]에 대해 학습 직후와 새 서버의 점수를 대조했습니다. 총 3개 입력 × 3개 배포 버전을 검사했습니다.</p><dl className="handoff-scores">{handoff.manifest.models.map(model => <div key={model.version}><dt>{model.version}</dt><dd>{model.probe_scores[1].toFixed(12)}</dd></div>)}</dl><p>같은 기반 모델을 다시 사용하는 risk-v3도 risk-v1과 다른 해시를 받습니다. 이전 판단을 새 배포의 결과로 취급하지 않도록 한 장치입니다.</p></details>
    <p className="serving-boundary">새 Python 프로세스마다 학습 함수를 금지한 뒤 ASGI 요청으로 확인한 저장 기록입니다. 공개 API의 현재 상태나 처리 속도를 나타내지 않습니다. 체크섬은 파일 손상을 탐지하며 배포자의 신원을 인증하지 않습니다.</p>
    <footer className="serving-source"><time>{new Date(handoff.measured_at).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', hour12: false})} KST</time><a href={root + 'docs/evidence/model-handoff.json'} target="_blank" rel="noreferrer">예측값·실패 사유 원본 ↗</a><a href={root + 'docs/model-handoff.md'} target="_blank" rel="noreferrer">재현 명령과 설계 ↗</a></footer>
  </section>;
}
