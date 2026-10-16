import { useState } from "react";
import data from "./safety-evidence.json";
import "./safetyComparison.css";

const labels: Record<string, string> = {
  trust_at_creation: "생성 당시 결과 신뢰",
  check_then_act: "검사 후 별도로 기록",
  atomic_guard: "검증과 기록을 한 트랜잭션으로",
};
const cases: Record<string, { title: string; note: string }> = {
  current: {
    title: "원문 변경 없음",
    note: "유효한 답변으로 새 작업이 기록되어야 합니다.",
  },
  cited_edit_before_check: {
    title: "검사 전에 원문 변경",
    note: "별도 검사도 이 시점의 변경은 발견합니다.",
  },
  cited_edit_after_check: {
    title: "검사 뒤, 기록 전에 원문 변경",
    note: "검사할 때는 유효했습니다. 그 결과만 믿고 기록하면 변경을 놓칩니다.",
  },
  unrelated_edit: {
    title: "인용하지 않은 문서만 변경",
    note: "카드 문서의 변경이 이체 한도 답변까지 막아서는 안 됩니다.",
  },
  deletion: {
    title: "인용한 문서 삭제",
    note: "답변이 남아 있어도 삭제된 근거로 새 작업을 만들 수 없습니다.",
  },
  ttl_expiry: {
    title: "기록 직전에 유효 시간 만료",
    note: "실험용 시계를 정확한 만료 경계로 이동했습니다. 공개 API에서 시간을 바꾸지는 않습니다.",
  },
  release_change: {
    title: "모델·인덱스 묶음 교체",
    note: "답변을 준비한 배포 버전과 현재 버전이 다릅니다.",
  },
  revision_aba: {
    title: "원문 변경 후 같은 내용으로 복원",
    note: "본문은 다시 같아졌지만 v1 → v2 → v3 이력은 남습니다. 내용만 비교하면 놓치는 경우입니다.",
  },
  duplicate_submission: {
    title: "같은 요청을 두 번 제출",
    note: "세 방식 모두 같은 키를 중복 제거합니다. 재시도는 같은 작업 ID를 반환해야 합니다.",
  },
};
const events: Record<string, string> = {
  prepare: "답변 준비",
  edit: "원문 수정",
  check_opportunity: "별도 검사 시점",
  submit: "기록 요청",
  unrelated: "다른 문서 수정",
  delete: "원문 삭제",
  expire: "만료 경계",
  release: "배포 교체",
  aba: "수정 후 복원",
  retry_same_key: "같은 키 재시도",
};
const workloadLabels: Record<string, { title: string; note: string }> = {
  same_key: {
    title: "같은 키로 동시에 요청",
    note: "회차마다 새 작업 1건, 나머지는 같은 작업의 재시도 응답이어야 합니다.",
  },
  unique_keys: {
    title: "서로 다른 키로 동시에 요청",
    note: "서로 다른 유효 요청입니다. 모든 요청이 각각 기록되어야 합니다.",
  },
  edit_after_check: {
    title: "검사와 기록 사이에 원문 변경",
    note: "모든 별도 검사를 마친 뒤 원문 변경을 커밋하고 기록 요청을 함께 풀었습니다. 오래된 신규 기록만 집계합니다.",
  },
  replay_after_edit: {
    title: "완료 후 원문이 바뀐 작업 재시도",
    note: "이미 완료된 과거 작업을 다시 조회하는 요청입니다. 기존 작업 반환은 새 실행이나 현재 유효성 보장이 아닙니다. 검사부터 하는 방식은 이 반환도 거절합니다.",
  },
  lock_timeout_retry: {
    title: "DB 잠금 시간 초과 후 같은 키로 재요청",
    note: "실제 SQL 잠금을 유지해 첫 요청을 시간 초과시켰습니다. 잠금을 해제한 뒤 오류가 난 요청만 같은 키로 한 번씩 재요청했습니다. 첫 오류와 복구를 분리해 보여줍니다.",
  },
};
const repo = "https://github.com/sokldjs554/recheck-ml-serving/blob/main/";

