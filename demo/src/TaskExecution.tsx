import { useEffect, useRef, useState, type RefObject } from "react";
import { CaseApiError, CaseApi, type CaseAction } from "./caseApi";
import type { RecordStore, RecordAttempt } from "./recordStore";

/** One mounted receipt owns one request key, including ambiguous response failures. */
export default function TaskExecution({ base, session, receiptId, disabled, onBusyChange, onUnconfirmedChange, requestLock, records, output }: { base: string; session: string; receiptId: string; disabled: boolean; onBusyChange: (busy: boolean) => void; onUnconfirmedChange: (value: boolean) => void; requestLock: RefObject<boolean>; records: RecordStore; output: string }) {
  const key = useRef(crypto.randomUUID());
  const pending = useRef(false);
  const alive = useRef(true);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [action, setAction] = useState<CaseAction | null>(null);
  const [error, setError] = useState("");
  const [failure, setFailure] = useState<{status?: number; traceId?: string; detail: string} | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function execute() {
    if (pending.current || requestLock.current || disabled) return;
    pending.current = true; requestLock.current = true; setFailure(null); setBusy(true); onBusyChange(true); setAttempted(true); setError("");
    let attempt: RecordAttempt = { key: key.current, receiptId, output };
    records.begin(attempt);
    try {
      const result = await new CaseApi(base).execute(session, receiptId, key.current);
      if (alive.current) { setAction(result); onUnconfirmedChange(false); attempt = { ...attempt, result }; records.complete(attempt); }
    } catch (e) { if (alive.current) { attempt = { ...attempt, rejected: e instanceof CaseApiError && [409, 422, 429].includes(e.status), reason: e instanceof Error ? e.message : "응답 미확인" }; records.complete(attempt); onUnconfirmedChange(!(e instanceof CaseApiError && [404, 409, 422, 429].includes(e.status))); setError(e instanceof CaseApiError ? e.message : "응답을 확인하지 못했습니다. 저장 여부는 같은 요청 재시도나 서버 기록 조회로 확인하세요."); setFailure(e instanceof CaseApiError ? {status:e.status, traceId:e.traceId, detail:e.detail} : {detail:"응답 확인 실패 · 저장 여부는 같은 키 재시도나 서버 조회로 확인"}); } }
    finally { if (alive.current) await records.refresh(); pending.current = false; requestLock.current = false; if (alive.current) { setBusy(false); onBusyChange(false); } }
  }
  return <section className="task-execution" data-testid="custom-execution">
    <h3>기록 요청</h3>
    <button className="case-next" disabled={busy || disabled} onClick={() => void execute()}>{busy ? "기록 확인 중…" : attempted ? "같은 요청 재시도" : "이 답변으로 작업 기록"}</button>
    {error && <p role="alert">{error}</p>}
    {!action && <p>기록 완료 응답 없음{attempted && !error && !busy ? " · 서버 기록 조회로 확인" : ""}</p>}
    {action && <div className="task-result" role="status"><strong>{busy || error ? "마지막 성공 응답 · " : ""}{action.replayed ? "같은 작업 반환" : "새 작업 기록"}</strong><details><summary>작업 ID</summary><code>{action.action_id}</code></details><p>{action.replayed ? "같은 요청 키의 기존 작업을 반환했습니다. 아래 작업 기록과 대조할 수 있습니다." : "가상 데이터의 내부 작업입니다. 실제 송금·발송은 하지 않습니다."}</p></div>}
    {attempted && <details className="execution-detail"><summary>요청·응답 근거</summary><pre>{JSON.stringify({receipt_id:receiptId,idempotency_key:key.current,last_success:action,failure},null,2)}</pre></details>}
  </section>;
}
