import { CaseApiError, type CaseAction, type CaseApi } from "./caseApi";
import { RecordStore, type RecordAttempt } from "./recordStore";
import { EvidenceApiError } from "./evidenceApi";
import { parseCheckpoint, type CaseStorage } from "./caseStorage";
import type {
  EvidenceReceipt,
  EvidenceState,
  ReleaseReport,
} from "./evidenceApi";
export type CaseEvent = { label: string; at: string; data: unknown };
export type CaseSnapshot = {
  restored: boolean;
  storageWarning: string;
  step: number;
  canReprepare: boolean;
  busy: boolean;
  running: boolean;
  error: string;
  status: string;
  session: string;
  sessionExpired: boolean;
  state: EvidenceState | null;
  oldReceipt: EvidenceReceipt | null;
  freshReceipt: EvidenceReceipt | null;
  report: ReleaseReport | null;
  action: CaseAction | null;
  events: CaseEvent[];
};
const initial = (): CaseSnapshot => ({
  restored: false,
  storageWarning: "",
  step: 0,
  canReprepare: false,
  busy: false,
  running: false,
  error: "",
  status: "",
  session: "",
  sessionExpired: false,
  state: null,
  oldReceipt: null,
  freshReceipt: null,
  report: null,
  action: null,
  events: [],
});
const QUERY = "하루 이체 한도";
class Superseded extends Error {}
/** Every awaited response is fenced before another request or UI write. */
export class CaseFlow {
  readonly records: RecordStore;
  private value = initial();
  private generation = 0;
  private disposed = false;
  private listeners = new Set<() => void>();
  private actionKey: string = crypto.randomUUID();
  private oldActionKey: string = crypto.randomUUID();
  constructor(private api: CaseApi, private storage?: CaseStorage) {
    this.records = new RecordStore(session => this.api.actions(session));
    if (!storage) return;
    try {
      const raw = storage.read();
      if (!raw) return;
      const saved = parseCheckpoint(raw, api.base);
      this.records.reset(saved.snapshot.session);
      this.actionKey = saved.actionKey;
      this.oldActionKey = saved.oldActionKey;
      const interrupted = !saved.snapshot.sessionExpired && saved.snapshot.step < 6 &&
        (saved.snapshot.busy || saved.snapshot.running || !!saved.snapshot.error ||
          (saved.snapshot.step === 4 && !saved.snapshot.canReprepare && !saved.snapshot.action));
      this.value = { ...saved.snapshot, restored: true, storageWarning: "", busy: false, running: false,
        error: interrupted ? "" : saved.snapshot.error,
        status: interrupted ? "중단된 실행의 확인된 기록을 복원했습니다. 자동 재전송하지 않습니다. 이어서 실행하면 서버 상태부터 확인합니다." + (saved.snapshot.error ? ` 마지막 오류: ${saved.snapshot.error}` : "") : "이 탭에 저장된 실행 기록을 복원했습니다. 현재 서버 상태를 다시 조회한 결과는 아닙니다." };
    } catch {
      this.value.storageWarning = "저장된 기록을 읽을 수 없어 새 화면으로 열었습니다. 손상·구버전·다른 API의 기록은 복원하지 않습니다.";
      // Construction is read-only, including React StrictMode's double render.
      // Explicit reset clears invalid data; the next request overwrites it.
    }
  }
  getSnapshot = () => this.value;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private set(patch: Partial<CaseSnapshot>) {
    this.value = { ...this.value, ...patch };
    if (this.storage) {
      try {
        if (!this.value.session && !this.value.events.length && !this.value.busy) this.storage.clear();
        else {
          const raw = JSON.stringify({ version: 1, base: this.api.base, snapshot: this.value, actionKey: this.actionKey, oldActionKey: this.oldActionKey });
          if (raw.length > 1_000_000 || this.value.events.length > 512) throw new Error("checkpoint limit");
          this.storage.write(raw);
        }
      } catch {
        this.value = { ...this.value, storageWarning: "브라우저에 진행 상황을 저장하지 못했습니다. 새로고침하면 이번 진행 내용이 복원되지 않을 수 있습니다. 사건 기록 JSON을 내려받으세요." };
        try { this.storage.clear(); } catch { /* Keep the warning visible. */ }
      }
    }
    this.listeners.forEach((fn) => fn());
  }
  reset = () => {
    this.generation++;
    this.records.reset();
    this.actionKey = crypto.randomUUID();
    this.oldActionKey = crypto.randomUUID();
    this.set(initial());
  };
  reprepare = () => {
    if (
      this.disposed ||
      this.value.sessionExpired ||
      this.value.busy ||
      this.value.step !== 4 ||
      this.value.action ||
      !this.value.canReprepare
    )
      return;
    // Keep the original case evidence, but use a new draft for the next task.
    this.set({
      step: 3,
      freshReceipt: null,
      error: "",
      status: "현재 근거로 답변을 다시 준비하세요.",
    });
  };
  dispose = () => {
    this.disposed = true;
    this.generation++;
    this.records.suspend();
  };
  activate = () => {
    this.disposed = false;
  };
  resumeAfterNavigation = () => {
    this.activate();
    this.set({ busy: false, running: false, restored: true, error: "", status: "이전 실행 상태입니다. 계속하려면 같은 요청으로 서버 상태를 확인하세요." });
  };
  next = async () => {
    if (this.value.running) return;
    await this.advance();
  };
  runAll = async () => {
    if (
      this.value.busy ||
      this.value.running ||
      this.value.sessionExpired ||
      this.value.step >= 6 ||
      this.disposed
    )
      return;
    const generation = this.generation;
    this.set({ running: true });
    try {
      while (
        !this.disposed &&
        generation === this.generation &&
        this.value.step < 6
      ) {
        const before = this.value.step;
        await this.advance();
        if (this.value.error || this.value.step <= before || [1, 3, 5].includes(this.value.step)) break;
      }
    } finally {
      if (!this.disposed && generation === this.generation)
        this.set({ running: false });
    }
  };
  private advance = async () => {
    if (
      this.value.busy ||
      this.value.step >= 6 ||
      this.disposed ||
      this.value.sessionExpired
    )
      return;
    const generation = this.generation;
    const current = this.value;
    const check = () => {
      if (this.disposed || generation !== this.generation)
        throw new Superseded();
    };
    const take = async <T>(
      label: string,
      operation: () => Promise<T>,
    ): Promise<T> => {
      check();
      const result = await operation();
      check();
      this.set({
        events: [
          ...this.value.events,
          { label, at: new Date().toISOString(), data: result },
        ],
      });
      return result;
    };
    const writeReceipt = current.step === 2 ? current.oldReceipt : [4, 5].includes(current.step) ? current.freshReceipt : null;
    let attempt: RecordAttempt | null = writeReceipt ? { key: current.step === 2 ? this.oldActionKey : this.actionKey, receiptId: writeReceipt.id, output: writeReceipt.output, previousId: current.step === 5 ? current.action?.action_id : undefined } : null;
    if (attempt) this.records.begin(attempt);
    this.set({ busy: true, error: "", status: "" });
    try {
      if (current.restored && current.session) {
        // Read-only preflight. Do not replace historical state: replaying the
        // original event revision and idempotency keys must remain possible.
        await this.api.state(current.session);
        check();
        this.set({ restored: false });
      }
      if (current.step === 0) {
        const session = current.session ? { session_id: current.session } : await take("Python API 연결 · 세션 생성", () =>
          this.api.connect(),
        );
        this.records.reset(session.session_id);
        this.set({ session: session.session_id });
        await this.records.refresh();
        check();
        const state = await take("현재 원문 조회", () =>
          this.api.state(session.session_id),
        );
        const oldReceipt = await take("300만 원 답변 준비", () =>
          this.api.prepare(session.session_id, QUERY, "answer"),
        );
        this.set({
          session: session.session_id,
          state,
          oldReceipt,
          step: 1,
          status: "원문을 인용한 답변을 준비했습니다.",
        });
      } else if (current.step === 1) {
        const source = current.state!.sources.find(
          (item) => item.source_id === "transfer",
        );
        if (!source || !source.text.includes("300만"))
          throw new Error(
            "예상한 300만 원 원문이 없습니다. 새 사례를 시작하세요.",
          );
        await take("원문 변경 이벤트 적용", () =>
          this.api.event(
            current.session,
            source,
            source.text.replace("300만", "100만"),
          ),
        );
        const state = await take("변경된 원문 조회", () =>
          this.api.state(current.session),
        );
        this.set({
          state,
          step: 2,
          status:
            "원문은 바뀌었고, 준비된 답변은 이전 내용을 그대로 보존합니다.",
        });
      } else if (current.step === 2) {
        try {
          await take("이전 답변 실행 응답", () =>
            this.api.execute(
              current.session,
              current.oldReceipt!.id,
              this.oldActionKey,
            ),
          );
          throw new Error(
            "예상과 달리 이전 답변 실행이 허용되었습니다. 기록을 내려받아 확인하세요.",
          );
        } catch (error) {
          check();
          if (
            !(error instanceof CaseApiError) ||
            error.status !== 409 ||
            error.detail !== "source_changed"
          )
            throw error;
          if (attempt) { attempt = { ...attempt, rejected: true, reason: "답변이 인용한 안내가 변경되어 작업 기록에 추가하지 않았습니다." }; this.records.complete(attempt); }
          this.set({
            events: [
              ...this.value.events,
              {
                label: "이전 답변 실행 차단",
                at: new Date().toISOString(),
                data: { status: error.status, detail: error.detail, ...(error.traceId ? { trace_id: error.traceId } : {}) },
              },
            ],
            step: 3,
            status: "오래된 답변 차단 · 원문이 변경되어 기록하지 않았습니다.",
          });
        }
      } else if (current.step === 3) {
        const report = await take("정상 모델·인덱스 쌍 평가", () =>
          this.api.evaluate(current.session, "paired"),
        );
        if (!report.passed)
          throw new Error(
            "후보가 평가를 통과하지 못했습니다. 실행을 진행하지 않습니다.",
          );
        await take("검증한 후보 적용", () =>
          this.api.promote(current.session, report.id),
        );
        const freshReceipt = await take("100만 원 답변 다시 준비", () =>
          this.api.prepare(current.session, QUERY, "answer"),
        );
        const state = await take("새 배포 버전 조회", () =>
          this.api.state(current.session),
        );
        this.records.prepared();
        this.set({
          report,
          freshReceipt,
          state,
          step: 4,
          canReprepare: true,
          status: "평가를 통과한 버전에서 최신 답변을 준비했습니다.",
        });
      } else if (current.step === 4) {
        this.set({ canReprepare: false });
        const action = await take("최신 답변으로 내부 작업 기록", () =>
          this.api.execute(
            current.session,
            current.freshReceipt!.id,
            this.actionKey,
          ),
        );
        if (attempt) { attempt = { ...attempt, result: action }; this.records.complete(attempt); }
        this.set({
          action,
          step: 5,
          status: action.replayed
            ? "같은 작업 반환 · 응답을 확인하지 못한 요청의 기존 기록입니다."
            : "답변 작업 1건 기록 · 검증과 기록을 같은 트랜잭션에서 처리했습니다.",
        });
      } else {
        const action = await take("동일 키로 작업 재요청", () =>
          this.api.execute(
            current.session,
            current.freshReceipt!.id,
            this.actionKey,
          ),
        );
        if (!action.replayed || action.action_id !== current.action?.action_id)
          throw new Error(
            "동일 작업 재시도 응답이 일치하지 않습니다. 기록을 확인하세요.",
          );
        if (attempt) { attempt = { ...attempt, result: action }; this.records.complete(attempt); }
        this.set({
          action,
          step: 6,
          status:
            "같은 작업 반환 · 과거 기록과 같은 작업 ID이며 새 작업을 만들지 않았습니다.",
        });
      }
    } catch (error) {
      if (attempt && generation === this.generation && !this.disposed && error instanceof EvidenceApiError && [404, 409, 422, 429].includes(error.status)) {
        attempt = { ...attempt, rejected: true, reason: error.message };
      }
      if (
        !(error instanceof Superseded) &&
        generation === this.generation &&
        !this.disposed
      )
        this.set({
          sessionExpired:
            error instanceof EvidenceApiError &&
            error.status === 404 &&
            error.detail === "session_missing_or_expired",
          canReprepare:
            current.step === 4
              ? error instanceof CaseApiError &&
                error.status === 409 &&
                [
                  "source_changed",
                  "source_deleted",
                  "receipt_expired",
                  "release_changed",
                ].includes(error.detail)
              : this.value.canReprepare,
          error: error instanceof Error ? error.message : String(error),
          status: "",
        });
    } finally {
      if (generation === this.generation && !this.disposed) {
        if (attempt) { this.records.complete(attempt); await this.records.refresh(); }
        if (generation === this.generation && !this.disposed) this.set({ busy: false });
      }
    }
  };
}
