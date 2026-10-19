import { useEffect, useRef, useState } from "react";
import { CaseApi } from "./caseApi";

export default function ServerRecords({ base, session, expectedId }: { base: string; session: string; expectedId?: string }) {
  const [rows, setRows] = useState<{ action_id: string; receipt_id: string; output: string }[] | null>(null);
  const [observed, setObserved] = useState("");
  const [queriedFor, setQueriedFor] = useState<string | undefined>(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const generation = useRef(0);
  useEffect(() => { generation.current++; pending.current = false; setRows(null); setQueriedFor(undefined); setObserved(""); setError(""); setBusy(false); return () => { generation.current++; }; }, [session, base]);
  async function inspect() {
    if (!session || pending.current) return;
    pending.current = true; setBusy(true); setError("");
    const token = generation.current;
    try {
      const result = await new CaseApi(base).actions(session);
      if (token !== generation.current) return;
      setRows(result); setQueriedFor(expectedId); setObserved(new Date().toLocaleTimeString("ko-KR"));
    } catch (e) { if (token === generation.current) setError(e instanceof Error ? e.message : "조회 실패"); }
    finally { if (token === generation.current) { pending.current = false; setBusy(false); } }
  }
  return <section className="server-records" data-testid="server-records" aria-label="서버 저장 기록">
    <div className="record-heading"><h3>서버 저장 기록</h3><button disabled={!session || busy} onClick={() => void inspect()}>{busy ? "조회 중…" : "서버 기록 조회"}</button></div>
    <p>현재 세션의 기록을 API에서 조회합니다. 조회는 새 작업을 만들지 않습니다.</p>
    {error && <p role="alert">{error} {rows && "아래는 마지막 조회 기록입니다."}</p>}
    {rows === null ? <p className="record-empty">{session ? "조회 전 · 화면의 실행 응답과 별도로 확인" : "작업을 시작하면 조회할 수 있습니다."}</p> : <div aria-live="polite">
      <p>{observed} 조회 · <strong>{rows.length}개 작업</strong>{expectedId && (queriedFor !== expectedId ? " · 이후 실행 결과가 바뀜 · 다시 조회 필요" : rows.some(row => row.action_id === expectedId) ? " · 실행 응답의 작업 ID와 일치" : " · 실행 응답의 작업 ID 없음")}</p>
      {rows.length === 0 ? <p>저장된 작업이 없습니다.</p> : <ul>{rows.map(row => <li key={row.action_id}><code>{row.action_id}</code><p>{row.output}</p></li>)}</ul>}
    </div>}
  </section>;
}
