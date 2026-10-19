import type { CaseAction, CaseApi } from "./caseApi";
export type RecordRow = Awaited<ReturnType<CaseApi["actions"]>>[number];
export type RecordAttempt = { key: string; receiptId: string; output: string; result?: CaseAction; rejected?: boolean; reason?: string; previousId?: string };
type Snapshot = { session: string; rows: RecordRow[] | null; observed: string; busy: boolean; writing: boolean; error: string; attempt: RecordAttempt | null; checkedAttempt: number; attemptNumber: number };
const empty = (session = ""): Snapshot => ({ session, rows: null, observed: "", busy: false, writing: false, error: "", attempt: null, checkedAttempt: -1, attemptNumber: 0 });
/** A workspace owns this store. GET data never comes from a POST or a count delta. */
export class RecordStore {
  private value = empty();
  private generation = 0;
  private query = 0;
  private listeners = new Set<() => void>();
  constructor(private read: (session: string) => Promise<RecordRow[]>) {}
  getSnapshot = () => this.value;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<Snapshot>) { this.value = { ...this.value, ...patch }; this.listeners.forEach(fn => fn()); }
  reset(session = "") { this.generation++; this.query++; this.value = empty(session); this.listeners.forEach(fn => fn()); }
  begin(attempt: RecordAttempt) {
    // A response to a GET started before this write must not confirm this attempt.
    this.query++;
    const previousId = this.value.attempt?.key === attempt.key ? this.value.attempt.result?.action_id || this.value.rows?.find(row => row.receipt_id === attempt.receiptId && row.output === attempt.output)?.action_id : undefined;
    this.set({ attempt: { ...attempt, previousId }, attemptNumber: this.value.attemptNumber + 1, writing: true, busy: false, error: "" });
  }
  complete(attempt: RecordAttempt) { this.set({ writing: false, attempt: { ...attempt, previousId: this.value.attempt?.previousId } }); }
  refresh = async () => {
    if (!this.value.session) return;
    const generation = this.generation, query = ++this.query;
    const { session, attemptNumber } = this.value;
    this.set({ busy: true, error: "" });
    try {
      const rows = await this.read(session);
      if (generation !== this.generation || query !== this.query) return;
      this.set({ rows, observed: new Date().toISOString(), checkedAttempt: attemptNumber });
    } catch (e) {
      if (generation === this.generation && query === this.query) this.set({ error: e instanceof Error ? e.message : "상담 기록을 조회하지 못했습니다." });
    } finally {
      if (generation === this.generation && query === this.query) this.set({ busy: false });
    }
  };
}
