import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Download,
  FileText,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-react";
import { CaseApi } from "./caseApi";
import { CaseFlow } from "./caseFlow";
import "./caseStudy.css";

const stages = [
  "답변 준비",
  "원문 변경",
  "실행 차단",
  "다시 준비",
  "작업 기록",
  "재시도",
];
const actions = [
  "API 연결하고 답변 준비",
  "원문을 100만 원으로 변경",
  "이전 답변으로 실행 시도",
  "검증 후 최신 답변 준비",
  "최신 답변으로 작업 기록",
  "같은 키로 다시 요청",
];
const explanations = [
  "고객 질문은 “하루 이체 한도가 얼마인가요?”입니다. Python API에서 원문을 검색하고 답변을 준비합니다.",
  "답변을 준비한 뒤 정책이 바뀌는 상황입니다. 원문만 바꾸면 이미 준비한 답변은 어떻게 될까요?",
  "원문은 100만 원, 준비한 답변은 300만 원입니다. 이 답변으로 상담 작업을 기록해 봅니다.",
  "오래된 답변은 차단했습니다. 변경된 문서로 모델·인덱스 쌍을 평가하고 새 답변을 준비합니다.",
  "100만 원을 인용한 새 답변입니다. 실행 시점에 근거를 다시 검증하고 같은 트랜잭션에서 기록합니다.",
  "응답을 놓쳐 같은 요청을 다시 보냈다고 가정합니다. 동일한 키로 요청하면 작업이 하나 더 생길까요?",
  "완료했습니다. 바뀐 근거는 실행을 막고, 최신 근거는 작업으로 남기며, 재시도는 같은 작업을 돌려줍니다.",
];
function short(value?: string) {
  return value ? value.slice(0, 8) : "—";
}
function Highlight({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(300만 원|100만 원)/)
        .map((part, index) =>
          /^(300|100)만 원$/.test(part) ? (
            <mark key={index}>{part}</mark>
          ) : (
            part
          ),
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
  const [prediction, setPrediction] = useState("");
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
  const reset = () => {
    flow.reset();
    setPrediction("");
    setConfigError("");
  };
  const configure = () => {
    try {
      new CaseApi(base);
      flow.reset();
      setConfiguredBase(base);
      setConfigError("");
      setPrediction("");
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
      <div className="case-topline">
        <span className="case-kicker">
          <span /> CASE 01 / SUPPORT DESK
        </span>
        <span
          className={`case-connection ${state.session ? "is-connected" : ""}`}
        >
          <Terminal size={13} />
          {state.session ? "PYTHON API 연결됨" : "실제 API · 연결 전"}
        </span>
      </div>
      <div className="case-heading">
        <div>
          <h2>이체 한도 안내</h2>
          <p>준비할 때 맞던 답변, 실행할 때도 맞을까요?</p>
        </div>
        <button
          className="case-quiet"
          data-testid="case-reset"
          onClick={reset}
          aria-label="사례 처음부터"
        >
          <RotateCcw size={14} />
          <span>처음부터</span>
        </button>
      </div>
      <ol className="case-steps" aria-label="사례 진행 단계">
        {stages.map((stage, i) => (
          <li
            key={stage}
            className={
              state.step > i ? "is-done" : state.step === i ? "is-current" : ""
            }
            aria-current={state.step === i ? "step" : undefined}
          >
            <span>
              {state.step > i ? (
                <Check size={12} />
              ) : (
                String(i + 1).padStart(2, "0")
              )}
            </span>
            {stage}
          </li>
        ))}
      </ol>
      <div className="case-workspace">
        <div className="case-main">
          <div className="case-brief">
            <span>고객 문의</span>
            <p>“하루 이체 한도가 얼마인가요?”</p>
            <span className="case-brief-label">가상 상담 사례</span>
          </div>
          <div className="case-comparison">
            <article
              className={`case-document ${mismatched ? "is-updated" : ""}`}
              data-testid="case-source"
            >
              <div className="case-card-label">
                <FileText size={15} />
                <span>현재 원문</span>
                <code>{source ? `v${source.revision}` : "—"}</code>
              </div>
              <h3>{source?.title || "API에서 불러올 원문"}</h3>
              {source ? (
                <p className="case-body-text">
                  <Highlight text={source.text} />
                </p>
              ) : (
                <p className="case-placeholder">
                  연결 후 이체 한도 문서가 표시됩니다.
                </p>
              )}
              <div className="case-card-foot">
                {source ? (
                  <>
                    <span>source / {source.source_id}</span>
                    <span>
                      {state.state?.index_stale
                        ? "인덱스 갱신 필요"
                        : "인덱스 일치"}
                    </span>
                  </>
                ) : (
                  <span>서버 응답 대기</span>
                )}
              </div>
            </article>
            <article
              className={`case-document case-answer ${mismatched ? "is-outdated" : ""}`}
              data-testid="case-draft"
            >
              <div className="case-card-label">
                <ShieldCheck size={15} />
                <span>
                  {state.freshReceipt ? "다시 준비한 답변" : "준비한 답변"}
                </span>
                <code>
                  {receipt ? `v${receipt.references[0]?.revision}` : "—"}
                </code>
              </div>
              <h3>
                {receipt ? "문서에서 추출한 답변" : "아직 답변이 없습니다"}
              </h3>
              {receipt ? (
                <p className="case-body-text">
                  <Highlight text={receipt.output} />
                </p>
              ) : (
                <p className="case-placeholder">
                  원문을 검색하고 인용한 내용을 보존합니다.
                </p>
              )}
              <div className="case-card-foot">
                <span>
                  {receipt
                    ? `receipt / ${short(receipt.id)}`
                    : "생성 결과를 미리 표시하지 않습니다"}
                </span>
                {mismatched && <strong>이전 근거 보존</strong>}
              </div>
            </article>
          </div>
          {state.freshReceipt && state.oldReceipt && (
            <details className="case-old">
              <summary>
                <ChevronDown size={13} /> 최초 300만 원 답변은 어떻게 됐나요?{" "}
                <span>
                  v{state.oldReceipt.references[0]?.revision} · 보존됨
                </span>
              </summary>
              <p>
                <Highlight text={state.oldReceipt.output} />
              </p>
              <code>{state.oldReceipt.id}</code>
            </details>
          )}
          <div
            className={`case-action-area ${state.step === 3 ? "is-blocked" : ""}`}
          >
            <div className="case-action-title">
              <span className="case-stage-number">
                {state.step < 6 ? (
                  String(state.step + 1).padStart(2, "0")
                ) : (
                  <Check size={16} />
                )}
              </span>
              <h3>
                {state.step < 6 ? stages[state.step] : "하나의 작업으로 마무리"}
              </h3>
            </div>
            <p className="case-explanation">{explanations[state.step]}</p>
            {state.step === 1 && (
              <fieldset className="case-prediction" disabled={state.busy}>
                <legend>
                  실행 결과를 예상해 보세요 <span>선택 사항</span>
                </legend>
                {["이전 답변 실행", "변경 감지 후 차단"].map((option) => (
                  <label key={option}>
                    <input
                      type="radio"
                      name="case-prediction"
                      checked={prediction === option}
                      onChange={() => setPrediction(option)}
                    />
                    {option}
                  </label>
                ))}
              </fieldset>
            )}
            {state.step === 3 && prediction && (
              <p className="case-reveal">
                내 예상: {prediction}. 서버는 인용한 원문 버전의 변경을
                감지했습니다. 이 선택으로 지원자의 역량을 평가하지 않습니다.
              </p>
            )}
            <div
              className="case-result"
              data-testid="case-status"
              role={state.error ? "alert" : "status"}
              aria-live="polite"
            >
              {state.error ? (
                <>
                  <strong>요청 실패</strong>
                  <span>{state.error}</span>
                  <span>
                    같은 단계에서 다시 시도하거나 처음부터 시작하세요.
                  </span>
                </>
              ) : state.busy ? (
                <>
                  <LoaderCircle className="case-spin" size={15} />
                  <span>
                    {state.step === 0
                      ? "API 연결·답변 준비 중… 서버가 쉬고 있었다면 최대 90초가 걸립니다."
                      : "API 응답을 기다리는 중…"}
                  </span>
                </>
              ) : state.status ? (
                <>
                  <span className="case-result-dot" />
                  <span>{state.status}</span>
                </>
              ) : (
                <span>
                  모든 결과는 버튼을 누른 뒤 실제 API 응답으로 채워집니다.
                </span>
              )}
            </div>
            {state.action && (
              <div className="case-action-receipt" data-testid="case-action">
                <span>
                  LOCAL TASK <code>{state.action.action_id}</code>
                </span>
                <span>
                  {state.action.replayed
                    ? "동일 작업 · 과거 기록"
                    : "작업 기록됨"}
                </span>
              </div>
            )}
            {state.step === 4 && state.freshReceipt && (
              <div className="case-expiry">
                <span>
                  {!state.canReprepare
                    ? "원래 요청을 다시 보내 기록 여부를 확인하세요."
                    : secondsLeft > 0
                      ? `새 답변 유효기간 · 약 ${secondsLeft}초 남음`
                      : "답변 유효기간이 지났습니다. 새 답변을 준비하세요."}
                </span>
                <button
                  disabled={state.busy || !state.canReprepare}
                  onClick={flow.reprepare}
                >
                  새 답변 다시 준비
                </button>
              </div>
            )}
            <div className="case-next-row">
              {state.step < 6 ? (
                <button
                  data-testid="case-next"
                  className="case-next"
                  disabled={
                    state.busy ||
                    (state.step === 4 &&
                      state.canReprepare &&
                      secondsLeft === 0)
                  }
                  onClick={() => void flow.next()}
                >
                  {state.busy ? (
                    <LoaderCircle className="case-spin" size={16} />
                  ) : (
                    <Zap size={15} />
                  )}
                  {state.error ? "이 단계 다시 시도" : actions[state.step]}
                  {!state.busy && <ArrowRight size={16} />}
                </button>
              ) : (
                <button
                  data-testid="case-next"
                  className="case-next"
                  onClick={onEvidence}
                >
                  실제 검증 기록 살펴보기
                  <ArrowRight size={16} />
                </button>
              )}
              <span>{Math.min(state.step, 6)} / 6 완료</span>
            </div>
          </div>
          <p className="case-scope">
            검증 범위: 같은 데이터베이스 안의 상담 작업 기록. 실제 메시지
            발송·송금은 하지 않습니다.
            {state.step === 6 &&
              " 재시도 응답은 과거 기록이며 현재 근거가 유효하다는 뜻은 아닙니다."}
          </p>
        </div>
        <aside className="case-trail" aria-label="실제 API 응답 기록">
          <div className="case-trail-heading">
            <h3>사건 기록</h3>
            <span>{String(state.events.length).padStart(2, "0")} EVENTS</span>
          </div>
          <p className="case-trail-caption">원문 → 답변 → 실행의 연결</p>
          {state.events.length ? (
            <ol data-testid="case-events">
              {state.events.map((event, i) => (
                <li key={`${i}-${event.at}`}>
                  <span className="case-event-point" />
                  <details>
                    <summary>
                      <span>{event.label}</span>
                      <time>
                        {new Date(event.at).toLocaleTimeString("ko-KR", {
                          hour12: false,
                        })}
                      </time>
                    </summary>
                    <pre>{JSON.stringify(event.data, null, 2)}</pre>
                  </details>
                </li>
              ))}
            </ol>
          ) : (
            <div className="case-trail-empty">
              <span className="case-empty-line" />
              <p>아직 일어난 사건이 없습니다.</p>
              <span>
                답변을 준비하면
                <br />첫 기록이 남습니다.
              </span>
            </div>
          )}
          <button
            className="case-download"
            disabled={state.busy || !state.events.length}
            onClick={download}
          >
            <Download size={14} /> 사건 기록 JSON
          </button>
          <p className="case-trail-note">
            시각은 브라우저 수신 시각입니다.
            <br />
            펼치면 서버 응답 원본을 봅니다.
          </p>
        </aside>
      </div>
      <div className="case-bottom">
        <details className="case-connection-config">
          <summary>
            API 연결 설정 <ChevronDown size={12} />
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
              disabled={state.busy}
              onChange={(event) => setBase(event.target.value)}
            />
            <button disabled={state.busy} onClick={configure}>
              주소 적용
            </button>
            {configError && <p role="alert">{configError}</p>}
          </div>
        </details>
        <div className="case-deep-links">
          <button disabled={state.busy} onClick={onExplore}>
            고급 실험
            <ArrowRight size={13} />
          </button>
          <button disabled={state.busy} onClick={onEvidence}>
            검증 기록
            <ArrowRight size={13} />
          </button>
        </div>
      </div>
    </section>
  );
}
