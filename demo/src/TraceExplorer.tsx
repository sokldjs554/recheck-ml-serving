import { useState } from "react";
import data from "./serving-evidence.json";
import "./evidenceInspector.css";

const explanations: Record<string, string> = {
  decision:
    "요청의 애플리케이션 처리 구간입니다. HTTP 전체 왕복 시간과는 다릅니다.",
  snapshot:
    "추론에 사용할 상태와 버전을 읽는 구간입니다. 순수 SQL 실행 시간으로 분리 측정하지 않았습니다.",
  "model.http":
    "API에서 모델 서버를 호출한 구간입니다. 하위 worker span과 시간이 겹치므로 합산하지 않습니다.",
  "model.infer":
    "별도 모델 프로세스에서 처리한 구간입니다. 실패 요청에서는 503 예외를 남기고 예측 실행 전 종료했습니다.",
  "model.predict": "복구 요청에서 실제 예측을 실행한 구간입니다.",
  "fence.commit":
    "버전 확인과 기록 준비 구간입니다. ORM flush/commit 전에 끝나므로 SQL 커밋 시간이 아닙니다. 저장 성공은 아래 독립 SQL 조회로 확인합니다.",
};

export default function TraceExplorer() {
  const [which, setWhich] = useState<"failed" | "recovered">("failed");
  const [selectedName, setSelectedName] = useState("model.infer");
  const record = data.failure[which];
  const spans = data.failure.trace_views[which];
  const selected = spans.find((span) => span.name === selectedName) || spans[0];
  const total = Math.max(
    ...spans.map((span) => span.start_ms + span.duration_ms),
  );
  const sqlMatches =
    JSON.stringify(record.receipt) === JSON.stringify(record.sql_row.payload);
  return (
    <section
      className="trace-explorer"
      data-testid="trace-explorer"
      aria-label="저장된 실패와 복구 추적 탐색"
    >
      <div className="inspector-heading">
        <h3>요청 한 건의 내부 흐름</h3>
        <span>저장된 OTLP · 로컬 실험</span>
      </div>
      <div
        className="inspector-switch"
        role="group"
        aria-label="저장된 추적 선택"
      >
        <button
          data-testid="trace-failed"
          aria-pressed={which === "failed"}
          onClick={() => setWhich("failed")}
        >
          모델 실패
        </button>
        <button
          data-testid="trace-recovered"
          aria-pressed={which === "recovered"}
          onClick={() => setWhich("recovered")}
        >
          오류 해제 후
        </button>
        <span>
          HTTP {record.http_status} · {record.receipt.status}
        </span>
      </div>
      <p className="inspector-caption">
        단계를 선택하면 서비스·예외·부모 span을 확인할 수 있습니다. 겹치는
        구간의 시간을 합산하지 않습니다.
      </p>
      <code className="trace-identity">trace {record.receipt.trace_id}</code>
      <div className="trace-workspace">
        <div
          className="trace-waterfall"
          role="group"
          aria-label="실제 수집 span"
        >
          <div className="trace-scale">
            <span>요청 시작 +0ms</span>
            <span>+{total.toFixed(2)}ms</span>
          </div>
          {spans.map((span) => (
            <button
              key={span.span_id}
              data-span-name={span.name}
              aria-pressed={selected.span_id === span.span_id}
              className={`trace-row ${span.status_code === 2 ? "trace-error" : ""}`}
              onClick={() => setSelectedName(span.name)}
            >
              <span
                className="trace-row-label"
                style={{ paddingInlineStart: `${span.depth * 10}px` }}
              >
                <strong>{span.name}</strong>
                <small>
                  {span.service} ·{" "}
                  {span.status_code === 2 ? "오류" : "오류 표시 없음"}
                </small>
              </span>
              <span className="trace-track" aria-hidden="true">
                <i
                  style={{
                    left: `${(span.start_ms / total) * 100}%`,
                    width: `${(span.duration_ms / total) * 100}%`,
                  }}
                />
              </span>
              <span className="trace-duration">
                {span.duration_ms.toFixed(2)} ms
              </span>
            </button>
          ))}
        </div>
        <div
          className="span-detail"
          data-testid="span-detail"
          aria-live="polite"
        >
          <span>{selected.service}</span>
          <h4>{selected.name}</h4>
          <p>{explanations[selected.name]}</p>
          <dl>
            <div>
              <dt>시작 / 소요</dt>
              <dd>
                +{selected.start_ms.toFixed(3)} /{" "}
                {selected.duration_ms.toFixed(3)} ms
              </dd>
            </div>
            <div>
              <dt>span ID</dt>
              <dd>
                <code>{selected.span_id}</code>
              </dd>
            </div>
            <div>
              <dt>부모 span</dt>
              <dd>
                <code>{selected.parent_span_id || "최상위"}</code>
              </dd>
            </div>
          </dl>
          {selected.status_message && (
            <p className="span-exception">{selected.status_message}</p>
          )}
          {selected.events.map((event, i) => (
            <details key={i}>
              <summary>{event.name} 원본</summary>
              <pre>{JSON.stringify(event.attributes, null, 2)}</pre>
            </details>
          ))}
        </div>
      </div>
      <div className="trace-reconciliation">
        <strong>
          응답 ↔ 독립 SQL 조회: {sqlMatches ? "같은 기록 확인" : "불일치"}
        </strong>
        <code>{record.receipt.id}</code>
        <span>
          {record.receipt.status} / {record.receipt.reason}
        </span>
      </div>
      <details className="inspector-raw">
        <summary>이 요청의 API 로그와 SQL 원본</summary>
        <pre>{record.structured_log.join("\n")}</pre>
        <pre>{JSON.stringify(record.sql_row, null, 2)}</pre>
      </details>
      <p className="inspector-caption">
        네이티브 SQL span은 없습니다. 두 요청의 상대 시간축이며 공개 서버의
        실시간 추적이 아닙니다.{" "}
        <a
          href="https://github.com/sokldjs554/recheck-ml-serving/blob/main/docs/evidence/failure-trace-proof.json"
          target="_blank"
          rel="noreferrer"
        >
          원본 근거 ↗
        </a>
      </p>
    </section>
  );
}
