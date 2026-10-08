import type {
  Adapter,
  DecisionInput,
  Mutation,
  Receipt,
  Session,
  Validation,
  Versions,
} from "./types";
const uuid = () => globalThis.crypto.randomUUID();
const same = (a: Versions, b: Versions) =>
  a.feature_version === b.feature_version &&
  a.policy_version === b.policy_version &&
  a.model_version === b.model_version;
type State = {
  versions: Versions;
  receipts: Receipt[];
  pending: Map<string, { body: string; promise: Promise<Receipt> }>;
};
/** Local educational rule, not an ML model or backend measurement. */
export class Simulation implements Adapter {
  private sessions = new Map<string, State>();
  async createSession(): Promise<Session> {
    const session_id = uuid();
    const versions = {
      feature_version: 1,
      policy_version: 1,
      model_version: "risk-v1",
    };
    this.sessions.set(session_id, {
      versions,
      receipts: [],
      pending: new Map(),
    });
    return { session_id, ...versions };
  }
  private state(id: string) {
    const state = this.sessions.get(id);
    if (!state)
      throw new Error("세션을 찾을 수 없습니다. 새 세션을 시작하세요.");
    return state;
  }
  async mutate(id: string, kind: Mutation): Promise<Versions> {
    const s = this.state(id);
    if (kind === "feature") s.versions.feature_version++;
    if (kind === "policy") s.versions.policy_version++;
    if (kind === "model")
      s.versions.model_version = `risk-v${Number(s.versions.model_version.split("v")[1]) + 1}`;
    return { ...s.versions };
  }
  async receipts(id: string) {
    return [...this.state(id).receipts];
  }
  async decide(id: string, body: DecisionInput): Promise<Receipt> {
    const s = this.state(id);
    const key = JSON.stringify(body);
    const existing = s.pending.get(body.idempotency_key);
    if (existing) {
      if (existing.body !== key)
        throw new Error("409 · 같은 멱등 키의 요청 내용이 달라졌습니다.");
      return existing.promise;
    }
    if (s.pending.size > 50)
      throw new Error(
        "브라우저 데모 요청 상한에 도달했습니다. 새 세션을 시작하세요.",
      );
    const snapshot = { ...s.versions };
    const start = Date.now();
    const promise = (async () => {
      const delay =
        body.fault === "unavailable"
          ? 0
          : body.fault === "timeout"
            ? 300
            : Math.min(body.delay_ms, 300);
      if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay));
      const stale = !same(snapshot, s.versions);
      const failed = body.fault !== "none" || body.delay_ms > 300;
      const score = failed
        ? null
        : Math.min(
            0.95,
            0.07 +
              body.amount / 10000000 +
              ((snapshot.feature_version - 1) % 3) * 0.16,
          );
      const status = failed
        ? "review"
        : stale && body.protected
          ? "invalidated"
          : score! >= 0.5
            ? "review"
            : "clear";
      const reason =
        body.fault === "unavailable"
          ? "model_unavailable"
          : failed
            ? "deadline_exceeded"
            : stale && body.protected
              ? "versions_changed"
              : score! >= 0.5
                ? "risk_threshold"
                : "no_risk_signal";
      const latency = Math.max(0, Date.now() - start);
      const created = new Date();
      const receipt: Receipt = {
        id: uuid(),
        session_id: id,
        ...snapshot,
        status,
        reason,
        risk_score: score,
        created_at: created.toISOString(),
        expires_at: new Date(created.getTime() + 20000).toISOString(),
        latency_ms: latency,
        trace_id: uuid().replaceAll("-", ""),
        model_hash: "browser-rule-v1 (not ML)",
        protected: body.protected,
        spans: [
          { name: "snapshot.read", start_ms: 0, duration_ms: 0, status: "ok" },
          {
            name: "simulation.wait",
            start_ms: 0,
            duration_ms: latency,
            status: failed ? "error" : "ok",
          },
          {
            name: body.protected ? "versions.recheck" : "recheck.skipped",
            start_ms: latency,
            duration_ms: 0,
            status: stale && body.protected ? "error" : "ok",
          },
          {
            name: "receipt.create",
            start_ms: latency,
            duration_ms: 0,
            status: "ok",
          },
        ],
      };
      s.receipts.unshift(receipt);
      s.receipts = s.receipts.slice(0, 30);
      return receipt;
    })();
    s.pending.set(body.idempotency_key, { body: key, promise });
    return promise;
  }
  async validate(id: string, receiptId: string): Promise<Validation> {
    const s = this.state(id);
    const receipt = s.receipts.find((r) => r.id === receiptId);
    if (!receipt) throw new Error("판단 기록을 찾을 수 없습니다.");
    const reason =
      receipt.status !== "clear"
        ? receipt.reason
        : !same(receipt, s.versions)
          ? "versions_changed"
          : Date.now() >= Date.parse(receipt.expires_at)
            ? "receipt_expired"
            : "valid";
    return {
      valid: reason === "valid",
      reason,
      current_versions: { ...s.versions },
    };
  }
}
