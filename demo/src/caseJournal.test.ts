import { describe, expect, it } from "vitest";
import { describeEvent, selectEvents } from "./caseJournal";
const event = (data: unknown) => ({
  label: "실제 응답",
  at: "2026-10-17T00:00:00Z",
  data,
});
describe("case evidence inspection", () => {
  it("distinguishes a blocked write from recording and replaying the same action", () => {
    const blocked = event({ status: 409, detail: "source_changed" });
    const recorded = event({
      action_id: "same-id",
      receipt_id: "draft",
      output: "100만 원",
      replayed: false,
    });
    const replayed = event({ ...(recorded.data as object), replayed: true });
    expect(describeEvent(blocked).kind).toBe("blocked");
    expect(describeEvent(recorded)).toMatchObject({
      kind: "record",
      identity: "same-id",
      title: "새 작업 기록",
    });
    expect(describeEvent(replayed)).toMatchObject({
      kind: "record",
      identity: "same-id",
      title: "기존 작업 반환",
    });
    const rows = [event({ sources: [] }), blocked, recorded, replayed];
    expect(selectEvents(rows, "blocked").map((r) => r.index)).toEqual([1]);
    expect(selectEvents(rows, "record").map((r) => r.index)).toEqual([2, 3]);
    expect(selectEvents(rows, "all")).toHaveLength(4);
    expect(rows).toHaveLength(4);
  });
  it("does not call an unrelated or malformed response a recorded action", () => {
    for (const data of [
      null,
      [],
      { id: "receipt" },
      { action_id: "", replayed: false },
      { action_id: "a" },
    ]) {
      expect(describeEvent(event(data)).kind).toBe("other");
    }
  });
});
