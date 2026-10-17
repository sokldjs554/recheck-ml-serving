import { useEffect, useState, useSyncExternalStore } from "react";
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
      </ol>
      <div className="replay-controls">
        <div className="replay-now">
          <span>
            {state.step === 6
              ? "COMPLETE"
              : `STEP ${String(state.step + 1).padStart(2, "0")}`}
          </span>
          <p>{descriptions[state.step]}</p>
        </div>
        <div className="replay-buttons">
          <button
            data-testid="case-next"
            className="case-next"
            disabled={locked || expired || state.sessionExpired}
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
        <div className="replay-title">
          <span className="replay-case-number">01</span>
          <div>
            <span className="case-route-label">
              01 / 실행 재현 · 실시간 API
            </span>
            <h2>상담 기록, 실행 직전 검증</h2>
            <p>
              300만 → 100만 원 변경을 적용하고, 이전 답변의 기록이 차단되는지
              확인합니다.
            </p>
          </div>
        </div>
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
      {state.restored && <p className="case-persistence-note" data-testid="case-restored">이 탭의 실행 기록을 복원했습니다. ‘이어서 실행’으로 서버 상태를 확인하고 계속하세요.</p>}
      <div className={`replay-machine gate-${gate}`}>
        {transport}
        <div className="replay-ruler" aria-hidden="true">
          <span>문제 상황 · 변경된 원문</span>
          <span>비교 대상 · 준비된 답변</span>
          <span>실행 판단 · 차단 또는 기록</span>
        </div>
        <div className="replay-canvas">
          <aside className="replay-source" data-testid="case-source">
            <div className="replay-node-label">
              <span>01 / 원문</span>
              <span>{source ? `v${source.revision}` : "실험 조건"}</span>
            </div>
            <h2>하루 이체 한도</h2>
            <div
              className={`replay-amount ${state.step >= 2 ? "has-changed" : ""}`}
            >
              <span className="replay-amount-before">300</span>
              <span className="replay-amount-arrow">↘</span>
              <span className="replay-amount-after">
                100<small>만 원</small>
              </span>
            </div>
            <div className="replay-source-caption">
              {source
                ? state.step >= 2
                  ? "원문 변경 적용됨"
                  : "현재 원문 · 300만 원"
                : "300만 원에서 100만 원으로 변경 예정"}
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
                  가상 정책 문서입니다. 실행하면 서버에서 원문을 가져옵니다.
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
                        ? "바뀐 원문과 달라 실행이 차단됐습니다."
                        : "원문이 바뀌었습니다. 이 답변은 그대로입니다."
                      : state.action
                        ? "이 답변으로 작업을 기록했습니다."
                        : "현재 원문을 인용했습니다. 실행 전 다시 검증합니다."}
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
                      문서를 검색해 답변을 준비합니다.
                      <br />
                      <strong>원문이 바뀌어도, 이 답변은 남습니다.</strong>
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
              <span>03 / 서버의 실행 판단</span>
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
                  ? "기록 반환"
                  : "기록 완료"
                : blocked && !state.freshReceipt
                  ? "실행 차단"
                  : mismatched
                    ? "변경 감지"
                    : state.freshReceipt
                      ? "다시 검증"
                      : "검증 대기"}
            </h2>
            <p>
              {state.action
                ? state.action.replayed
                  ? "재시도에도 같은 작업을 반환했습니다."
                  : "검증과 기록을 한 트랜잭션으로 처리했습니다."
                : blocked && !state.freshReceipt
                  ? "이전 답변으로는 작업을 기록할 수 없습니다."
                  : mismatched
                    ? "이전 답변으로 기록을 시도해 보세요."
                    : state.freshReceipt
                      ? "갱신한 답변으로 기록을 시도합니다."
                      : "답변과 현재 근거가 일치해야 기록합니다."}
            </p>
            <code className="replay-gate-code">
              {state.action
                ? state.action.replayed
                  ? "200 / replayed"
                  : "200 / recorded"
                : blocked && !state.freshReceipt
                  ? "409 / source_changed"
                  : "검증 후 서버 응답 표시"}
            </code>
            <p className="replay-result-guide">
              {state.action
                ? state.action.replayed
                  ? "같은 요청 키의 재시도: 아래 작업 ID로 기존 기록과 비교"
                  : "현재 원문과 답변의 일치 확인 후 작업 기록 생성"
                : blocked && !state.freshReceipt
                  ? "차단 이유: 답변의 300만 원과 현재 한도 100만 원의 불일치"
                  : mismatched
                    ? "비교 대상: 변경 전 답변 300만 원 / 현재 한도 100만 원"
                    : state.freshReceipt
                      ? "갱신 결과: 현재 한도 100만 원을 반영한 새 답변"
                      : "확인 순서: 답변 준비 → 한도 변경 → 기록 차단 → 새 답변 기록"}
            </p>
          </div>
        </div>


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
              <CaseJournal events={state.events} />
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
          {blocked || state.action ? (
            <section
              className="case-outcomes"
              data-testid="case-outcomes"
              aria-label="서버가 확인한 실행 결과"
            >
              <h2>기록 결과</h2>
              <dl>
                <div>
                  <dt>이전 답변</dt>
                  <dd className="is-blocked">
                    {blocked ? "실행 차단" : "확인 전"}
                  </dd>
                </div>
                <div>
                  <dt>갱신한 답변</dt>
                  <dd>{state.action ? "작업 기록됨" : "기록 전"}</dd>
                </div>
                <div>
                  <dt>같은 요청 재시도</dt>
                  <dd>{state.step === 6 ? "동일 작업 반환" : "확인 전"}</dd>
                </div>
              </dl>
              {state.action && (
                <div className="case-action-receipt" data-testid="case-action">
                  <span>작업 ID</span>
                  <code>{state.action.action_id}</code>
                  <small>
                    {state.action.replayed ? "동일 작업 · 과거 기록" : "기록됨"}
                  </small>
                </div>
              )}
            </section>
          ) : (
            <div className="replay-inspector-note">
              <h2>실행 전에 확인할 것</h2>
              <p>
                답변을 준비할 때 맞았던 근거가 기록하는 순간에도 유효할까요?
              </p>
              <span>실제 API로 차단과 재시도를 확인합니다.</span>
            </div>
          )}
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
        가상 상담 문서 · TF-IDF 검색 · /evidence/…/execute
      </p>
    </section>
  );
}