export default function SafetyComparison() {
  const [database, setDatabase] = useState("postgresql");
  const [scenario, setScenario] = useState("cited_edit_after_check");
  const [workload, setWorkload] = useState("edit_after_check");
  const db =
    data.databases.find((item) => item.database === database) ||
    data.databases[0];
  const selected = db.results.map((row) => ({
    strategy: row.strategy,
    case: row.cases.find((item) => item.case === scenario)!,
  }));
  const current = selected[0].case;
  const work = data.workloads.databases.find(
    (item) => item.database === db.database,
  );
  const params = data.workloads.parameters;
  function download() {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            measured_at: data.measured_at,
            database: db.database,
            database_version: db.database_version,
            scope: data.scope,
            results: selected,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `recheck-${db.database}-${scenario}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section
      className="safety-comparison"
      aria-label="같은 사건의 세 가지 처리 방식"
    >
      <div className="comparison-heading">
        <div>
          <p className="comparison-kicker" data-testid="comparison-scope">
            저장된 SQL 실행 기록 · {data.measured_at.slice(0, 10)}
          </p>
          <h2>동일 요청의 방식별 기록 결과</h2>
          <p>
            사건을 골라 세 방식의 결과를 비교하세요. 각 결과는 실제 DB 실행에서
            가져왔습니다.
          </p>
        </div>
        <label>
          데이터베이스
          <select
            aria-label="비교할 데이터베이스"
            value={db.database}
            onChange={(e) => setDatabase(e.target.value)}
          >
            {data.databases.map((item) => (
              <option key={item.database} value={item.database}>
                {item.database === "postgresql" ? "PostgreSQL" : "SQLite"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="comparison-section">
        <div className="comparison-controls">
          <label>
            01 · 사건 선택
            <select
              aria-label="비교할 사건"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            >
              {Object.entries(cases).map(([key, item]) => (
                <option key={key} value={key}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <button onClick={download}>
            선택한 사건 JSON <span aria-hidden="true">↓</span>
          </button>
        </div>
        <ol
          className="comparison-sequence"
          aria-label="실제로 적용한 사건 순서"
        >
          {current.schedule.map((event, index) => (
            <li key={`${index}-${event}`}>{events[event] || event}</li>
          ))}
        </ol>
        <div className="comparison-documents">
          <div data-testid="comparison-receipt">
            <span>
              답변이 인용한 원문 · v{current.state_at_submit.receipt_revision}
            </span>
            <p>{current.receipt.references[0].text}</p>
          </div>
          <div data-testid="comparison-source">
            <span>
              기록 요청 시 원문 · v{current.state_at_submit.source_revision}
            </span>
            <p>
              {current.state_at_submit.deleted
                ? "문서 삭제됨"
                : current.state_at_submit.source_text}
            </p>
          </div>
        </div>
        <p className="comparison-explanation">{cases[scenario].note}</p>
        <div className="comparison-table-wrap">
          <table
            className="comparison-case-table"
            data-testid="comparison-case-results"
          >
            <thead>
              <tr>
                <th>처리 방식</th>
                <th>별도 검사 응답</th>
                <th>기록 요청 결과</th>
                <th>DB에 남은 작업</th>
              </tr>
            </thead>
            <tbody>
              {selected.map((row) => (
                <tr
                  key={row.strategy}
                  className={
                    row.strategy === "atomic_guard" ? "comparison-guard" : ""
                  }
                >
                  <th scope="row">{labels[row.strategy]}</th>
                  <td data-label="별도 검사">
                    {row.case.separate_check
                      ? row.case.separate_check.valid
                        ? "당시 사용 가능"
                        : "당시 사용 불가"
                      : row.strategy === "atomic_guard"
                        ? "기록 트랜잭션 안에서 검사"
                        : "없음"}
                  </td>
                  <td data-label="요청 결과">
                    {row.case.attempts.map((attempt) => (
                      <div className="comparison-attempt" key={attempt.attempt}>
                        <strong
                          className={
                            attempt.stale_accepts ? "comparison-stale" : ""
                          }
                        >
                          {attempt.observed === "rejected"
                            ? "실행 거절"
                            : attempt.observed === "replayed"
                              ? "기존 작업 반환"
                              : attempt.stale_accepts
                                ? "오래된 근거로 기록"
                                : "새 작업 기록"}
                        </strong>
                        <small>
                          {attempt.error
                            ? `${attempt.error.status} · ${attempt.error.reason}`
                            : `작업 ${attempt.action_id?.slice(0, 8)}`}
                        </small>
                      </div>
                    ))}
                  </td>
                  <td data-label="남은 작업">
                    <strong>
                      {row.case.attempts.at(-1)?.persisted_action_count}건
                    </strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {work && (
        <>
          <div className="comparison-section">
            <div className="comparison-controls">
              <label>
                02 · 동시에 들어온 요청
                <select
                  aria-label="비교할 동시 요청"
                  value={workload}
                  onChange={(e) => setWorkload(e.target.value)}
                >
                  {Object.entries(workloadLabels).map(([key, item]) => (
                    <option key={key} value={key}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <span>
                {params.workers}개 동시 요청 × {params.rounds}회차 · 방식별{" "}
                {params.workers * params.rounds}회 요청
              </span>
            </div>
            <p
              data-testid="comparison-workload-note"
              className="comparison-explanation"
            >
              {workloadLabels[workload].note}
            </p>
            <div className="comparison-table-wrap">
              <table
                className="comparison-workload-table"
                data-testid="comparison-workload-results"
              >
                <thead>
                  <tr>
                    <th>처리 방식</th>
                    <th>신규 기록</th>
                    <th>그중 오래된 근거</th>
                    <th>중복 기록</th>
                    <th>기존 작업 반환</th>
                    <th>첫 거절 / DB 오류</th>
                    <th>오류 재요청 처리 / 시도</th>
                  </tr>
                </thead>
                <tbody>
                  {work.strategies.map((row) => {
                    const totals = row.workloads.find(
                      (item) => item.name === workload,
                    )!.totals;
                    return (
                      <tr
                        key={row.strategy}
                        className={
                          row.strategy === "atomic_guard"
                            ? "comparison-guard"
                            : ""
                        }
                      >
                        <th scope="row">{labels[row.strategy]}</th>
                        <td data-label="신규 기록">{totals.new_actions}</td>
                        <td
                          data-label="오래된 근거"
                          className={
                            totals.stale_commits ? "comparison-stale" : ""
                          }
                        >
                          {totals.stale_commits}
                        </td>
                        <td data-label="중복 기록">
                          {totals.duplicate_commits}
                        </td>
                        <td data-label="기존 작업 반환">{totals.replays}</td>
                        <td data-label="거절 / DB 오류">
                          {totals.rejections} / {totals.operational_errors}
                        </td>
                        <td data-label="오류 재요청 처리 / 시도">
                          {totals.recovered_requests} /{" "}
                          {totals.recovery_requests}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="comparison-footnote">
              회차마다 새 세션을 사용했습니다. 기존 작업 반환·거절·DB 오류는 첫
              요청의 응답 수입니다. 신규 기록은 복구 후까지 남은 SQL 기록
              수입니다. DB 오류만 같은 키로 한 번 재요청하며, 논리적인 검증
              거절은 재시도하지 않습니다. 모든 응답과 복구 전후 기록을 아래에서
              확인할 수 있습니다.
            </p>
            <details className="comparison-details">
              <summary>첫 회차의 요청과 SQL 기록 보기</summary>
              <pre>
                {JSON.stringify(
                  work.strategies.map((row) => ({
                    strategy: row.strategy,
                    ...row.workloads.find((item) => item.name === workload)!
                      .example,
                  })),
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
          <div className="comparison-section" data-testid="comparison-latency">
            <div className="comparison-controls">
              <h3>03 · 검증을 포함한 기록 비용</h3>
              <span>방식별 정상 요청 {params.samples}회 · 동시성 1</span>
            </div>
            <p className="comparison-explanation">
              준비된 답변으로 새 작업을 기록하는 구간만 측정했습니다. 별도 검사
              방식은 검사 시간도 포함합니다.
            </p>
            <div className="comparison-table-wrap">
              <table className="comparison-cost-table">
                <thead>
                  <tr>
                    <th>처리 방식</th>
                    <th>p50</th>
                    <th>p95</th>
                    <th>기록 성공 / 전체</th>
                  </tr>
                </thead>
                <tbody>
                  {work.strategies.map((row) => (
                    <tr
                      key={row.strategy}
                      className={
                        row.strategy === "atomic_guard"
                          ? "comparison-guard"
                          : ""
                      }
                    >
                      <th scope="row">{labels[row.strategy]}</th>
                      <td data-label="p50">
                        {row.latency.p50_ms.toFixed(2)} ms
                      </td>
                      <td data-label="p95">
                        {row.latency.p95_ms.toFixed(2)} ms
                      </td>
                      <td data-label="성공 / 전체">
                        {row.latency.commits} / {row.latency.requests}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="comparison-footnote">
              {params.warmups}회씩 예열 후 실행 순서를 회전했습니다.
              HTTP·검색·세션 준비·경쟁 재현용 대기는 제외했습니다. 실패 요청도
              표본에 포함합니다. 같은 개발 호스트에서의 짧은 측정으로, 작은
              차이를 일반적인 성능 우위로 해석하지 않습니다.
            </p>
          </div>
        </>
      )}
      <details className="comparison-details comparison-summary">
        <summary>고정 사건 9개의 전체 집계와 측정 범위</summary>
        <p>
          방식별 사건 9개 · 제출 10회입니다. 두 DB는 같은 사건을 반복한 것이며
          독립적인 표본 수로 합산하지 않습니다.
        </p>
        <div className="comparison-table-wrap">
          <table>
            <thead>
              <tr>
                <th>방식</th>
                <th>오래된 기록 / 기회</th>
                <th>정상 오거절 / 기회</th>
                <th>중복 기록 / 재시도</th>
              </tr>
            </thead>
            <tbody>
              {db.results.map((row) => (
                <tr key={row.strategy}>
                  <th>{labels[row.strategy]}</th>
                  <td>
                    {row.totals.stale_accepts} /{" "}
                    {row.totals.stale_opportunities}
                  </td>
                  <td>
                    {row.totals.false_rejects} /{" "}
                    {row.totals.valid_first_action_opportunities}
                  </td>
                  <td>
                    {row.totals.duplicate_commits} /{" "}
                    {row.totals.retry_opportunities}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>{db.database_version}</p>
        <p>
          동시 요청·비용 측정: {data.workloads.measured_at} · Python{" "}
          {data.workloads.environment.python}. 고정된 합성 사건과 내부 SQL
          작업만 다룹니다. 무작위 부하·실서비스 사고율·외부 송금·검색 품질의
          증거가 아닙니다.
        </p>
      </details>
      <div className="safety-links">
        <a
          href={repo + "docs/action-comparison-audit.md"}
          target="_blank"
          rel="noreferrer"
        >
          감사 결과와 이번 보강 ↗
        </a>
        <a
          href={repo + "docs/safety-case-study.md"}
          target="_blank"
          rel="noreferrer"
        >
          사건 조건 ↗
        </a>
        <a
          href={repo + "docs/evidence/action-workloads.json"}
          target="_blank"
          rel="noreferrer"
        >
          동시 요청·시간 원본 ↗
        </a>
        <a
          href={repo + "docs/action-contract.md"}
          target="_blank"
          rel="noreferrer"
        >
          보장 범위 ↗
        </a>
      </div>
    </section>
  );
}
