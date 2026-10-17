import { describe, expect, it } from "vitest";
import { CaseFlow } from "./caseFlow";
import { CaseApiError, type CaseApi } from "./caseApi";
import { savedCaseBase } from "./caseStorage";

function harness() {
  let saved: string | null = null;
  const storage = { read: () => saved, write: (value: string) => { saved = value; }, clear: () => { saved = null; } };
  const source = { source_id: "transfer", title: "한도", text: "300만 원", revision: 1, deleted: false };
  const state = { sources: [source], active_release: { release_epoch: 1 }, events: [], receipts: [], reports: [] };
  let prepares = 0, connects = 0, checks = 0, expired = false;
  const keys: string[] = [];
  const rows = new Map<string, object>();
  let loseResponse = false;
  const api = {
    base: "http://api.test",
    connect: async () => { connects++; return { session_id: "session" }; },
    state: async () => { checks++; if (expired) throw new CaseApiError(404, "session_missing_or_expired"); return structuredClone(state); },
    prepare: async () => ({ id: ++prepares === 1 ? "old" : "fresh", output: source.text, references: [{ source_id: source.source_id, title: source.title, text: source.text, revision: source.revision }], expires_at: Date.now() / 1000 + 60 }),
    event: async () => { source.text = "100만 원"; source.revision = 2; return { applied: true }; },
    evaluate: async () => ({ id: "report", passed: true }),
    promote: async () => ({ release_epoch: 2 }),
    execute: async (_sid: string, rid: string, key: string) => {
      keys.push(key);
      if (rid === "old") throw new CaseApiError(409, "source_changed");
      const replayed = rows.has(key);
      if (!replayed) rows.set(key, { action_id: "one", receipt_id: rid, output: "100만 원", replayed: false });
      if (loseResponse) { loseResponse = false; throw new Error("response lost after commit"); }
      return { ...rows.get(key), replayed };
    },
  };
  const create = () => new CaseFlow(api as unknown as CaseApi, storage);
  return { storage, api, create, rows, keys, setExpired: () => { expired = true; }, loseNextResponse: () => { loseResponse = true; }, counts: () => ({ prepares, connects, checks }) };
}

describe("same-tab case checkpoints", () => {
  it("restores completed evidence without sending any request", async () => {
    const h = harness(), first = h.create(); await first.runAll();
    const before = first.getSnapshot(), counts = h.counts(); first.dispose();
    const restored = h.create();
    expect(restored.getSnapshot()).toMatchObject({ step: 6, session: before.session, action: before.action, events: before.events, restored: true, busy: false, running: false });
    expect(h.counts()).toEqual(counts);
    await restored.runAll(); expect(h.counts()).toEqual(counts);
  });
  it("preserves the same key after a committed response was lost across reload", async () => {
    const h = harness(), first = h.create();
    for (let i = 0; i < 4; i++) await first.next();
    h.loseNextResponse(); await first.next(); first.dispose();
    const restored = h.create();
    expect(restored.getSnapshot()).toMatchObject({ step: 4, canReprepare: false, action: null });
    await restored.runAll();
    expect(restored.getSnapshot()).toMatchObject({ step: 6, action: { action_id: "one", replayed: true } });
    expect(new Set(h.keys.slice(1)).size).toBe(1);
    expect(h.rows.size).toBe(1);
  });
  it("reload during a pending mutation pauses instead of automatically retrying", async () => {
    const h = harness(), first = h.create(); await first.next();
    let release!: () => void;
    h.api.event = () => new Promise(resolve => { release = () => resolve({ applied: true }); });
    const pending = first.next(); first.dispose();
    const restored = h.create();
    expect(restored.getSnapshot()).toMatchObject({ step: 1, restored: true, busy: false, running: false });
    expect(restored.getSnapshot().status).toContain("중단");
    release(); await pending;
    expect(restored.getSnapshot().step).toBe(1);
  });
  it("checks the server before continuing and preserves expired historical evidence", async () => {
    const h = harness(), first = h.create(); await first.next(); first.dispose(); h.setExpired();
    const restored = h.create(), events = restored.getSnapshot().events;
    await restored.runAll();
    expect(restored.getSnapshot()).toMatchObject({ step: 1, sessionExpired: true, events });
    expect(h.api.base).toBe("http://api.test");
    expect(h.keys).toEqual([]);
  });
  it("keeps a confirmed session if reload interrupts the initial preparation", async () => {
    const h = harness(); let release!: () => void;
    const original = h.api.state;
    h.api.state = () => new Promise(resolve => { release = async () => resolve(await original()); });
    const first = h.create(), pending = first.next();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    first.dispose(); const restored = h.create();
    expect(restored.getSnapshot().session).toBe("session");
    h.api.state = original; release(); await pending;
    await restored.next();
    expect(h.counts().connects).toBe(1);
    expect(restored.getSnapshot().step).toBe(1);
  });
  it("explicit reset removes the checkpoint and never restores the old action", async () => {
    const h = harness(), first = h.create(); await first.runAll(); first.reset();
    expect(h.storage.read()).toBeNull();
    expect(h.create().getSnapshot()).toMatchObject({ step: 0, events: [], session: "", action: null });
  });
  it("rejects damaged and structurally incomplete saved data", async () => {
    const h = harness();
    for (const raw of ["{broken", JSON.stringify({ version: 1, snapshot: { step: 6, session: "s" } })]) {
      h.storage.write(raw); const flow = h.create();
      expect(flow.getSnapshot()).toMatchObject({ step: 0, restored: false });
      expect(flow.getSnapshot().storageWarning.length).toBeGreaterThan(0);
    }
  });
  it("rejects a checkpoint belonging to another API server", async () => {
    const h = harness(); await h.create().next(); h.api.base = "http://other.test";
    expect(h.create().getSnapshot()).toMatchObject({ step: 0, session: "" });
  });
  it("restores a validated custom case endpoint independently of the default API", async () => {
    const h = harness(); await h.create().next();
    expect(savedCaseBase("http://default.test", h.storage)).toBe("http://api.test");
    h.storage.write('{"base":"javascript:alert(1)"}');
    expect(savedCaseBase("http://default.test", h.storage)).toBe("http://default.test");
  });
  it("storage denial does not crash the flow and visibly reports missing persistence", async () => {
    const h = harness(); const denied = { read: () => { throw new Error("denied"); }, write: () => { throw new Error("quota"); }, clear: () => {} };
    const flow = new CaseFlow(h.api as unknown as CaseApi, denied); await flow.next();
    expect(flow.getSnapshot()).toMatchObject({ step: 1, busy: false });
    expect(flow.getSnapshot().storageWarning.length).toBeGreaterThan(0);
  });
});
