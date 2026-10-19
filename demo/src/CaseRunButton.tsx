import { useEffect, useState, useSyncExternalStore } from "react";
import { LoaderCircle } from "lucide-react";
import type { CaseFlow } from "./caseFlow";

/** Automatic execution shares admission and state with the contextual next action. */
export default function CaseRunButton({
  flow,
  top = false,
}: {
  flow: CaseFlow;
  top?: boolean;
}) {
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const receipt = state.freshReceipt || state.oldReceipt;
  const expired =
    state.step === 4 &&
    state.canReprepare &&
    (!receipt || receipt.expires_at * 1000 <= now);
  return (
    <button
      className={top ? "case-run-top" : "case-run"}
      data-testid={top ? "case-run-top" : "case-run-all"}
      disabled={
        state.busy ||
        state.running ||
        expired ||
        state.sessionExpired ||
        state.step >= 6
      }
      onClick={() => void flow.runAll()}
    >
      {state.running ? (
        <LoaderCircle className="case-spin" size={15} />
      ) : (
        <span aria-hidden="true">▶</span>
      )}
      {state.step >= 6
        ? state.restored ? "완료 기록 복원 · 아래에서 결과 확인" : "실행 완료 · 아래에서 결과 확인"
        : state.running
          ? "실행 중"
          : state.step === 0
            ? "답변 불러오기"
            : state.step === 1 ? "원문 변경 후 기록 요청" : state.step === 3 ? "답변 갱신 후 기록" : state.step === 5 ? "같은 요청 재시도" : "이어서 실행"}
    </button>
  );
}
