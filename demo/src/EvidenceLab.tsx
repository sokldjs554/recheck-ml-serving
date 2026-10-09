import { visibleValidation, staleRelease } from "./evidencePresentation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  Files,
  ArrowRight,
  ArrowUpRight,
  Check,
  Download,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  Wifi,
} from "lucide-react";
import {
  EvidenceApi,
  type Candidate,
  type EvidenceReceipt,
  type EvidenceState,
  type ReleaseReport,
  type UseResult,
} from "./evidenceApi";

const reasons: Record<string, string> = {
  current: "인용한 문서와 배포 버전이 현재와 같습니다.",
  source_changed:
    "인용한 문서가 수정되었습니다. 이전 답변을 사용하지 않습니다.",
  source_deleted:
    "인용한 문서가 삭제되었습니다. 이전 답변을 사용하지 않습니다.",
  release_changed: "답변을 만든 뒤 모델·인덱스가 교체되었습니다.",
  receipt_expired:
    "120초의 기록 유효기간이 지났습니다. 답변을 다시 준비하세요.",
};
const gates: Record<string, string> = {
  model_index_match: "모델·인덱스 일치",
  retrieval_quality: "검색 품질",
  quality_regression: "기준선 대비 품질 하락",
  query_latency: "검색 지연시간",
};
const queries: Record<string, string> = {
  transfer: "하루 이체 한도",
  refund: "해외 결제 취소 환불",
  card: "분실 카드 재발급",
  loan: "대출 소득 증빙 서류",
};
function download(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function EvidenceLab({ defaultBase }: { defaultBase: string }) {
  const [base, setBase] = useState(defaultBase);
  const [state, setState] = useState<EvidenceState | null>(null);
  const [sid, setSid] = useState("");
  const [sourceId, setSourceId] = useState("transfer");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("하루 이체 한도");
  const [product, setProduct] = useState<"answer" | "checklist">("answer");
  const [receipt, setReceipt] = useState<EvidenceReceipt | null>(null);
  const [validation, setValidation] = useState<UseResult | null>(null);
  const [candidate, setCandidate] = useState<Candidate>("paired");
  const [report, setReport] = useState<ReleaseReport | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [clock, setClock] = useState(Date.now());
  const api = useRef<EvidenceApi | null>(null),
    epoch = useRef(0),
    pending = useRef(false);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => {
      epoch.current++;
      clearInterval(timer);
    };
  }, []);
  const source = state?.sources.find((s) => s.source_id === sourceId);
  const locked = !!busy;
  const expired = !!receipt && clock >= receipt.expires_at * 1000;
  const checked = visibleValidation(validation, receipt, state, clock);
  const staleReport = staleRelease(report, state);
  const failure = (e: unknown) =>
    e instanceof Error
      ? e.message === "Failed to fetch"
        ? "서버에 연결하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도하세요."
        : e.message
      : "요청을 완료하지 못했습니다.";
  async function connect(reset = false) {
    if (pending.current) return;
    pending.current = true;
    const generation = ++epoch.current;
    setBusy(reset ? "새 실험 준비 중" : "Python 서버 연결 중");
    setError("");
    setValidation(null);
    try {
      const nextApi =
        reset && api.current ? api.current : new EvidenceApi(base);
      const session = reset
        ? await nextApi.createSession()
        : await nextApi.connect();
      const next = await nextApi.state(session.session_id);
      if (generation !== epoch.current) return;
      api.current = nextApi;
      setSid(session.session_id);
      setState(next);
      setSourceId("transfer");
      setText(next.sources.find((s) => s.source_id === "transfer")!.text);
      setQuery(queries.transfer);
      setReceipt(null);
      setReport(null);
      setNotice(
        "01 · 답변을 준비한 뒤, 왼쪽 문서의 300만 원을 100만 원으로 바꿔보세요.",
      );
    } catch (e) {
      if (generation === epoch.current) setError(failure(e));
    } finally {
      if (generation === epoch.current) {
        pending.current = false;
        setBusy("");
      }
    }
  }
  async function run<T>(
    label: string,
    operation: (api: EvidenceApi, sid: string) => Promise<T>,
    apply: (value: T, next: EvidenceState) => void,
  ) {
    if (pending.current || !api.current || !sid) return;
    pending.current = true;
    const generation = epoch.current;
    setBusy(label);
    setError("");
    setValidation(null);
    setNotice("");
    try {
      const value = await operation(api.current, sid);
      const next = await api.current.state(sid);
      if (generation !== epoch.current) return;
      setState(next);
      apply(value, next);
    } catch (e) {
      if (generation === epoch.current) setError(failure(e));
    } finally {
      if (generation === epoch.current) {
        pending.current = false;
        setBusy("");
      }
    }
  }
  function prepare() {
    void run(
      "근거 검색 중",
      (a, s) => a.prepare(s, query, product),
      (value) => {
        setReceipt(value);
        setNotice(
          "02 · 원문을 수정한 뒤, 이 답변을 지금 사용해도 되는지 확인하세요.",
        );
      },
    );
  }
  function edit(deleted = false) {
    if (!source) return;
    void run(
      deleted ? "삭제 반영 중" : "수정 반영 중",
      (a, s) => a.event(s, source, text, deleted),
      () => {
        setReport(null);
        setNotice(
          "03 · 원문은 바뀌었지만 오른쪽 답변은 그대로입니다. 사용 직전 검증으로 차이를 확인하세요.",
        );
      },
    );
  }
  function evaluate() {
    setReport(null);
    void run(
      "실제 검색 품질 측정 중",
      (a, s) => a.evaluate(s, candidate),
      (value) => {
        setReport(value);
        setNotice(
          value.passed
            ? "검증을 통과했습니다. 모델과 인덱스를 함께 적용할 수 있습니다."
            : "후보가 차단되었습니다. 현재 사용 중인 배포는 유지됩니다.",
        );
      },
    );
  }
  return (
    <section className="evidence-lab" aria-label="근거 변경 실험실">
      <div className="el-connect">
        <div>
          <span className="eyebrow">실제 PYTHON · 외부 LLM 호출 없음</span>
          <p>
            가상의 안내 문서 4개에서 근거를 검색합니다. 실제 은행 정책이
            아닙니다.
          </p>
        </div>
        {!state ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void connect();
            }}
          >
            <label htmlFor="evidence-api">근거 실험 API 주소</label>
            <input
              id="evidence-api"
              type="url"
              value={base}
              placeholder={location.origin}
              onChange={(e) => setBase(e.target.value)}
              disabled={locked}
            />
            <button className="ink-button" disabled={locked}>
              <Wifi size={16} />
              {locked ? "연결 대기 중" : "실험 시작"}
            </button>
          </form>
        ) : (
          <div className="el-connected">
            <span data-testid="evidence-ready">
              <span className="el-dot" />
              Python 연결됨
            </span>
            <button
              className="text-button"
              onClick={() => void connect(true)}
              disabled={locked}
            >
              <RefreshCw size={14} />새 실험
            </button>
          </div>
        )}
      </div>
      {!state && (
        <div className="el-preview" aria-label="연결 전 화면 미리보기">
          <div className="el-preview-toolbar">
            <span>문서 / 답변 비교</span>
            <span>연결 전 미리보기 · 실행 결과 아님</span>
          </div>
          <div className="el-preview-panes">
            <div className="el-preview-source">
              <span className="eyebrow">원문 · 예시 문서</span>
              <h2>이체 한도 안내</h2>
              <p>
                하루 이체 한도는 <mark>300만 원</mark>입니다.
              </p>
              <p>한도 상향을 위한 송금 본인 인증은 앱에서 진행합니다.</p>
              <small>실험을 시작하면 이 내용을 직접 수정할 수 있습니다.</small>
            </div>
            <div className="el-preview-result">
              <span className="eyebrow">답변 기록 · 실행 전</span>
              <div className="el-empty-document">
                <Files size={25} />
                <p>검색 결과가 여기에 기록됩니다.</p>
              </div>
              <ol>
                <li>
                  <span>1</span>문서에서 답변 준비
                </li>
                <li>
                  <span>2</span>원문의 금액 또는 조건 수정
                </li>
                <li>
                  <span>3</span>이전 답변의 사용 가능 여부 확인
                </li>
              </ol>
            </div>
          </div>
          <div className="el-preview-foot">
            무료 Python 서버의 첫 연결은 최대 90초 걸릴 수 있습니다. 연결이
            끝나면 실제 검색과 검증을 실행합니다.
          </div>
        </div>
      )}
      <div className="el-status" role="status" aria-live="polite">
        {locked ? (
          <>
            <LoaderCircle className="spin" size={16} />
            {busy}
            {!state ? " · 무료 서버가 시작 중일 수 있습니다." : ""}
          </>
        ) : (
          notice
        )}
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} />
          {error}
        </div>
      )}
      {state && (
        <>
          <ol className="el-steps" aria-label="실험 순서">
            <li>
              <span>01</span>답변 준비
            </li>
            <li>
              <span>02</span>원문 수정
            </li>
            <li>
              <span>03</span>사용 거절 확인
            </li>
            <li>
              <span>04</span>검증 후 다시 검색
            </li>
          </ol>
          <div className="el-workbench">
            <section className="el-source">
              <div className="el-section-head">
                <span className="eyebrow">지금의 원문</span>
                <span className="el-tag">SOURCE / v{source?.revision}</span>
              </div>
              <label htmlFor="evidence-source">근거 문서</label>
              <select
                id="evidence-source"
                value={sourceId}
                disabled={locked}
                onChange={(e) => {
                  setSourceId(e.target.value);
                  setText(
                    state.sources.find((s) => s.source_id === e.target.value)!
                      .text,
                  );
                  setQuery(queries[e.target.value]);
                  setValidation(null);
                }}
              >
                {state.sources.map((s) => (
                  <option key={s.source_id} value={s.source_id}>
                    {s.title}
                    {s.deleted ? " · 삭제됨" : ""}
                  </option>
                ))}
              </select>
              <label htmlFor="evidence-text">문서 본문</label>
              <textarea
                id="evidence-text"
                maxLength={600}
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={locked}
                rows={6}
              />
              <small>
                숫자나 조건을 직접 바꾸세요. 수정은 실제 저장된 문서에
                반영됩니다.
              </small>
              <div className="el-actions">
                <button
                  className="ink-button"
                  disabled={locked || !text.trim()}
                  onClick={() => edit(false)}
                >
                  수정 반영
                </button>
                <button
                  className="text-button"
                  disabled={locked || source?.deleted}
                  onClick={() => edit(true)}
                >
                  문서 삭제
                </button>
              </div>
              <div
                className={`el-index ${state.index_stale ? "needs-rebuild" : ""}`}
                data-testid="index-freshness"
              >
                <span className="el-dot" />
                {state.index_stale
                  ? "검색 인덱스 재구축 필요"
                  : "검색 인덱스 최신"}
                <small>
                  사용 중인 배포{" "}
                  <b data-testid="release-epoch">
                    r{state.active_release.release_epoch}
                  </b>
                </small>
              </div>
            </section>
            <section className="el-answer">
              <div className="el-section-head">
                <span className="eyebrow">답변에 쓰인 근거</span>
                <span className="el-tag">
                  RECEIPT / {receipt ? `r${receipt.release_epoch}` : "—"}
                </span>
              </div>
              <div
                className="el-products"
                role="group"
                aria-label="공통 기능을 사용하는 제품"
              >
                <button
                  className={product === "answer" ? "selected" : ""}
                  aria-pressed={product === "answer"}
                  disabled={locked}
                  onClick={() => setProduct("answer")}
                >
                  상담 답변 초안
                </button>
                <button
                  className={product === "checklist" ? "selected" : ""}
                  aria-pressed={product === "checklist"}
                  disabled={locked}
                  onClick={() => setProduct("checklist")}
                >
                  업무 체크리스트
                </button>
              </div>
              <label htmlFor="evidence-query">질문</label>
              <div className="el-query">
                <input
                  id="evidence-query"
                  value={query}
                  maxLength={160}
                  disabled={locked}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  className="ink-button"
                  disabled={
                    locked || query.trim().length < 2 || state.index_stale
                  }
                  onClick={prepare}
                >
                  답변 준비
                  <ArrowRight size={15} />
                </button>
              </div>
              {state.index_stale && (
                <small className="el-rebuild-help">
                  아래 배포 검증에서 정상 후보를 평가·적용하면 새 문서를 검색할
                  수 있습니다.
                </small>
              )}
              <div className={`el-receipt ${receipt ? "has-receipt" : ""}`}>
                {receipt ? (
                  <>
                    <div className="el-receipt-head">
                      <span>
                        {receipt.product === "answer"
                          ? "상담 답변 초안"
                          : "업무 체크리스트"}{" "}
                        · 저장 당시 내용
                      </span>
                      <small>{receipt.retrieval_ms.toFixed(2)}ms 검색</small>
                    </div>
                    <p data-testid="evidence-output">{receipt.output}</p>
                    <div className="el-citation">
                      {receipt.references.map((ref) => (
                        <span key={ref.source_id}>
                          ↳ {ref.title} <b>v{ref.revision}</b>
                        </span>
                      ))}
                      <small>문서에서 직접 추출한 결과 · LLM 생성 아님</small>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="el-quote">“</span>
                    <p>아직 준비한 답변이 없습니다.</p>
                    <small>
                      질문을 보내면 실제 Python 검색 결과가 여기에 기록됩니다.
                    </small>
                  </>
                )}
              </div>
              <button
                className="el-use"
                disabled={locked || !receipt}
                onClick={() =>
                  receipt &&
                  void run(
                    "현재 근거 검증 중",
                    (a, s) => a.validate(s, receipt.id),
                    (value) => setValidation(value),
                  )
                }
              >
                <ShieldCheck size={18} />
                지금 사용해도 되는지 확인
                <ArrowRight size={16} />
              </button>
              {checked && (
                <div
                  data-testid="evidence-validation"
                  className={`el-validation ${checked.valid ? "valid" : "refused"}`}
                  role="status"
                >
                  <strong>
                    {checked.valid ? (
                      <Check size={21} />
                    ) : (
                      <TriangleAlert size={21} />
                    )}{" "}
                    {checked.valid ? "사용 가능" : "사용 거절"}
                  </strong>
                  <p>{reasons[checked.reason] || checked.reason}</p>
                  <small>
                    {new Date(checked.checked_at * 1000).toLocaleTimeString(
                      "ko-KR",
                    )}{" "}
                    확인 시점 기준 · 외부 업무 실행을 보장하지 않음
                  </small>
                </div>
              )}
              {expired && (
                <p className="el-expired">
                  이 기록의 유효기간이 지났습니다. 새 답변을 준비하세요.
                </p>
              )}
              {receipt && (
                <button
                  className="text-button el-export"
                  onClick={() =>
                    download(receipt, "recheck-evidence-receipt.json")
                  }
                >
                  <Download size={14} />
                  근거 기록 JSON
                </button>
              )}
            </section>
          </div>
          <section className="el-release">
            <div className="el-release-intro">
              <span className="eyebrow">두 번째 실험 / 안전한 모델 교체</span>
              <h2>모델·인덱스 배포 검증</h2>
              <p>
                같은 질문으로 후보를 실제 평가합니다. 모델과 인덱스가 맞아도
                검색 품질이 나빠지면 배포를 멈춥니다.
              </p>
              <div className="el-pair">
                <span>
                  MODEL
                  <code>{state.active_release.model_hash.slice(0, 8)}</code>
                </span>
                <span>↔</span>
                <span>
                  INDEX EXPECTS
                  <code>
                    {state.active_release.index_model_hash.slice(0, 8)}
                  </code>
                </span>
              </div>
              <small>
                모델·인덱스는 검증 후 하나의 배포로 함께 교체됩니다.
              </small>
            </div>
            <div className="el-release-bench">
              <label htmlFor="evidence-candidate">배포 후보</label>
              <select
                id="evidence-candidate"
                value={candidate}
                disabled={locked}
                onChange={(e) => {
                  setCandidate(e.target.value as Candidate);
                  setReport(null);
                }}
              >
                <option value="paired">
                  정상 후보 · 모델과 인덱스 함께 교체
                </option>
                <option value="mismatch">
                  실패 주입 · 모델만 바꿔 인덱스와 불일치
                </option>
                <option value="regressed">
                  실패 주입 · 질문 구분 능력을 잃은 모델
                </option>
              </select>
              <button
                className="ink-button"
                disabled={locked}
                onClick={evaluate}
              >
                후보 평가
                <ArrowRight size={15} />
              </button>
              {report ? (
                <div className="el-report" data-testid="release-report">
                  <div
                    className="el-report-verdict"
                    data-testid="release-verdict"
                  >
                    <span className={report.passed ? "el-pass" : "el-fail"}>
                      {staleReport
                        ? "재평가 필요"
                        : report.passed
                          ? "배포 가능"
                          : "배포 차단"}
                    </span>
                    <small>{report.sample_count}회 실제 검색 · 합성 문서</small>
                  </div>
                  <div className="el-measures">
                    <div>
                      <span>Recall@1</span>
                      <strong>
                        {(report.recall_at_1 * 100).toFixed(0)}
                        <small>%</small>
                      </strong>
                      <small>정답 문서가 첫 번째인 비율</small>
                    </div>
                    <div>
                      <span>검색 p95</span>
                      <strong>
                        {report.p95_ms.toFixed(2)}
                        <small>ms</small>
                      </strong>
                      <small>워밍업 이후 검색만 측정</small>
                    </div>
                  </div>
                  <ul className="el-gates">
                    {Object.entries(gates).map(([key, label]) => (
                      <li key={key}>
                        <span>
                          {report.failed_gates.includes(key) ? "×" : "✓"}{" "}
                          {label}
                        </span>
                        <small>
                          {key === "model_index_match"
                            ? "모델 식별값 일치"
                            : key === "retrieval_quality"
                              ? "90% 이상"
                              : key === "quality_regression"
                                ? "기준선보다 5%p 이내 하락"
                                : "p95 50ms 이하"}
                        </small>
                      </li>
                    ))}
                  </ul>
                  {staleReport && (
                    <p className="el-expired">
                      이미 적용되었거나 다른 배포로 바뀐 평가입니다. 다시
                      평가하세요.
                    </p>
                  )}
                  <div className="el-actions">
                    <button
                      className="ink-button"
                      disabled={locked || !report.passed || staleReport}
                      onClick={() =>
                        void run(
                          "모델·인덱스 적용 중",
                          (a, s) => a.promote(s, report.id),
                          () => {
                            setNotice(
                              "04 · 새 인덱스가 적용되었습니다. 위에서 답변을 다시 준비해 바뀐 내용을 확인하세요.",
                            );
                          },
                        )
                      }
                    >
                      검증된 모델·인덱스 적용
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        download(report, "recheck-release-report.json")
                      }
                    >
                      <Download size={14} />
                      평가 원본 JSON
                    </button>
                  </div>
                </div>
              ) : (
                <div className="el-report-empty">
                  <ArrowDown size={20} />
                  <p>
                    후보를 고르고 평가하면
                    <br />
                    통과 여부와 실측값을 확인할 수 있습니다.
                  </p>
                </div>
              )}
              <p className="el-measure-note">
                프로젝트 자체 기준입니다. 문서 4개·질문 8개의 어휘 검색
                실험으로, 토스뱅크 SLA나 대규모 검색 성능을 뜻하지 않습니다.
                삭제한 문서의 질문은 평가에서 제외됩니다.
              </p>
            </div>
          </section>
          <section className="el-records">
            <div>
              <span className="eyebrow">실제로 바뀐 것</span>
              <h3>문서 변경 기록</h3>
            </div>
            <div>
              {state.events.length ? (
                state.events.slice(0, 5).map((e, i) => (
                  <div
                    className="el-event"
                    key={`${e.source_id}-${e.revision}`}
                  >
                    <span>
                      {String(state.events.length - i).padStart(2, "0")}
                    </span>
                    <p>
                      {
                        state.sources.find((s) => s.source_id === e.source_id)
                          ?.title
                      }{" "}
                      <b>v{e.revision}</b>
                    </p>
                    <small>
                      {e.operation === "delete" ? "삭제" : "수정"} ·{" "}
                      {new Date(e.at * 1000).toLocaleTimeString("ko-KR")}
                    </small>
                  </div>
                ))
              ) : (
                <p>
                  아직 변경이 없습니다. 원문을 수정하면 실제 이벤트가
                  기록됩니다.
                </p>
              )}
            </div>
          </section>
        </>
      )}
      <section className="el-foundation">
        <div>
          <span className="eyebrow">자료에서 구현으로</span>
          <h3>공통 API와 Python SDK</h3>
          <p>
            답변 초안과 업무 체크리스트는 같은 근거 기록 API를 사용합니다.
            저장소에는 두 제품에서 재사용하는 Python SDK와 실행 예제도 있습니다.
            검색·기록·사용 직전 검증을 제품마다 다시 만들지 않습니다.
          </p>
        </div>
        <div className="el-reading">
          <a
            href="https://toss.tech/article/tech_talk_talk_3"
            target="_blank"
            rel="noreferrer"
          >
            토스증권 검색·추천 발표 <ArrowUpRight size={15} />
            <small>모델과 인덱스의 버전 일치 → 실제 교체·불일치 실험</small>
          </a>
          <a
            href="https://toss.im/slash-22/sessions/3-2"
            target="_blank"
            rel="noreferrer"
          >
            SLASH22 ML 서비스 발표 <ArrowUpRight size={15} />
            <small>공통 서빙 기능 → JSON 모델 아티팩트와 Python SDK</small>
          </a>
          <a
            href="https://labhub.hopto.org/blog/culture/2026-03-21-tossbank-ml-backend-engineer-study-guide"
            target="_blank"
            rel="noreferrer"
          >
            LabHub 학습 가이드 <ArrowUpRight size={15} />
            <small>측정과 선택 근거 → 품질·지연시간 배포 기준</small>
          </a>
        </div>
      </section>
    </section>
  );
}
