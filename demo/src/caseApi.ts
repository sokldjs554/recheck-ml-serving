import { EvidenceApi, EvidenceApiError, type Source } from "./evidenceApi";
export type CaseAction = {
  action_id: string;
  receipt_id: string;
  output: string;
  committed_at: number;
  release_epoch: number;
  references: Source[];
  scope: string;
  replayed: boolean;
};
export class CaseApiError extends EvidenceApiError {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(status, detail);
    this.name = "CaseApiError";
  }
}
export class CaseApi extends EvidenceApi {
  async execute(
    sid: string,
    receiptId: string,
    key: string,
  ): Promise<CaseAction> {
    const response = await fetch(
      `${this.base}/api/sessions/${encodeURIComponent(sid)}/evidence/receipts/${encodeURIComponent(receiptId)}/execute`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: key }),
        signal: AbortSignal.timeout(15000),
      },
    );
    if (!response.ok) {
      let detail = "요청을 완료하지 못했습니다. 다시 시도하세요.";
      try {
        const data = await response.json();
        if (typeof data.detail === "string") detail = data.detail;
      } catch {
        /* non-JSON gateway response */
      }
      throw new CaseApiError(response.status, detail);
    }
    const invalid = () =>
      new Error(
        "서버 응답 형식이나 답변 ID가 올바르지 않아 완료로 표시하지 않습니다. 같은 요청으로 다시 시도하세요.",
      );
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw invalid();
    }
    if (!data || typeof data !== "object") throw invalid();
    const item = data as Record<string, unknown>;
    const text = (v: unknown) => typeof v === "string" && v.trim().length > 0;
    const positiveInteger = (v: unknown) =>
      typeof v === "number" && Number.isSafeInteger(v) && v > 0;
    if (
      !text(item.action_id) ||
      item.receipt_id !== receiptId ||
      !text(item.output) ||
      typeof item.committed_at !== "number" ||
      !Number.isFinite(item.committed_at) ||
      item.committed_at <= 0 ||
      !positiveInteger(item.release_epoch) ||
      typeof item.replayed !== "boolean" ||
      item.scope !==
        "atomic local synthetic support task recording; no external action" ||
      !Array.isArray(item.references) ||
      !item.references.length ||
      !item.references.every(
        (ref) =>
          ref &&
          typeof ref === "object" &&
          text(ref.source_id) &&
          text(ref.title) &&
          text(ref.text) &&
          positiveInteger(ref.revision),
      )
    )
      throw invalid();
    return data as CaseAction;
  }
}
