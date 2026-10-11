import { afterEach, describe, expect, it, vi } from "vitest";
import { CaseApi } from "./caseApi";
const valid = {
  action_id: "task-1",
  receipt_id: "receipt-1",
  output: "현재 문서",
  committed_at: 1800000000,
  release_epoch: 2,
  references: [
    { source_id: "transfer", title: "안내", text: "현재 문서", revision: 2 },
  ],
  scope: "atomic local synthetic support task recording; no external action",
  replayed: false,
};
afterEach(() => vi.unstubAllGlobals());
describe("execute response boundary", () => {
  it.each([
    {},
    { ...valid, receipt_id: "another-receipt" },
    { ...valid, action_id: "" },
    { ...valid, replayed: "false" },
    { ...valid, committed_at: null },
    { ...valid, references: [] },
  ])(
    "does not turn malformed or mismatched success into a recorded action",
    async (body) => {
      vi.stubGlobal(
        "fetch",
        async () => new Response(JSON.stringify(body), { status: 200 }),
      );
      await expect(
        new CaseApi("http://localhost").execute("session", "receipt-1", "key"),
      ).rejects.toThrow("응답");
    },
  );
  it("accepts valid original and historical actions", async () => {
    vi.stubGlobal(
      "fetch",
      async () => new Response(JSON.stringify(valid), { status: 200 }),
    );
    expect(
      await new CaseApi("http://localhost").execute(
        "session",
        "receipt-1",
        "key",
      ),
    ).toEqual(valid);
  });
});
