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
import CaseRunButton from "./CaseRunButton";
import CaseJournal from "./CaseJournal";

const actions = [
  "답변 준비",
  "정책 변경 적용",
  "이전 답변으로 기록 시도",
  "최신 근거로 다시 준비",
  "검증하고 상담 기록",
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
function Highlight({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(300만 원|100만 원)/)
        .map((part, i) =>
          /^(300|100)만 원$/.test(part) ? <mark key={i}>{part}</mark> : part,
        )}
    </>
  );
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
          {state.step < 6 ? (
            <CaseRunButton flow={flow} />
          ) : (
            <button className="case-run" onClick={download}>
              <Download size={15} />
              실행 기록 저장
            </button>
          )}
        </div>
      </div>
      <div
        className={`case-result ${!state.error && !state.busy && !state.status ? "is-empty" : ""}`}
        data-testid="case-status"
        role={state.error ? "alert" : "status"}
        aria-live="polite"
      >
        {state.error ? (
          <>
            <strong>{state.sessionExpired ? "세션 만료" : "요청 실패"}</strong>
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
          {state.restored ? "이전 상담 기록" : "답변 확인"}
          <small>{state.restored ? "브라우저 저장본" : "실시간 API · 샘플 상담"}</small>
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
                : "API 연결 전"}
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
                : "‘이어서 실행’으로 서버 상태를 확인하고 계속하세요."}</p>
        </div>
      )}
      {(blocked || state.action) && (
        <section
          className="case-outcomes case-outcome-summary"
          data-testid="case-outcomes"
          ref={outcomeRef}
          tabIndex={-1}
          aria-labelledby="case-outcome-title"
        >
          <h2 id="case-outcome-title">{state.restored ? "이전 실행 결과" : "이번 실행 결과"}</h2>
          <p className="case-outcome-explanation">
            {blocked
              ? "300만 원을 안내한 답변은 문서 변경으로 차단됐습니다. 현재 안내는 100만 원입니다."
              : "서버가 반환한 상담 기록입니다. 이전 답변의 차단 여부는 실행 로그를 확인하세요."}
          </p>
          <dl>
            <div>
              <dt>변경 전 답변</dt>
              <dd className={blocked ? "is-blocked" : "is-pending"}>{blocked ? "오래된 답변 차단" : "확인 전"}</dd>
              <dd className="case-outcome-detail">{blocked ? "300만 원 안내 · 인용 문서 변경으로 기록 거절" : "차단 응답 확인 전"}</dd>
            </div>
            <div>
              <dt>변경 후 답변</dt>
              <dd className={state.action ? "" : "is-pending"}>{state.action ? "새 답변 기록 완료" : "기록 확인 전"}</dd>
              <dd className="case-outcome-detail">{state.action ? "100만 원 안내 · 현재 문서를 확인한 뒤 기록" : "성공 응답을 받아야 기록 완료로 표시"}</dd>
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
        </section>
      )}
      <div className={`replay-machine gate-${gate}`}>
        <div className="replay-ruler" aria-hidden="true">
          <span>문제 상황 · 변경된 원문</span>
          <span>비교 대상 · 준비된 답변</span>
          <span>실행 판단 · 차단 또는 기록</span>
        </div>
        <div className="replay-canvas">
          <aside className="replay-source" data-testid="case-source">
            <div className="replay-node-label">
              <span>안내 문서</span>
              <span>{source ? `문서 v${source.revision}` : "불러오기 전"}</span>
            </div>
            <h2>하루 이체 한도</h2>
            <div className="policy-value" data-testid="case-policy-value">
              {source ? <Highlight text={state.step >= 2 ? "100만 원" : "300만 원"} /> : "—"}
            </div>
            <div className="replay-source-caption">
              {source ? (state.step >= 2 ? "변경된 안내 · 이전 한도 300만 원" : "현재 안내") : "서버 연결 후 표시"}
            </div>
            <div className="replay-source-text">
              {source ? (
                <>
                  <p>
                    <Highlight text={source.text} />
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
            </div>
            <span className="replay-wire" aria-hidden="true">
              →
            </span>
          </aside>

          <div className="replay-answer">
            <div className="replay-query">
              <span>고객 문의</span>
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
                    <Highlight text={receipt.output} />
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
                      아직 작성된 답변이 없습니다.
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
              <details className="case-superseded" data-testid="case-old-draft">
                <summary>
                  <span>차단된 최초 답변 · 300만 원</span>
                  <ChevronDown size={13} />
                </summary>
                <p>
                  <Highlight text={state.oldReceipt.output} />
                </p>
                <small>
                  문서 v{state.oldReceipt.references[0]?.revision} · 차단 근거
                  보존
                </small>
              </details>
            )}
            <span className="replay-wire" aria-hidden="true">
              →
            </span>
          </div>

          <div className="replay-gate">
            <div className="replay-node-label">
              <span>기록 처리</span>
            </div>
            <div className="replay-gate-symbol" aria-hidden="true">
              <span />
              <span />
              <span />
              <i>
                {state.action
                  ? "✓"
                  : blocked && !state.freshReceipt
                    ? "×"
                    : "↳"}
              </i>
            </div>
            <h2>
              {state.action
                ? state.action.replayed
                  ? "같은 작업 반환"
                  : "정상 답변 기록"
                : blocked && !state.freshReceipt
                  ? "오래된 답변 차단"
                  : mismatched
                    ? "변경 감지"
                    : state.freshReceipt
                      ? "새 답변 확인 대기"
                      : "기록 전 확인"}
            </h2>
            <p>
              {state.action
                ? state.action.replayed
                  ? "재시도에도 같은 작업을 반환했습니다."
                  : "현재 안내 문서를 인용한 새 답변을 기록했습니다."
                : blocked && !state.freshReceipt
                  ? "인용한 안내 문서가 변경되어 기록을 거절했습니다. 새 답변이 필요합니다."
                  : mismatched
                    ? "답변은 이전 안내를 인용하고 있습니다. 기록 요청 시 서버가 변경 여부를 확인합니다."
                    : state.freshReceipt
                      ? "갱신한 답변으로 기록을 시도합니다."
                      : "인용한 문서가 바뀌지 않았고 유효기간이 남아 있어야 상담 기록을 저장합니다."}
            </p>
            <p className="replay-result-guide">
              {state.action
                ? state.action.replayed
                  ? "같은 요청 키의 재시도: 아래 작업 ID로 기존 기록과 비교"
                  : "현재 원문과 답변의 일치 확인 후 작업 기록 생성"
                : blocked && !state.freshReceipt
                  ? "이전 답변 300만 원 / 변경된 안내 100만 원"
                  : mismatched
                    ? "비교 대상: 변경 전 답변 300만 원 / 현재 한도 100만 원"
                    : state.freshReceipt
                      ? "갱신 결과: 현재 한도 100만 원을 반영한 새 답변"
                      : "확인 대상: 인용 문서의 변경 여부 · 답변 유효기간"}
            </p>
          </div>
        </div>

        {transport}
      </div>

      <div className="replay-below">
        <div className="replay-audit">
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
        </div>
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
        가상 상담 문서 · TF-IDF 검색 · 실제 API의 검증과 작업 기록
      </p>
    </section>
  );
}
