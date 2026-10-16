import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { CaseEvent } from "./caseFlow";
import { selectEvents, type EventFilter } from "./caseJournal";
import "./evidenceInspector.css";

export default function CaseJournal({ events }: { events: CaseEvent[] }) {
  const [filter, setFilter] = useState<EventFilter>("all");
  const rows = selectEvents(events, filter);
  return (
    <div className="case-journal" data-testid="case-journal">
      <div
        className="inspector-switch"
        role="group"
        aria-label="실행 로그 필터"
      >
        {(
          [
            ["all", "전체"],
            ["blocked", "실행 차단"],
            ["record", "기록·재시도"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
        <span>
          {rows.length} / {events.length}개
        </span>
      </div>
      <p className="inspector-caption">
        현재 실행의 API 응답입니다. 차단 이유와 작업 ID를 확인하고 원본 응답을
        펼쳐 볼 수 있습니다.
      </p>
      <ol data-testid="case-events">
        {rows.map(({ event, index, view }) => (
          <li key={`${index}-${event.at}`} data-outcome={view.kind}>
            <details>
              <summary>
                <span className="case-event-order">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="journal-description">
                  <strong>{event.label}</strong>
                  <small>{view.title}</small>
                </span>
                <time>
                  {new Date(event.at).toLocaleTimeString("ko-KR", {
                    hour12: false,
                  })}
                </time>
              <ChevronDown size={12} aria-hidden="true" />
              </summary>
              <pre aria-label={`${event.label} 원본 응답`}>
                {JSON.stringify(event.data, null, 2)}
              </pre>
            </details>
            {view.identity && (
              <div className="journal-identity">
                <span>{view.kind === "blocked" ? "차단 사유" : "작업 ID"}</span>
                <code>{view.identity}</code>
              </div>
            )}
          </li>
        ))}
      </ol>
      {!rows.length && (
        <p className="inspector-caption">
          이 조건에 해당하는 기록이 아직 없습니다. 실행을 진행하거나 전체 로그를
          확인하세요.
        </p>
      )}
    </div>
  );
}
