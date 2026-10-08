import { describe, it, expect, vi } from "vitest";
import { Simulation } from "./simulation";
const body = {
  amount: 150000,
  recipient: "demo-recipient",
  idempotency_key: "key",
  delay_ms: 50,
  fault: "none" as const,
  protected: true,
};
describe("simulation receipt lifecycle", () => {
  it("invalidates inference if features change before completion", async () => {
    vi.useFakeTimers();
    const api = new Simulation();
    const session = await api.createSession();
    const pending = api.decide(session.session_id, body);
    await api.mutate(session.session_id, "feature");
    await vi.advanceTimersByTimeAsync(60);
    const receipt = await pending;
    expect(receipt.status).toBe("invalidated");
    expect((await api.validate(session.session_id, receipt.id)).valid).toBe(
      false,
    );
    vi.useRealTimers();
  });
  it("does not share feature state between sessions", async () => {
    const api = new Simulation();
    const a = await api.createSession();
    const b = await api.createSession();
    await api.mutate(a.session_id, "feature");
    const receipt = await api.decide(b.session_id, { ...body, delay_ms: 0 });
    expect(receipt.feature_version).toBe(1);
    expect((await api.validate(b.session_id, receipt.id)).valid).toBe(true);
  });
  it("revalidates a receipt after policy mutation", async () => {
    const api = new Simulation();
    const a = await api.createSession();
    const receipt = await api.decide(a.session_id, { ...body, delay_ms: 0 });
    await api.mutate(a.session_id, "policy");
    expect((await api.validate(a.session_id, receipt.id)).valid).toBe(false);
  });
  it("shows the deliberate stale baseline counterexample but rejects use", async () => {
    vi.useFakeTimers();
    const api = new Simulation();
    const a = await api.createSession();
    const pending = api.decide(a.session_id, { ...body, protected: false });
    await api.mutate(a.session_id, "feature");
    await vi.advanceTimersByTimeAsync(60);
    const receipt = await pending;
    expect(receipt.status).toBe("clear");
    expect((await api.validate(a.session_id, receipt.id)).valid).toBe(false);
    vi.useRealTimers();
  });
  it("advances model versions monotonically within one session", async () => {
    const api = new Simulation();
    const a = await api.createSession();
    await api.mutate(a.session_id, "model");
    const next = await api.mutate(a.session_id, "model");
    expect(next.model_version).toBe("risk-v3");
  });
  it("expires receipts and returns review for unavailable models", async () => {
    vi.useFakeTimers();
    const api = new Simulation();
    const a = await api.createSession();
    const receipt = await api.decide(a.session_id, { ...body, delay_ms: 0 });
    await vi.advanceTimersByTimeAsync(20001);
    expect((await api.validate(a.session_id, receipt.id)).valid).toBe(false);
    expect(
      (
        await api.decide(a.session_id, {
          ...body,
          idempotency_key: "failure",
          delay_ms: 0,
          fault: "unavailable",
        })
      ).status,
    ).toBe("review");
    vi.useRealTimers();
  });
});
