import { useSyncExternalStore } from "react";
import type { RecordStore } from "./recordStore";

export default function ServerRecords({ store }: { store: RecordStore }) {
  const s = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const a = s.attempt;
  const current = !s.writing && !s.busy && !s.error && s.checkedAttempt === s.attemptNumber;
  const match = a && s.rows?.find(row => row.receipt_id === a.receiptId && row.output === a.output && (!a.result || row.action_id === a.result.action_id));
  const outcome = s.writing ? "처리 응답 대기" : !a ? "" : a.result
    ? (a.result.replayed ? "기존 기록 반환" : "새 기록 저장")
    : a.rejected ? "이번 기록 요청 거절" : "처리 응답 미확인";
  const tone = s.writing ? "pending" : a?.rejected ? "blocked" : a?.result ? "saved" : "unknown";
  return <section className="server-records" data-testid="server-records" aria-label="서버 저장 기록" aria-busy={s.busy}>
    <div className="record-heading"><h3>저장된 작업</h3><button disabled={!s.session || s.busy || s.writing} onClick={() => void store.refresh()}>{s.busy ? "조회 중…" : "서버 기록 조회"}</button></div>
    {s.busy && <p role="status">서버에 저장된 내용을 확인 중입니다.</p>}
    {s.error && <p role="alert">현재 조회 실패 · {s.error}{s.rows !== null && " 아래는 마지막으로 확인한 기록입니다."}</p>}
    {a && <div className={`record-confirmation outcome-${tone}`} data-testid="record-confirmation" aria-live="polite">
      <span className="outcome-label">이번 요청의 처리 응답</span>
      <h4 data-testid="request-outcome">{outcome}</h4>
      <p>{s.writing ? "기록 요청 처리 중 · 아직 처리 응답을 받지 않았습니다." : a.result ? a.result.replayed ? (a.previousId === a.result.action_id ? "기록 요청 응답: 같은 요청 키·작업 ID의 기존 기록 반환 · 이번 요청으로 추가된 기록 0건" : "기록 요청 응답: 기존 기록 반환 · 이전 작업 ID와의 대조는 확인되지 않았습니다.") : "기록 요청 응답: 답변 기록 완료" : a.rejected ? `기록 요청 거절: ${a.reason}` : "기록 요청 응답 미확인 · 저장 실패를 뜻하지 않습니다. 같은 요청 키를 유지합니다."}</p>
      <p className="read-verdict" data-testid="read-verdict">{!current ? "이번 요청 이후의 저장 내역은 아직 확인되지 않았습니다." : match ? "이후 서버 조회: 요청한 답변 본문과 저장된 작업이 일치합니다." : a.rejected && !s.rows?.some(row => row.receipt_id === a.receiptId) ? "이후 서버 조회: 거절된 답변은 작업 기록에 없습니다." : "이후 서버 조회: 이 답변의 기록을 찾지 못했습니다. 같은 요청으로 재시도해 확인하세요."}</p>
      {current && match && !a.result && <p>저장된 답변은 확인했습니다. 같은 요청 재시도로 처리 응답을 확인하세요.</p>}
    </div>}
    {s.rows === null ? <p className="record-empty">{s.session ? "조회 전 · 저장된 기록 수는 아직 모릅니다." : "조회 전 · 작업을 시작하면 서버 기록을 확인합니다."}</p> : <div aria-live="polite">
      <p className="record-observed">{!current ? "마지막 확인 기록" : "서버 조회 결과"} · <time dateTime={s.observed}>{new Date(s.observed).toLocaleTimeString("ko-KR")}</time> · <strong data-testid="record-count">{s.rows.length}개 작업</strong></p>
      {s.rows.length === 0 ? <p className="record-empty-confirmed">확인한 작업 기록이 없습니다.</p> : <ul>{s.rows.map(row => <li key={row.action_id} data-action-id={row.action_id}>
        <span className="stored-answer-label">서버 조회로 확인한 답변</span>
        <p className="stored-answer" data-testid="stored-answer">{row.output}</p>
        <details><summary>기록 식별 정보</summary><span>작업 ID</span><code>{row.action_id}</code><span>답변 ID</span><code>{row.receipt_id}</code></details>
      </li>)}</ul>}
    </div>}
  </section>;
}
