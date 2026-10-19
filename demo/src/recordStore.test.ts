import { describe, it, expect, vi } from "vitest";
import { RecordStore, type RecordRow } from "./recordStore";
const row = { action_id: "a", receipt_id: "r", output: "실제 답변" };
const deferred = () => { let resolve!: (rows: RecordRow[]) => void; const promise = new Promise<RecordRow[]>(r => { resolve = r; }); return { promise, resolve }; };
describe("GET-confirmed consultation records", () => {
  it("distinguishes not queried, confirmed empty and retained snapshot after query failure", async () => {
    const read = vi.fn().mockResolvedValueOnce([]).mockResolvedValueOnce([row]).mockRejectedValueOnce(new Error("offline"));
    const store = new RecordStore(read); store.reset("s");
    expect(store.getSnapshot().rows).toBeNull();
    await store.refresh(); expect(store.getSnapshot().rows).toEqual([]);
    await store.refresh(); const observed = store.getSnapshot().observed;
    await store.refresh(); expect(store.getSnapshot()).toMatchObject({ rows: [row], observed, error: "offline" });
  });
  it("a repeated same-key / same-ID attempt still requires a new GET", async () => {
    const read = vi.fn().mockResolvedValue([row]); const store = new RecordStore(read); store.reset("s");
    const attempt = { key: "same", receiptId: "r", output: row.output };
    store.begin(attempt); await store.refresh(); expect(store.getSnapshot().checkedAttempt).toBe(1);
    store.begin(attempt); expect(store.getSnapshot().checkedAttempt).not.toBe(store.getSnapshot().attemptNumber);
    await store.refresh(); expect(read).toHaveBeenCalledTimes(2); expect(store.getSnapshot().checkedAttempt).toBe(2);
  });
  it("ignores a late GET from another session and an earlier query from before a write", async () => {
    const old = deferred(), earlier = deferred();
    const read = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(earlier.promise).mockResolvedValueOnce([row]);
    const store = new RecordStore(read); store.reset("old"); const p1 = store.refresh();
    store.reset("new"); const p2 = store.refresh(); store.begin({ key: "k", receiptId: "r", output: row.output }); await store.refresh();
    old.resolve([]); earlier.resolve([]); await Promise.all([p1,p2]);
    expect(store.getSnapshot()).toMatchObject({ session: "new", rows: [row], checkedAttempt: 1, busy: false });
  });
  it("never populates the list from the write response; a lost response can be reconciled by GET", async () => {
    const store = new RecordStore(async () => [row]); store.reset("s"); store.begin({ key: "kept", receiptId: "r", output: row.output });
    expect(store.getSnapshot().rows).toBeNull(); await store.refresh();
    expect(store.getSnapshot().attempt?.result).toBeUndefined(); expect(store.getSnapshot().rows).toEqual([row]);
  });
});
