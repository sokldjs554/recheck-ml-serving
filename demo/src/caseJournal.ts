import type { CaseEvent } from "./caseFlow";
export type EventFilter = "all" | "blocked" | "record";
export function describeEvent(event: CaseEvent): {
  kind: "blocked" | "record" | "other";
  title: string;
  identity: string;
} {
  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data))
    return { kind: "other", title: "응답 확인", identity: "" };
  const row = data as Record<string, unknown>;
  if (row.status === 409 && row.detail === "source_changed")
    return {
      kind: "blocked",
      title: "기록 차단",
      identity: "409 / source_changed",
    };
  if (
    typeof row.action_id === "string" &&
    row.action_id.length > 0 &&
    typeof row.replayed === "boolean"
  )
    return {
      kind: "record",
      title: row.replayed ? "기존 작업 반환" : "새 작업 기록",
      identity: row.action_id,
    };
  return { kind: "other", title: "응답 확인", identity: "" };
}
export function selectEvents(events: CaseEvent[], filter: EventFilter) {
  return events
    .map((event, index) => ({ event, index, view: describeEvent(event) }))
    .filter((row) => filter === "all" || row.view.kind === filter);
}
