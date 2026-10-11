import { describe, expect, it, vi } from "vitest";
import { CaseFlow } from "./caseFlow";
import { CaseApiError, type CaseApi } from "./caseApi";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function fixture() {
  const source = {
    source_id: "transfer",
    title: "이체 한도 안내",
    text: "하루 이체 한도는 300만 원입니다.",
    revision: 1,
    deleted: false,
  };
  const state = {
    sources: [source],
    active_release: { release_epoch: 1 },
    events: [],
  };
  const receipt = { id: "old", output: source.text, references: [source] };
  const api = {
    connect: vi.fn().mockResolvedValue({ session_id: "session" }),
    state: vi.fn().mockResolvedValue(state),
    prepare: vi.fn().mockResolvedValue(receipt),
    event: vi.fn().mockResolvedValue({
      source: {
        ...source,
        revision: 2,
        text: "하루 이체 한도는 100만 원입니다.",
      },
    }),
    evaluate: vi.fn(),
    promote: vi.fn(),
    execute: vi.fn(),
  };
  return { api, flow: new CaseFlow(api as unknown as CaseApi), receipt };
}

describe("guided case lifecycle", () => {
  it("discards an old session completion after reset, without preparing a draft", async () => {
    const { api, flow } = fixture();
    const pending = deferred<{ session_id: string }>();
    api.connect.mockReturnValue(pending.promise);
    const request = flow.next();
    flow.reset();
    pending.resolve({ session_id: "late" });
    await request;
    expect(flow.getSnapshot().step).toBe(0);
    expect(flow.getSnapshot().events).toEqual([]);
    expect(api.prepare).not.toHaveBeenCalled();
  });
  it("locks duplicate clicks and discards completions after unmount", async () => {
    const { api, flow } = fixture();
    const pending = deferred<{ session_id: string }>();
    api.connect.mockReturnValue(pending.promise);
    const request = flow.next();
    await flow.next();
    expect(api.connect).toHaveBeenCalledTimes(1);
    flow.dispose();
    pending.resolve({ session_id: "late" });
    await request;
    expect(api.prepare).not.toHaveBeenCalled();
  });
  it("clears the previous success when a request fails and leaves the same step retryable", async () => {
    const { api, flow } = fixture();
    await flow.next();
    expect(flow.getSnapshot().status).toContain("준비");
    api.event.mockRejectedValue(new Error("offline"));
    await flow.next();
    expect(flow.getSnapshot().step).toBe(1);
    expect(flow.getSnapshot().status).toBe("");
    expect(flow.getSnapshot().error).toContain("offline");
    expect(flow.getSnapshot().busy).toBe(false);
    api.event.mockResolvedValue({ applied: true });
    await flow.next();
    expect(flow.getSnapshot().step).toBe(2);
    expect(flow.getSnapshot().error).toBe("");
  });
  it("only treats source_changed HTTP 409 as the expected blocked result", async () => {
    const { api, flow } = fixture();
    await flow.next();
    await flow.next();
    api.execute.mockRejectedValue(new CaseApiError(503, "unavailable"));
    await flow.next();
    expect(flow.getSnapshot().step).toBe(2);
    expect(flow.getSnapshot().status).toBe("");
    api.execute.mockRejectedValue(new CaseApiError(409, "source_changed"));
    await flow.next();
    expect(flow.getSnapshot().step).toBe(3);
    expect(flow.getSnapshot().status).toContain("차단");
  });
  it("records a current task and retries its identical key as a historical action", async () => {
    const { api, flow } = fixture();
    await flow.next();
    await flow.next();
    api.execute.mockRejectedValueOnce(new CaseApiError(409, "source_changed"));
    await flow.next();
    api.evaluate.mockResolvedValue({ id: "report", passed: true });
    api.promote.mockResolvedValue({ release_epoch: 2 });
    api.prepare.mockResolvedValue({
      id: "fresh",
      output: "100만 원",
      references: [],
    });
    await flow.next();
    const action = {
      action_id: "action-1",
      receipt_id: "fresh",
      replayed: false,
    };
    api.execute
      .mockResolvedValueOnce(action)
      .mockResolvedValueOnce({ ...action, replayed: true });
    await flow.next();
    await flow.next();
    expect(api.execute.mock.calls[1]).toEqual(api.execute.mock.calls[2]);
    expect(flow.getSnapshot().action?.action_id).toBe("action-1");
    expect(flow.getSnapshot().step).toBe(6);
    expect(flow.getSnapshot().status).toContain("과거");
  });
  it("can reprepare a fresh draft without discarding the original blocked evidence", async () => {
    const { api, flow } = fixture();
    await flow.next();
    await flow.next();
    api.execute.mockRejectedValueOnce(new CaseApiError(409, "source_changed"));
    await flow.next();
    api.evaluate.mockResolvedValue({ id: "report", passed: true });
    api.promote.mockResolvedValue({ release_epoch: 2 });
    api.prepare.mockResolvedValue({
      id: "fresh",
      output: "100만 원",
      references: [],
    });
    await flow.next();
    flow.reprepare();
    expect(flow.getSnapshot().step).toBe(3);
    expect(flow.getSnapshot().freshReceipt).toBeNull();
    expect(flow.getSnapshot().oldReceipt?.id).toBe("old");
    expect(flow.getSnapshot().events.length).toBeGreaterThan(0);
    await flow.next();
    expect(flow.getSnapshot().step).toBe(4);
  });
  it("does not replace a draft after an ambiguous execution failure, preserving safe retry", async () => {
    const { api, flow } = fixture();
    await flow.next();
    await flow.next();
    api.execute.mockRejectedValueOnce(new CaseApiError(409, "source_changed"));
    await flow.next();
    api.evaluate.mockResolvedValue({ id: "report", passed: true });
    api.promote.mockResolvedValue({ release_epoch: 2 });
    api.prepare.mockResolvedValue({
      id: "fresh",
      output: "100만 원",
      references: [],
    });
    await flow.next();
    api.execute.mockRejectedValueOnce(new Error("response lost after commit"));
    await flow.next();
    flow.reprepare();
    expect(flow.getSnapshot().step).toBe(4);
    expect(flow.getSnapshot().freshReceipt?.id).toBe("fresh");
    api.execute.mockResolvedValueOnce({
      action_id: "same-task",
      receipt_id: "fresh",
      replayed: true,
    });
    await flow.next();
    expect(api.execute.mock.calls.at(-1)).toEqual(
      api.execute.mock.calls.at(-2),
    );
    expect(flow.getSnapshot().step).toBe(5);
  });
});
