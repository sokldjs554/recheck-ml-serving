import { useState } from 'react';
import { defaultApiBase } from './api';
type Counter = {name: string; labels: Record<string,string>; value: number};
type Sample = {id: string; at: number; boot_id: string; ready: boolean; reason: string; api: Counter[]; model: Counter[]; dropped_unpersisted_samples: number};
type Journal = {storage: string; samples: Sample[]};
const stamp = (at: number) => new Date(at * 1000).toLocaleString('ko-KR', {timeZone:'Asia/Seoul',hour12:false});
export default function PublicOperations() {
  const [journal, setJournal] = useState<Journal | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setError('');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    try {
      const base = defaultApiBase(location.hostname, localStorage.getItem('recheck-api-base'));
      const response = await fetch(base + '/api/operations', {signal:controller.signal});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      if (!Array.isArray(result.samples)) throw new Error('관측 기록 형식 확인 필요');
      setJournal(result);
    } catch (e) { setError(e instanceof Error ? e.message : '조회 실패'); }
    finally { clearTimeout(timer); setBusy(false); }
  }
  const latest = journal?.samples.at(-1);
  const total = (rows: Counter[], name: string, predicate: (r:Counter) => boolean = () => true) => rows.filter(r => r.name === name && predicate(r)).reduce((sum,r) => sum+r.value,0);
  return <section className="public-observation" aria-label="공개 서버 운영 기록">
    <h2>공개 서버 운영 기록</h2>
    <p>실제 요청이 발생한 구간의 HTTP 응답·모델 실패·준비 상태를 PostgreSQL에 보관합니다. 서버가 다시 시작되어도 이전 관측은 남습니다.</p>
    <p>10월 12일 재배포 검증에서 서버 실행 ID가 바뀐 뒤에도 같은 작업 1개를 그대로 재생했습니다. <a href="https://github.com/sokldjs554/recheck-ml-serving/blob/main/docs/evidence/public-storage-verification.json" target="_blank" rel="noreferrer">재배포 전후 원본 ↗</a></p>
    <button className="operations-load" onClick={load} disabled={busy}>{busy ? '공개 서버에 연결 중…' : '운영 기록 조회'}</button>
    {busy && <p role="status">무료 서버가 잠들어 있으면 시작에 시간이 걸릴 수 있습니다. 최대 90초까지 기다립니다.</p>}
    {error && <p role="alert">기록을 가져오지 못했습니다: {error}. 조회 실패를 정상 상태로 표시하지 않습니다.</p>}
    {journal && !latest && <p>아직 저장된 관측이 없습니다.</p>}
    {latest && <div aria-live="polite" data-testid="public-operations">
      <p><time>{stamp(latest.at)} KST</time>에 저장 · {journal?.storage} · 당시 준비 상태 {latest.ready ? '정상' : latest.reason}</p>
      <dl className="serving-outcomes">
        <div><dt>이번 서버 실행의 HTTP 응답</dt><dd>{total(latest.api, 'recheck_http_requests_total')}<small>건</small></dd></div>
        <div><dt>HTTP 5xx</dt><dd>{total(latest.api, 'recheck_http_requests_total', r => r.labels.status?.startsWith('5'))}<small>건</small></dd></div>
        <div><dt>모델 사용 불가로 보류</dt><dd>{total(latest.api, 'recheck_business_outcomes_total',r => r.labels.reason === 'model_unavailable')}<small>건</small></dd></div>
        <div><dt>조회된 기록</dt><dd>{journal?.samples.length}<small>개</small></dd></div>
      </dl>
      <p>서버 실행 ID <code>{latest.boot_id}</code></p>
      <details><summary>최근 관측 12개</summary><ol>{journal?.samples.slice(-12).reverse().map(row => <li key={row.id}><time>{stamp(row.at)}<br/>실행 {row.boot_id.slice(0,8)}</time><b>{row.ready ? '준비됨' : row.reason}</b><span>모델 보류 {total(row.api, 'recheck_business_outcomes_total',r => r.labels.reason === 'model_unavailable')}건</span></li>)}</ol></details>
      {latest.dropped_unpersisted_samples > 0 && <p>DB 장애 중 저장 대기 한도를 넘긴 관측 {latest.dropped_unpersisted_samples}개가 누락됐습니다.</p>}
    </div>}
    <p>활동이 있는 동안 60초마다 수집 · 7일 보관 · 최신 120개 조회. 데모 조작과 장애 주입 자동 점검도 함께 집계하며, 숫자는 실행 ID별 누적값입니다. 잠든 시간·관측 사이·강제 종료 직전은 알 수 없으며, 장기 가용성이나 실시간 무장애 표시가 아닙니다.</p>
  </section>;
}
