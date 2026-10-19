import { useRef, useState } from "react";
import data from "./serving-evidence.json";

const run = data.sustained;
const names: Record<string, string> = { normal: "정상", overload: "과부하", recovery: "정상 복귀" };
const n = (value: number) => value.toLocaleString("ko-KR");
const kinds = [
  { key: "useful_on_time", label: "유효 응답", hint: "300ms 안에 도착한 유효한 판단", tone: "useful" },
  { key: "deferred", label: "보류", hint: "HTTP 200이어도 사용할 수 없는 판단", tone: "deferred" },
  { key: "refused", label: "처리 한도 초과", hint: "HTTP 429 · 처리 한도 초과", tone: "refused" },
  { key: "server_timeout", label: "응답 시간 초과", hint: "HTTP 504 · 응답 시간 예산 초과", tone: "timeout" },
];

export default function LoadExplorer() {
  const [selectedIndex, setSelectedIndex] = useState(1);
  const [showException, setShowException] = useState(false);
  const detailRef = useRef<HTMLDivElement>(null);
  const revealException = () => {
    setSelectedIndex(run.commit_exceptions[0].request.phase);
    setShowException(true);
    requestAnimationFrame(() => {
      const summary = detailRef.current?.querySelector<HTMLElement>(".commit-exception > summary");
      summary?.focus({ preventScroll: true });
      summary?.scrollIntoView({ block: "center" });
    });
  };
  const selected = run.phases[selectedIndex];
  const categories = selected.categories as Record<string, number>;
  const exception = run.commit_exceptions.find((item) => item.request.phase === selected.index);
  const select = (index: number) => {
    setSelectedIndex(index); setShowException(false);
    if (window.matchMedia("(max-width: 1000px)").matches) {
      requestAnimationFrame(() => { detailRef.current?.focus({ preventScroll: true }); detailRef.current?.scrollIntoView({ block: "start" }); });
    }
  };
  return (
    <section className="load-explorer" aria-label="부하 구간과 응답 분류">
      <div className="load-explorer-heading">
        <div><span className="workspace-eyebrow">180초 · 정상 → 과부하 → 정상 복귀, 두 번</span><h3>구간별 응답 구성</h3></div>
        <button className="exception-jump" onClick={revealException}>
          저장 후 응답 실패 1건 <span aria-hidden="true">↘</span>
        </button>
      </div>
      <div className="load-workspace">
        <label className="mobile-phase-select">확인할 30초 구간
          <select aria-label="부하 구간 선택" value={selectedIndex} onChange={event => { setSelectedIndex(Number(event.target.value)); setShowException(false); }}>
            {run.phases.map(phase => <option value={phase.index} key={phase.index}>{phase.cycle}회 · {names[phase.name]} · {phase.start_seconds}–{phase.start_seconds + phase.duration_seconds}초</option>)}
          </select>
        </label>
        <div className="load-cohorts">
          <div className="cohort-column-head"><span>선택할 구간 / 투입 목표</span><span>응답 구성 · 각 행 100%</span></div>
          <div className="phase-chart" role="group" aria-label="저장된 부하 구간 선택">
            {run.phases.map((phase) => {
              const counts = phase.categories as Record<string, number>;
              return <button key={phase.index} data-testid="phase-select" aria-pressed={selectedIndex === phase.index}
                onClick={() => select(phase.index)} className={`phase-column phase-${phase.name}`}>
                <span className="cohort-name"><strong>{phase.cycle}회 · {names[phase.name]}</strong><small>{phase.start_seconds}–{phase.start_seconds + phase.duration_seconds}초 · 목표 {phase.target_rps} req/s</small></span>
                <span className="cohort-visual"><span className="phase-track" aria-hidden="true">
                  {kinds.filter((kind) => counts[kind.key] > 0).map((kind) => <i key={kind.key} className={`outcome-${kind.tone}`} style={{ width: `${counts[kind.key] / phase.attempted * 100}%` }} />)}
                </span><span className="cohort-fraction">유효 {n(phase.good)} / {n(phase.attempted)}건</span></span>
              </button>;
            })}
          </div>
          <p className="outcome-legend">{kinds.map((kind) => <span key={kind.key}><i className={`outcome-${kind.tone}`} />{kind.label}</span>)}</p>
          <p className="inspector-caption">막대는 요청 건수의 구성비입니다. 처리율의 높낮이를 나타내지 않습니다. 구간을 선택하면 오른쪽 또는 아래에 상세가 표시됩니다.</p>
        </div>
        <div className="phase-detail" ref={detailRef} tabIndex={-1} data-testid="phase-detail" aria-live="polite">
          <span className="workspace-eyebrow">선택한 30초 구간</span>
          <h4>{selected.cycle}회 · {names[selected.name]} <span>{selected.start_seconds}–{selected.start_seconds + selected.duration_seconds}초</span></h4>
          <div className="selected-throughput"><strong>{selected.cohort_rates_rps.good.toFixed(2)}<small> 유효 req/s</small></strong><span>투입 목표 {selected.target_rps} req/s</span></div>
          <p className="phase-judgment">{selected.name === "overload"
            ? "수용 제한과 시간 예산의 비용: 투입한 요청 모두를 유효하게 처리하지는 못했습니다. 아래에서 보류·거절·시간 초과를 함께 확인합니다."
            : selected.name === "recovery"
              ? "부하를 낮춘 뒤의 관측: 이 30초 구간은 모든 예정 요청이 시간 예산 안의 유효 응답으로 돌아왔습니다. 장기 안정성을 뜻하지 않습니다."
              : "정상 부하의 기준 구간: 목표 요청률에서 모든 예정 요청이 시간 예산 안의 유효 응답으로 돌아왔습니다."}</p>
          <p>예정 요청 <strong>{n(selected.attempted)}건</strong>의 결과</p>
          <dl className="outcome-breakdown" data-testid="outcome-breakdown">
            {kinds.map((kind) => <div key={kind.key} className={`outcome-row outcome-row-${kind.tone}`}>
              <dt><i className={`outcome-${kind.tone}`} /><span>{kind.label}<small>{kind.hint}</small></span></dt>
              <dd>{n(categories[kind.key] || 0)}<small>건 · {((categories[kind.key] || 0) / selected.attempted * 100).toFixed(1)}%</small></dd>
            </div>)}
          </dl>
          <dl className="phase-rates">
            <div><dt>실제 전송률</dt><dd>{selected.cohort_rates_rps.sent.toFixed(2)} req/s</dd></div>
            <div><dt>응답 완료 요청률</dt><dd>{selected.cohort_rates_rps.completed.toFixed(2)} req/s</dd></div>
            <div><dt>유효 응답률</dt><dd>{selected.cohort_rates_rps.good.toFixed(2)} req/s</dd></div>
          </dl>
          <details className="phase-measurements"><summary>지연 분포·대기열·집계 기준</summary>
            <dl className="phase-rates">
              <div><dt>전체 p50 / p95 / p99</dt><dd>{Object.values(selected.scheduled_latency_ms).map(v => v.toFixed(1)).join(" / ")} ms</dd></div>
              <div><dt>유효 응답 p50 / p95 / p99</dt><dd>{Object.values(selected.useful_scheduled_latency_ms).map(v => v.toFixed(1)).join(" / ")} ms</dd></div>
              <div><dt>모델 대기 최대</dt><dd>{selected.resources.peak_worker_queue}개</dd></div>
              <div><dt>부하 생성 지연 p99</dt><dd>{selected.generator_lag_ms.p99.toFixed(1)} ms</dd></div>
            </dl>
            <p>지연은 예정 도착 시각부터 측정했습니다. 응답률은 이 구간의 마지막 완료까지 {selected.cohort_observed_seconds.toFixed(3)}초를 분모로 계산합니다. 완료에는 보류·거절이 포함됩니다. 고정 30초 창의 요청률은 아래 원본 표에서 확인할 수 있습니다.</p>
          </details>
          {exception && <details className="commit-exception" data-testid="commit-exception" open={showException} onToggle={event => setShowException(event.currentTarget.open)}>
            <summary>504 한 건: 응답 실패와 저장 실패는 달랐습니다</summary>
            <p>2회 과부하 구간, 시작 +{exception.request.due_seconds.toFixed(3)}초에 예정된 요청입니다. HTTP 응답은 실패했지만 같은 세션·요청 키로 DB 기록이 확인됐습니다.</p>
            <dl className="exception-record">
              <div><dt>응답</dt><dd>HTTP {exception.request.http_status}<code>{exception.request.response.detail}</code></dd></div>
              <div><dt>DB 기록</dt><dd>{exception.sql_row.payload.status} / {exception.sql_row.payload.reason}<code>{exception.sql_row.payload.id}</code></dd></div>
              <div><dt>같은 요청 키</dt><dd><code>{exception.request.idempotency_key}</code></dd></div>
              <div><dt>DB의 trace ID</dt><dd><code>{exception.sql_row.payload.trace_id}</code></dd></div>
            </dl>
            <p>이 한 건의 재시도는 이 부하 실험에서 실행하지 않았습니다. 장애 복구 탭의 lightweight 모델 trace와도 다른 요청입니다.</p>
            <details><summary>수신 응답과 최종 SQL 행 원본</summary><pre>{JSON.stringify(exception, null, 2)}</pre></details>
          </details>}
        </div>
      </div>
    </section>
  );
}
