import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  Download,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import { CaseApi } from "./caseApi";
import { CaseFlow } from "./caseFlow";
import "./caseStudy.css";

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
  "현재 근거를 검증하고 같은 트랜잭션에서 상담 작업을 기록합니다.",
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
  defaultBase,
  onExplore,
  onEvidence,
}: {
  defaultBase: string;
  onExplore: () => void;
  onEvidence: () => void;
}) {
  const [base, setBase] = useState(defaultBase);
  const [configuredBase, setConfiguredBase] = useState(defaultBase);
  const [configError, setConfigError] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const flow = useMemo(
    () => new CaseFlow(new CaseApi(configuredBase)),
    [configuredBase],
  );
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot);
  useEffect(() => {
    flow.activate();
    return () => flow.dispose();
  }, [flow]);
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
      setConfiguredBase(base);
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

  return (
    <section
      className="case-study"
      data-testid="case-study"
      data-step={state.step}
      aria-label="근거에서 실행까지 실제 API 사례"
    >
      <div className="case-desk-heading">
        <div className="case-desk-title">
          <span className="case-section-label">상담 검토</span>
          <span className="case-fiction">가상 문의</span>
        </div>
        <div className="case-heading-tools">
          <span
            className={`case-connection ${state.session ? "is-connected" : ""}`}
          >
            {state.session ? "Python API 연결됨" : "실행하면 API에 연결됩니다"}
          </span>
          <button
            className="case-quiet"
            data-testid="case-reset"
            onClick={reset}
            aria-label="사례 처음부터"
          >
            <RotateCcw size={14} />
            처음부터
          </button>
        </div>
      </div>

      <div className="case-question">
        <div>
          <span className="case-question-label">이체 한도 문의</span>
          <h1>하루 이체 한도가 얼마인가요?</h1>
          <p>
            답변을 준비한 뒤 한도가 바뀝니다. 이전 답변으로 기록을 남기면 어떻게
            될까요?
          </p>
        </div>
        <div className="case-run-control">
          {state.step < 6 ? (
            <button
              className="case-run"
              data-testid="case-run-all"
              disabled={locked || expired}
              onClick={() => void flow.runAll()}
            >
              {state.running ? (
                <LoaderCircle className="case-spin" size={15} />
              ) : null}
              {state.running
                ? "실행 중"
                : state.step === 0
                  ? "전체 과정 실행"
                  : "이어서 실행"}
              <ArrowUpRight size={17} />
            </button>
          ) : (
            <button className="case-run" onClick={download}>
              <Download size={15} />
              실행 기록 저장
            </button>
          )}
          <span>실제 API 요청 · 결과를 이 화면에 남깁니다</span>
        </div>
      </div>

      <div className="case-review-grid">
        <div className="case-answer-pane">
          <div className="case-pane-heading">
            <h2>상담 답변</h2>
            <span>
              {state.action ? "기록 완료" : receipt ? "검토 중" : "준비 전"}
            </span>
          </div>
          <article
            className={`case-draft ${mismatched ? "is-outdated" : ""}`}
            data-testid="case-draft"
          >
            {receipt ? (
              <>
                <div className="case-draft-meta">
                  <span>
                    {state.freshReceipt ? "갱신한 답변" : "최초 답변"}
                  </span>
                  <span>인용 문서 v{receipt.references[0]?.revision}</span>
                </div>
                <p className="case-answer-text">
                  <Highlight text={receipt.output} />
                </p>
                <div
                  className={`case-draft-verdict ${mismatched ? "is-warning" : ""}`}
                >
                  <span className="case-line-dot" />
                  {mismatched
                    ? blocked
                      ? "현재 정책과 달라 실행이 차단됐습니다."
                      : "현재 정책과 다릅니다. 실행 시점 검증이 필요합니다."
                    : state.action
                      ? "이 답변으로 상담 작업을 기록했습니다."
                      : "문서를 인용한 답변입니다. 기록 전 근거를 다시 확인합니다."}
                </div>
                <code className="case-receipt-id">
                  receipt / {short(receipt.id)}
                </code>
              </>
            ) : (
              <div className="case-start-note">
                <span className="case-note-label">이 상담에서 확인할 것</span>
                <p>
                  답변은 <strong>300만 원</strong>.<br />
                  그사이, 정책은 <strong>100만 원</strong>.
                </p>
                <span>
                  한 번 맞았던 답변이 기록하는 순간에도 맞는지 확인합니다.
                </span>
                <div className="case-start-sequence">
                  <span>답변 준비</span>
                  <ArrowRight size={14} />
                  <span>정책 변경</span>
                  <ArrowRight size={14} />
                  <span>실행 검증</span>
                </div>
              </div>
            )}
          </article>

          {state.freshReceipt && state.oldReceipt && (
            <div className="case-superseded" data-testid="case-old-draft">
              <div>
                <span>차단된 최초 답변</span>
                <span>문서 v{state.oldReceipt.references[0]?.revision}</span>
              </div>
              <p>
                <Highlight text={state.oldReceipt.output} />
              </p>
              <small>답변을 덮어쓰지 않고, 차단 근거와 함께 보존합니다.</small>
            </div>
          )}

          <div className="case-action-area">
            <div className="case-action-copy">
              <span>
                {state.step < 6
                  ? `${Math.min(state.step + 1, 6)} / 6 · ${working[state.step]}`
                  : "재시도 확인 완료"}
              </span>
              <p>{descriptions[state.step]}</p>
            </div>
            <button
              data-testid="case-next"
              className="case-next"
              disabled={locked || expired}
              onClick={state.step < 6 ? () => void flow.next() : onEvidence}
            >
              {state.busy && !state.running ? (
                <LoaderCircle className="case-spin" size={14} />
              ) : null}
              {state.step >= 6
                ? "검증 결과 보기"
                : state.error
                  ? "이 단계 다시 시도"
                  : actions[state.step]}
              <ArrowRight size={14} />
            </button>
          </div>
          <div
            className={`case-result ${!state.error && !state.busy && !state.status ? "is-empty" : ""}`}
            data-testid="case-status"
            role={state.error ? "alert" : "status"}
            aria-live="polite"
          >
            {state.error ? (
              <>
                <strong>요청 실패</strong>
                <span>{state.error}</span>
                <span>이 단계에서 다시 시도할 수 있습니다.</span>
              </>
            ) : state.busy ? (
              <>
                <LoaderCircle className="case-spin" size={14} />
                <span>
                  {state.step === 0
                    ? "서버 연결·문서 검색 중입니다. 서버가 쉬고 있었다면 최대 90초가 걸립니다."
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
                disabled={locked || !state.canReprepare}
                onClick={flow.reprepare}
              >
                새 답변 다시 준비
              </button>
            </div>
          )}
        </div>

        <aside className="case-policy-pane" data-testid="case-source">
          <div className="case-pane-heading">
            <h2>현재 정책</h2>
            <span>{source ? `v${source.revision}` : "실행 전"}</span>
          </div>
          <div className="case-policy-document">
            <span className="case-document-type">정책 문서 / 이체</span>
            <h3>{source?.title || "이체 한도 안내"}</h3>
            {source ? (
              <>
                <p className="case-policy-text">
                  <Highlight text={source.text} />
                </p>
                <div className="case-policy-index">
                  <span className="case-line-dot" />
                  {state.state?.index_stale
                    ? "원문 변경됨 · 인덱스 갱신 필요"
                    : "원문과 인덱스 일치"}
                </div>
                <code>source / {source.source_id}</code>
              </>
            ) : (
              <>
                <p className="case-policy-pending">
                  실행하면 Python 서버에서
                  <br />
                  원문과 버전을 불러옵니다.
                </p>
                <span className="case-note-label">미리 정한 변경 조건</span>
              </>
            )}
            <div
              className="case-policy-delta"
              aria-label="실험의 정책 변경 조건"
            >
              <div>
                <span>변경 전</span>
                <strong>
                  300<small>만 원</small>
                </strong>
              </div>
              <ArrowRight size={17} />
              <div>
                <span>변경 후</span>
                <strong>
                  100<small>만 원</small>
                </strong>
              </div>
            </div>
            <p className="case-policy-footnote">
              가상 문서의 일일 이체 한도
              <br />
              실제 금융기관의 정책과 무관합니다.
            </p>
          </div>
        </aside>
      </div>

      {(blocked || state.action) && (
        <section
          className="case-outcomes"
          data-testid="case-outcomes"
          aria-label="서버가 확인한 실행 결과"
        >
          <div className="case-outcomes-heading">
            <h2>무엇이 기록됐나요?</h2>
            <span>실제 서버 응답</span>
          </div>
          <dl>
            <div>
              <dt>이전 답변</dt>
              <dd className={blocked ? "is-blocked" : ""}>
                {blocked ? "실행 차단" : "확인 전"}
              </dd>
              <span>{blocked ? "409 · source_changed" : "—"}</span>
            </div>
            <div>
              <dt>갱신한 답변</dt>
              <dd>{state.action ? "작업 기록됨" : "기록 전"}</dd>
              <span>
                {state.action ? "검증과 기록을 한 트랜잭션으로" : "—"}
              </span>
            </div>
            <div>
              <dt>같은 요청 재시도</dt>
              <dd>{state.step === 6 ? "동일 작업 반환" : "확인 전"}</dd>
              <span>{state.step === 6 ? "새 작업 ID 없음" : "—"}</span>
            </div>
          </dl>
          {state.action && (
            <div className="case-action-receipt" data-testid="case-action">
              <span>작업 ID</span>
              <code>{state.action.action_id}</code>
              <span>
                {state.action.replayed ? "동일 작업 · 과거 기록" : "기록됨"}
              </span>
            </div>
          )}
        </section>
      )}

      <div className="case-audit-heading">
        <div>
          <h2>요청 내역</h2>
          <span>
            {state.events.length
              ? `${state.events.length}개의 응답`
              : "실행 후 표시됩니다"}
          </span>
        </div>
        <button
          className="case-download"
          disabled={locked || !state.events.length}
          onClick={download}
        >
          <Download size={13} />
          사건 기록 JSON
        </button>
      </div>
      <div className="case-trail" aria-label="실제 API 응답 기록">
        {state.events.length > 0 && (
          <ol data-testid="case-events">
            {state.events.map((event, i) => (
              <li key={`${i}-${event.at}`}>
                <details>
                  <summary>
                    <span className="case-event-order">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span>{event.label}</span>
                    <time>
                      {new Date(event.at).toLocaleTimeString("ko-KR", {
                        hour12: false,
                      })}
                    </time>
                    <ChevronDown size={12} />
                  </summary>
                  <pre>{JSON.stringify(event.data, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        )}
      </div>
      <p className="case-scope">
        가상 문서의 검색 결과를 발췌합니다. LLM 생성·실제 발송·송금은 하지
        않습니다.{" "}
        {state.step === 6 &&
          "재시도 응답은 과거 기록이며, 현재 근거의 유효성을 뜻하지 않습니다."}
      </p>
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
        <div className="case-deep-links">
          <button disabled={locked} onClick={onExplore}>
            조건을 직접 바꾸기
            <ArrowUpRight size={13} />
          </button>
          <button disabled={locked} onClick={onEvidence}>
            비교 실험과 검증 근거
            <ArrowUpRight size={13} />
          </button>
        </div>
      </div>
    </section>
  );
}
