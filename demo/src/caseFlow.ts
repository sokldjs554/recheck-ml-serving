import { CaseApiError, type CaseAction, type CaseApi } from "./caseApi";
import type {
  EvidenceReceipt,
  EvidenceState,
  ReleaseReport,
} from "./evidenceApi";
export type CaseEvent = { label: string; at: string; data: unknown };
export type CaseSnapshot = {
  step: number;
  canReprepare: boolean;
  busy: boolean;
  running: boolean;
  error: string;
  status: string;
  session: string;
  state: EvidenceState | null;
  oldReceipt: EvidenceReceipt | null;
  freshReceipt: EvidenceReceipt | null;
  report: ReleaseReport | null;
  action: CaseAction | null;
  events: CaseEvent[];
};
const initial = (): CaseSnapshot => ({
  step: 0,
  canReprepare: false,
  busy: false,
  running: false,
  error: "",
  status: "",
  session: "",
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
  private value = initial();
  private generation = 0;
  private disposed = false;
  private listeners = new Set<() => void>();
  private actionKey = crypto.randomUUID();
  private oldActionKey = crypto.randomUUID();
  constructor(private api: CaseApi) {}
  getSnapshot = () => this.value;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private set(patch: Partial<CaseSnapshot>) {
    this.value = { ...this.value, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  reset = () => {
    this.generation++;
    this.actionKey = crypto.randomUUID();
    this.oldActionKey = crypto.randomUUID();
    this.set(initial());
  };
  reprepare = () => {
    if (
      this.disposed ||
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
  };
  activate = () => {
    this.disposed = false;
  };
  next = async () => {
    if (this.value.running) return;
    await this.advance();
  };
  runAll = async () => {
    if (
      this.value.busy ||
      this.value.running ||
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
        if (this.value.error || this.value.step <= before) break;
      }
    } finally {
      if (!this.disposed && generation === this.generation)
        this.set({ running: false });
    }
  };
  private advance = async () => {
    if (this.value.busy || this.value.step >= 6 || this.disposed) return;
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
    this.set({ busy: true, error: "", status: "" });
    try {
      if (current.step === 0) {
        const session = await take("Python API 연결 · 세션 생성", () =>
          this.api.connect(),
        );
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
          this.set({
            events: [
              ...this.value.events,
              {
                label: "이전 답변 실행 차단",
                at: new Date().toISOString(),
                data: { status: error.status, detail: error.detail },
              },
            ],
            step: 3,
            status: "실행 차단 · HTTP 409 / source_changed",
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
        const action = await take("최신 답변으로 로컬 상담 작업 기록", () =>
          this.api.execute(
            current.session,
            current.freshReceipt!.id,
            this.actionKey,
          ),
        );
        this.set({
          action,
          step: 5,
          status: action.replayed
            ? "과거 작업 반환 · 응답을 확인하지 못한 요청의 기존 기록입니다."
            : "상담 작업 1건 기록 · 검증과 기록을 같은 트랜잭션에서 처리했습니다.",
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
        this.set({
          action,
          step: 6,
          status:
            "과거 작업 반환 · 같은 작업 ID이며 새 작업을 만들지 않았습니다.",
        });
      }
    } catch (error) {
      if (
        !(error instanceof Superseded) &&
        generation === this.generation &&
        !this.disposed
      )
        this.set({
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
      if (generation === this.generation && !this.disposed)
        this.set({ busy: false });
    }
  };
}
