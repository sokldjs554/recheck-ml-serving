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

it("preserves trace correlation on success and blocked responses without exposing it as result text", async () => {
  const api = new CaseApi("http://localhost");
  const trace = "1234567890abcdef1234567890abcdef";
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(valid), {status:200, headers:{"X-Recheck-Trace-Id":trace}}));
  expect(await api.execute("s", "receipt-1", "k")).toMatchObject({ trace_id: trace });
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({detail:"source_changed"}), {status:409, headers:{"X-Recheck-Trace-Id":trace}}));
  await expect(api.execute("s", "receipt-1", "k")).rejects.toMatchObject({traceId:trace, status:409, detail:"source_changed"});
});

it("reads server actions separately and rejects malformed successful lookups", async () => {
  const api = new CaseApi("http://localhost");
  const fetcher = vi.fn(async (_url: string) => new Response(JSON.stringify({actions:[valid]})));
  vi.stubGlobal("fetch", fetcher);
  expect(await api.actions("session/1")).toEqual([valid]);
  expect(fetcher.mock.calls[0][0]).toBe("http://localhost/api/sessions/session%2F1/evidence/actions");
  for (const body of [null, {}, {actions:[{action_id:"x"}]}]) {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify(body)));
    await expect(api.actions("session")).rejects.toThrow("서버 기록 응답 형식");
  }
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({detail:"session_missing_or_expired"}), {status:404}));
  await expect(api.actions("session")).rejects.toMatchObject({status:404, detail:"session_missing_or_expired"});
});
