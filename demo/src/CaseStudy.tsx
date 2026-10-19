import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  Download,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import { CaseApi } from "./caseApi";
import type { CaseFlow } from "./caseFlow";
import "./caseStudy.css";
import CaseJournal from "./CaseJournal";
import ServerRecords from "./ServerRecords";

const actions = [
  "답변 불러오기",
  "안내 문서 변경",
  "이 답변으로 기록 요청",
  "변경된 안내로 답변 갱신",
  "새 답변으로 기록 요청",
  "같은 요청 재시도",
];
const working = [
  "문서 검색 · 답변 준비",
  "정책 원문 변경",
  "이전 답변 실행 검증",
  "모델·인덱스 평가와 답변 갱신",
  "상담 작업 기록",
  "동일 요청 재시도",
];
const descriptions = [
  "문서를 검색해 300만 원을 인용한 답변을 준비합니다.",
  "답변은 그대로 둔 채, 정책 원문의 한도를 100만 원으로 바꿉니다.",
  "바뀌기 전 답변으로 상담 기록을 남겨 봅니다.",
  "변경된 근거로 모델·인덱스를 평가하고 답변을 다시 준비합니다.",
  "인용 문서와 유효기간을 확인한 뒤 상담 기록을 저장합니다.",
  "같은 키로 다시 요청해 중복 작업이 생기는지 확인합니다.",
  "실행 응답과 동일 키 재시도의 작업 ID가 일치합니다.",
];
function short(value?: string) {
  return value ? value.slice(0, 8) : "—";
}

