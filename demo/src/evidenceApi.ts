import { LiveApi } from "./api";
export type Source = {
  source_id: string;
  title: string;
  text: string;
  revision: number;
  deleted: boolean;
};
export type EvidenceReceipt = {
  id: string;
  product: "answer" | "checklist";
  query: string;
  output: string;
  references: Source[];
  release_epoch: number;
  artifact_hash: string;
  created_at: number;
  expires_at: number;
  retrieval_ms: number;
};
export type UseResult = {
  valid: boolean;
  reason: string;
  affected_sources: string[];
  checked_at: number;
  receipt_id: string;
};
export type Candidate = "paired" | "mismatch" | "regressed";
export type ReleaseReport = {
  id: string;
  candidate: Candidate;
  passed: boolean;
  failed_gates: string[];
  recall_at_1: number;
  baseline_recall_at_1: number;
  p95_ms: number;
  sample_count: number;
  model_index_match: boolean;
  artifact_hash: string;
  corpus_hash: string;
  base_release_epoch: number;
  model_hash: string;
  index_model_hash: string;
  samples: {
    query: string;
    expected_source: string;
    actual_source: string | null;
    latency_ms: number;
  }[];
  scope: string;
};
export type EvidenceState = {
  corpus_hash: string;
  sources: Source[];
  index_stale: boolean;
  active_release: {
    release_epoch: number;
    artifact_hash: string;
    model_hash: string;
    index_model_hash: string;
    corpus_hash: string;
  };
  receipts: EvidenceReceipt[];
  reports: ReleaseReport[];
  events: {
    source_id: string;
    revision: number;
    operation: string;
    at: number;
  }[];
};
const errors: Record<string, string> = {
  index_stale_rebuild_required:
    "문서가 바뀌었습니다. 아래에서 정상 후보를 평가·적용한 뒤 새 답변을 준비하세요.",
  evidence_changed_during_prepare:
    "검색 중 근거가 바뀌어 결과를 저장하지 않았습니다. 최신 인덱스를 적용하고 다시 시도하세요.",
  release_report_stale:
    "평가 이후 문서나 배포 버전이 바뀌었습니다. 후보를 다시 평가하세요.",
  evaluation_snapshot_changed:
    "평가 도중 문서나 배포 버전이 바뀌었습니다. 다시 평가하세요.",
  release_gate_failed:
    "품질 또는 버전 검증을 통과하지 못해 배포가 차단되었습니다.",
  no_matching_evidence:
    "일치하는 근거를 찾지 못했습니다. 문서에 있는 단어로 질문해 주세요.",
  session_missing_or_expired:
    "실험 세션이 만료되었거나 서버가 재시작되었습니다. 새 실험을 시작하세요.",
  evidence_receipt_capacity:
    "이 세션의 기록이 가득 찼습니다. 새 실험을 시작하세요.",
  release_report_capacity:
    "이 세션의 평가 기록이 가득 찼습니다. 새 실험을 시작하세요.",
  out_of_order_event: "현재 문서보다 이전 버전의 이벤트라 반영하지 않았습니다.",
  conflicting_event_revision:
    "같은 버전에 다른 내용이 들어왔습니다. 새 실험에서 다시 확인하세요.",
};
export class EvidenceApi {
  readonly base: string;
  constructor(base: string) {
    this.base = new LiveApi(base).base;
  }
  async connect() {
    const api = new LiveApi(this.base);
    await api.health();
    return api.createSession();
  }
  createSession() {
    return new LiveApi(this.base).createSession();
  }
  async request<T>(sid: string, path = "", body?: unknown): Promise<T> {
    const response = await fetch(
      `${this.base}/api/sessions/${encodeURIComponent(sid)}/evidence${path}`,
      {
        method: body === undefined ? "GET" : "POST",
        headers:
          body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(15000),
      },
    );
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail;
      } catch {
        /* non-JSON proxy failure */
      }
      throw new Error(
        errors[detail] ||
          `API ${response.status} · 요청을 완료하지 못했습니다. 다시 시도해 주세요.`,
      );
    }
    return response.json() as Promise<T>;
  }
  state(sid: string) {
    return this.request<EvidenceState>(sid);
  }
  prepare(sid: string, query: string, product: "answer" | "checklist") {
    return this.request<EvidenceReceipt>(sid, "/prepare", {
      query,
      product,
      idempotency_key: crypto.randomUUID(),
    });
  }
  validate(sid: string, id: string) {
    return this.request<UseResult>(
      sid,
      `/receipts/${encodeURIComponent(id)}/use`,
      {},
    );
  }
  event(sid: string, source: Source, text: string, deleted = false) {
    return this.request(sid, "/events", {
      source_id: source.source_id,
      revision: source.revision + 1,
      text,
      deleted,
    });
  }
  evaluate(sid: string, candidate: Candidate) {
    return this.request<ReleaseReport>(sid, "/releases/evaluate", {
      candidate,
    });
  }
  promote(sid: string, id: string) {
    return this.request(sid, `/releases/${encodeURIComponent(id)}/promote`, {});
  }
}