export default function CaseStudy({
  flow,
  configuredBase,
  onConfigure,
  onExplore,
  onEvidence,
}: {
  flow: CaseFlow;
  configuredBase: string;
  onConfigure: (base: string) => void;
  onExplore: () => void;
  onEvidence: () => void;
}) {
  const [base, setBase] = useState(configuredBase);
  const [configError, setConfigError] = useState("");
  const [now, setNow] = useState(Date.now());
  const outcomeRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot);
  const source = state.state?.sources.find(
    (item) => item.source_id === "transfer",
  );
  const receipt = state.freshReceipt || state.oldReceipt;
  const secondsLeft = receipt
    ? Math.max(0, Math.ceil((receipt.expires_at * 1000 - now) / 1000))
    : 0;
  const mismatched = !!(
    source &&
    receipt &&
    source.revision !== receipt.references[0]?.revision
  );
  const blocked = state.events.some(
    (event) => event.label === "이전 답변 실행 차단",
  );
  const locked = state.busy || state.running;
  const expired = state.step === 4 && state.canReprepare && secondsLeft === 0;
  const reset = () => {
    flow.reset();
    setConfigError("");
  };
  const configure = () => {
    try {
      new CaseApi(base);
      flow.reset();
      onConfigure(base);
      setConfigError("");
    } catch (error) {
      setConfigError(error instanceof Error ? error.message : String(error));
    }
  };
  const download = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            scope:
              "Actual API responses from a synthetic local support-task case; no external message or transfer",
            api: configuredBase || window.location.origin,
            session_id: state.session,
            snapshot: state,
            events: state.events,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `recheck-case-${short(state.session)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const phases = [
    "답변 준비",
    "원문 변경",
    "실행 차단",
    "답변 갱신",
    "작업 기록",
    "재시도",
  ];
  const gate = state.action
    ? "recorded"
    : blocked && !state.freshReceipt
      ? "blocked"
      : mismatched
        ? "changed"
        : "waiting";

  const transport = (
    <div className="replay-transport">
      <details className="case-progress-detail"><summary>처리 단계 · {state.step}/6</summary>
      <ol className="replay-timeline" aria-label="사례 실행 진행 상황">
        {phases.map((label, i) => (
          <li
            key={label}
            className={`${i < state.step ? "is-done" : ""} ${i === state.step ? "is-current" : ""}`}
            aria-current={i === state.step ? "step" : undefined}
          >
            <span>{String(i + 1).padStart(2, "0")}</span>
            <span>{label}</span>
            <i />
          </li>
        ))}
      </ol></details>
      <div className="replay-controls">
        <div className="replay-now">
          <span>
            {state.step === 6
              ? "완료"
              : `${state.step + 1}/6`}
          </span>
          <p>{descriptions[state.step]}</p>
        </div>
        <div className="replay-buttons">
          <button
            data-testid="case-next"
            className="case-next"
            disabled={locked || expired || state.sessionExpired}
            onClick={state.step < 6 ? () => void flow.next() : () => {
              const detail = outcomeRef.current?.querySelector("details");
              if (detail) detail.open = true;
              outcomeRef.current?.scrollIntoView({ block: "start" });
              outcomeRef.current?.focus({ preventScroll: true });
            }}
          >
            {state.busy && !state.running ? (
              <LoaderCircle className="case-spin" size={14} />
            ) : null}
            {state.step >= 6
              ? "이번 실행 결과"
              : state.error
                ? "이 단계 다시 시도"
                : actions[state.step]}
            <ArrowRight size={14} />
          </button>
          {state.step >= 6 && (
            <button className="case-run" onClick={download}>
              <Download size={15} />
              실행 기록 저장
            </button>
          )}
        </div>
      </div>
      <div
        className={`case-result ${!state.error && !state.busy ? state.status ? "is-announcement" : "is-empty" : ""}`}
        data-testid="case-status"
        role={state.error ? "alert" : "status"}
        aria-live="polite"
      >
        {state.error ? (
          <>
            <strong>{state.sessionExpired ? "세션 만료" : "응답 확인 필요"}</strong>
            <span>{state.error}</span>
            <span>
              {state.sessionExpired
                ? "기존 결과와 로그는 보존했습니다. ‘처음부터’로 새 세션을 시작하세요."
                : "이 단계에서 다시 시도할 수 있습니다."}
            </span>
          </>
        ) : state.busy ? (
          <>
            <LoaderCircle className="case-spin" size={14} />
            <span>
              {state.step === 0
                ? "서버 연결·문서 검색 중입니다. 첫 연결 응답은 최대 90초 동안 기다립니다. 저장된 시연도 볼 수 있습니다."
                : `${working[state.step]} 중…`}
            </span>
          </>
        ) : (
          <span>{state.status}</span>
        )}
      </div>
      {state.step === 4 && state.freshReceipt && (
        <div className="case-expiry">
          <span>
            {!state.canReprepare
              ? "같은 요청을 다시 보내 기록 여부를 확인하세요."
              : secondsLeft > 0
                ? `답변 유효기간 ${secondsLeft}초 남음`
                : "유효기간이 지났습니다. 답변을 다시 준비하세요."}
          </span>
          <button
            disabled={locked || !state.canReprepare || state.sessionExpired}
            onClick={flow.reprepare}
          >
            새 답변 다시 준비
          </button>
        </div>
      )}
    </div>
  );

  return (
    <section
      className="case-study"
      data-testid="case-study"
      data-step={state.step}
      aria-label="근거에서 실행까지 실제 API 사례"
    >
      <div className="replay-heading">
        <span className="case-route-label">
          {state.restored ? "이전 실행 기록" : "대표 흐름"}
          <small>{state.restored ? "브라우저 저장본" : "실시간 API · 가상 문서의 내부 작업 기록"}</small>
        </span>
        <div className="replay-heading-tools">
          <span
            className={`case-connection ${state.session ? "is-connected" : ""}`}
          >
            <i />
            {state.sessionExpired
              ? "세션 만료 · 과거 기록"
              : state.restored
                ? "저장 기록 복원 · 서버 확인 전"
              : state.session
                ? "API 연결됨"
                : locked ? "API 연결 중" : "API 연결 전"}
          </span>
          <button
            className="case-quiet"
            data-testid="case-reset"
            onClick={reset}
            aria-label="사례 처음부터"
          >
            <RotateCcw size={15} />
            처음부터
          </button>
        </div>
      </div>

      {state.storageWarning && <p className="case-persistence-note" role="status" data-testid="case-storage-warning">{state.storageWarning}</p>}
      {state.restored && (
        <div className="case-persistence-note" data-testid="case-restored">
          <strong>이전 실행 기록</strong>
          <p>새로고침 전 이 탭에 저장된 기록입니다. 복원만으로 새 요청을 보내거나 현재 서버 상태를 다시 확인하지 않습니다.</p>
          <p>{state.sessionExpired
            ? "만료된 세션의 과거 기록입니다. ‘처음부터’로 새 실행을 시작하세요."
            : state.step >= 6
              ? "아래의 저장된 차단 결과와 작업 ID를 확인하세요."
              : expired
                ? "‘새 답변 다시 준비’로 답변을 갱신한 뒤 계속하세요."
                : "상단 실행 버튼으로 서버 상태를 확인하고 계속하세요."}</p>
        </div>
      )}
      <div className={`replay-machine gate-${gate}`}>
        <div className="replay-canvas">
          <aside className="replay-source" data-testid="case-source">
            <div className="replay-node-label">
              <span>현재 안내 문서</span>
              <span>{source ? `문서 v${source.revision}` : "불러오기 전"}</span>
            </div>
            <h2>현재 안내</h2>
            <p className="source-example">{source?.title || "안내 문서 불러오기 전"}</p>
            <span hidden data-testid="case-policy-value">{source?.text || "—"}</span>
            <details className="replay-source-text" open><summary>원문 보기</summary>
              {source ? (
                <>
                  <p>
                    {source.text}
                  </p>
                  <span className="replay-index-status">
                    {state.state?.index_stale
                      ? "인덱스 갱신 대기"
                      : "원문 · 인덱스 일치"}
                  </span>
                </>
              ) : (
                <p>
                  상담 답변이 인용할 안내 문서입니다.
                </p>
              )}
            </details>
          </aside>

          <div className="replay-work">
          <div className="replay-answer">
            <div className="replay-query">
              <span>검색 질문</span>
              <p>“하루 이체 한도가 얼마인가요?”</p>
            </div>
            <article
              className={`case-draft ${mismatched ? "is-outdated" : ""}`}
              data-testid="case-draft"
            >
              <div className="replay-ticket-heading">
                <h2>상담 답변</h2>
                <span>
                  {receipt
                    ? `인용 v${receipt.references[0]?.revision}`
                    : "아직 준비되지 않음"}
                </span>
              </div>
              {receipt ? (
                <>
                  <p className="case-answer-text">
                    {receipt.output}
                  </p>
                  <div
                    className={`replay-draft-status ${mismatched ? "is-warning" : ""}`}
                  >
                    {mismatched
                      ? blocked
                        ? "인용한 안내 문서가 바뀌어 기록하지 않았습니다."
                        : "원문이 바뀌었습니다. 이 답변은 그대로입니다."
                      : state.action
                        ? "이 답변으로 작업을 기록했습니다."
                        : "기록 전에 인용 문서가 바뀌었는지 확인합니다."}
                  </div>
                  <div className="replay-ticket-foot">
                    <span>
                      {state.freshReceipt ? "갱신한 답변" : "최초 답변"}
                    </span>
                    <code>{short(receipt.id)}</code>
                  </div>
                </>
              ) : (
                <>
                  <div className="replay-empty-draft">
                    <span className="replay-placeholder-line" />
                    <span className="replay-placeholder-line" />
                    <p>
                      안내 문서를 불러오면 답변이 여기에 표시됩니다.
                    </p>
                  </div>
                  <div className="replay-ticket-foot">
                    <span>준비 → 변경 → 실행</span>
                    <code>대기 중</code>
                  </div>
                </>
              )}
            </article>
            {state.freshReceipt && state.oldReceipt && (
              <details className="case-superseded" data-testid="case-old-draft" open>
                <summary>
                  <span>상담 기록에 추가되지 않은 답변</span>
                  <ChevronDown size={13} />
                </summary>
                <p>
                  {state.oldReceipt.output}
                </p>
                <small>
                  인용한 안내가 변경되어 기록 요청이 거절됐습니다.
                </small>
              </details>
            )}
          </div>

          {transport}
          <ServerRecords store={flow.records} />
          </div>
        </div>
      </div>

      {(blocked || state.action) && (
        <section
          className="case-outcomes case-outcome-summary"
          data-testid="case-outcomes"
          ref={outcomeRef}
          tabIndex={-1}
          aria-labelledby="case-outcome-title"
        >
          <details><summary id="case-outcome-title">{state.restored ? "이전 실행 결과" : "이번 실행 결과"}</summary>
          <p className="case-outcome-explanation">
            {blocked
              ? "이전 답변은 인용 문서가 변경되어 상담 기록에 추가되지 않았습니다."
              : "서버가 반환한 상담 기록입니다. 이전 답변의 차단 여부는 실행 로그를 확인하세요."}
          </p>
          <dl>
            <div>
              <dt>변경 전 답변</dt>
              <dd className={blocked ? "is-blocked" : "is-pending"}>{blocked ? "오래된 답변 차단" : "확인 전"}</dd>
              <dd className="case-outcome-detail">{blocked ? "인용 문서 변경으로 기록 거절" : "차단 응답 확인 전"}</dd>
            </div>
            <div>
              <dt>변경 후 답변</dt>
              <dd className={state.action ? "" : "is-pending"}>{state.action ? "새 답변 기록 완료" : "기록 확인 전"}</dd>
              <dd className="case-outcome-detail">{state.action ? "현재 문서를 확인한 뒤 기록" : "성공 응답을 받아야 기록 완료로 표시"}</dd>
            </div>
            <div>
              <dt>같은 요청 재시도</dt>
              <dd className={state.step === 6 ? "" : "is-pending"}>{state.step === 6 ? "동일 작업 반환" : "확인 전"}</dd>
              <dd className="case-outcome-detail">{state.step === 6 ? "새 기록을 추가하지 않고 기존 작업 ID 반환" : "재시도 전후 작업 ID 비교 대기"}</dd>
            </div>
          </dl>
          {state.action && (
            <div className="case-action-receipt" data-testid="case-action">
              <span>상담 기록의 작업 ID</span>
              <code>{state.action.action_id}</code>
              <small>{state.action.replayed ? "동일 작업 · 과거 기록" : "기록됨"}</small>
            </div>
          )}
          </details>
        </section>
      )}




      <div className="replay-below">
        <details className="replay-audit"><summary>요청별 응답 · {state.events.length}건</summary>
          <div className="case-audit-heading">
            <div>
              <h2>실행 로그</h2>
              <span>{String(state.events.length).padStart(2, "0")}</span>
            </div>
            <button
              className="case-download"
              disabled={locked || !state.events.length}
              onClick={download}
            >
              <Download size={14} />
              사건 기록 JSON
            </button>
          </div>
          <div className="case-trail" aria-label="실제 API 응답 기록">
            {state.events.length > 0 ? (
              <CaseJournal events={state.events} restored={state.restored} />
            ) : (
              <div className="replay-empty-log">
                <span>—</span>
                <p>
                  아직 요청을 보내지 않았습니다.
                  <br />
                  <span>각 요청의 서버 응답이 여기에 남습니다.</span>
                </p>
              </div>
            )}
          </div>
        </details>
        <aside className="replay-inspector">
          <div className="replay-inspector-note">
            <h2>검증 방식 비교</h2>
            <p>{blocked || state.action ? "이번 체험의 결과는 위에 있습니다. " : "실행 후 위에서 이번 체험의 결과를 확인할 수 있습니다. "}별도 실험에서는 기록 전 검증 방식에 따른 차이를 비교합니다.</p>
          </div>
          <button className="case-compare" onClick={onEvidence}>
            세 방식 비교
            <ArrowUpRight size={16} />
          </button>
        </aside>
      </div>

      <div className="case-bottom">
        <details className="case-connection-config">
          <summary>
            API 연결 설정
            <ChevronDown size={12} />
          </summary>
          <div>
            <label htmlFor="case-api-base">
              API 주소 <span>비우면 현재 사이트</span>
            </label>
            <input
              id="case-api-base"
              data-testid="case-api-base"
              type="url"
              placeholder="https://… 또는 현재 사이트"
              value={base}
              disabled={locked}
              onChange={(event) => setBase(event.target.value)}
            />
            <button disabled={locked} onClick={configure}>
              주소 적용
            </button>
            {configError && <p role="alert">{configError}</p>}
          </div>
        </details>
        <button onClick={onExplore}>
          조건을 직접 바꾸기
          <ArrowUpRight size={14} />
        </button>
      </div>
      <p className="case-scope">
        가상 상담 문서 · TF-IDF 검색 · 내부 상담 작업만 기록하며 실제 송금은 하지 않습니다.
      </p>
    </section>
  );
}
