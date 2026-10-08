import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Clock3,
  Download,
  FileJson,
  LoaderCircle,
  Play,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  Wifi,
  X,
} from "lucide-react";
import { Simulation } from "./simulation";
import { LiveApi } from "./api";
import {
  comparisonConfirmed,
  currentValidation,
  raceReproduced,
} from "./presentation";
import type {
  Adapter,
  DecisionInput,
  Mutation,
  Receipt,
  Session,
  Validation,
} from "./types";
type Tab = "lab" | "receipts" | "architecture" | "story";
type Event = {
  id: string;
  at: string;
  title: string;
  detail: string;
  tone: "ok" | "warning" | "neutral";
};
const reasons: Record<string, string> = {
  current: "현재 버전과 유효기간을 확인했습니다.",
  no_current_warning: "현재 확인된 주의 신호가 없습니다.",
  feature_changed: "수취인 정보가 변경되었습니다.",
  expired: "판단의 유효기간이 만료되었습니다.",
  expired_at_issue: "추론 완료 전에 판단이 만료되었습니다.",
  feature_stale: "입력 정보의 최신성 확인이 필요합니다.",
  risk_signal: "추가 확인이 필요한 주의 신호가 있습니다.",
  overloaded: "모델 서버의 수용 한도를 초과했습니다.",
  model_version_mismatch: "요청 모델과 실제 모델 버전이 다릅니다.",
  request_cancelled: "요청이 취소되었습니다.",
  valid: "현재 버전과 유효기간을 확인했습니다.",
  versions_changed: "입력 정보 또는 정책·모델 버전이 변경되었습니다.",
  receipt_expired: "판단의 유효기간이 만료되었습니다.",
  deadline_exceeded: "300ms 시간 예산을 초과했습니다.",
  model_unavailable: "모델 서버가 응답할 수 없습니다.",
  no_risk_signal: "현재 확인된 주의 신호가 없습니다.",
  risk_threshold: "추가 확인이 필요한 주의 신호가 있습니다.",
};
const getReason = (reason: string) => reasons[reason] || reason;
const diff = (r: Receipt, s: Session) =>
  r.feature_version !== s.feature_version ||
  r.policy_version !== s.policy_version ||
  r.model_version !== s.model_version;
const money = (n: number) => new Intl.NumberFormat("ko-KR").format(n);
const short = (s: string) => s.slice(0, 8);
const clock = (s: string) =>
  new Date(s).toLocaleTimeString("ko-KR", { hour12: false });
const walkthrough = [
  {
    title: "정상 판단",
    text: "확인 요청을 보내 고객 안내와 판단 기록을 연결합니다.",
  },
  {
    title: "정보 변경",
    text: "수취인 정보를 바꿉니다. 생성된 답도 현재 버전과 다르면 사용할 수 없습니다.",
  },
  {
    title: "모델 장애",
    text: "시간 예산을 넘기는 상황에서 실패 원인을 확인합니다.",
  },
  {
    title: "기준선 비교",
    text: "추론 중 정보를 바꾸고, 재검증을 생략한 기준선과 보호 장치를 비교합니다.",
  },
];
function exportReceipt(receipt: Receipt) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `recheck-${receipt.id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
export default function App() {
  const [tab, setTab] = useState<Tab>("lab");
  const [mode, setMode] = useState<"browser" | "live">("browser");
  const [session, setSession] = useState<Session | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState("");
  const [amount, setAmount] = useState(150000);
  const [delay, setDelay] = useState(0);
  const [fault, setFault] = useState<DecisionInput["fault"]>("none");
  const [protectedMode, setProtected] = useState(true);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [validating, setValidating] = useState(false);
  const [detail, setDetail] = useState<Receipt | null>(null);
  const [guided, setGuided] = useState<number | null>(null);
  const [base, setBase] = useState(
    () => localStorage.getItem("recheck-api-base") || "",
  );
  const [showConnect, setShowConnect] = useState(false);
  const [, tick] = useState(0);
  const api = useRef<Adapter>(new Simulation());
  const validationEpoch = useRef(0);
  const receiptAmounts = useRef<Record<string, number>>({});
  const generation = useRef(0);
  const sessionRef = useRef<Session | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const addEvent = (
    title: string,
    detail: string,
    tone: Event["tone"] = "neutral",
  ) =>
    setEvents((items) =>
      [
        {
          id: crypto.randomUUID(),
          at: new Date().toISOString(),
          title,
          detail,
          tone,
        },
        ...items,
      ].slice(0, 18),
    );
  const newSession = async (adapter: Adapter = api.current) => {
    const gen = ++generation.current;
    validationEpoch.current++;
    setBusy(false);
    setMutating(false);
    setValidating(false);
    setDetail(null);
    receiptAmounts.current = {};
    setError("");
    setValidation(null);
    setReceipts([]);
    setEvents([]);
    setSession(null);
    setObservedAt(null);
    sessionRef.current = null;
    try {
      const next = await adapter.createSession();
      if (gen !== generation.current) return;
      sessionRef.current = next;
      setSession(next);
      setObservedAt(new Date().toISOString());
      addEvent(
        "새 세션 준비",
        "이 세션의 특징·정책·모델 버전을 독립적으로 관리합니다.",
      );
    } catch (e) {
      if (gen === generation.current)
        setError(e instanceof Error ? e.message : "세션을 생성할 수 없습니다.");
    }
  };
  useEffect(() => {
    void newSession();
    const timer = setInterval(() => tick((x) => x + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (detail) dialog.current?.showModal();
    else if (dialog.current?.open) dialog.current.close();
  }, [detail]);
  const current = receipts[0] || null;
  const shownAmount = current
    ? (receiptAmounts.current[current.id] ?? amount)
    : amount;
  const stale = !!(current && session && diff(current, session));
  const expired = !!(current && Date.now() >= Date.parse(current.expires_at));
  const shownValidation = currentValidation(
    validation,
    current,
    session,
    Date.now(),
  );
  const blocked = !!(
    current &&
    (current.status !== "clear" || (current.protected && (stale || expired)))
  );
  const unsafe = !!(
    current &&
    !current.protected &&
    current.status === "clear" &&
    (stale || expired)
  );
  const status = busy
    ? "checking"
    : !current
      ? "ready"
      : blocked
        ? "review"
        : unsafe
          ? "unsafe"
          : "clear";
  const statusText = {
    checking: "현재 정보를 확인하고 있어요",
    ready: "보내기 전, 한 번 더 확인해요",
    review:
      current?.status === "invalidated" || stale
        ? "정보가 바뀌어 다시 확인이 필요해요"
        : "추가 확인이 필요해요",
    unsafe: "오래된 답이 통과했어요",
    clear: "현재 확인된 주의 신호가 없어요",
  }[status];
  const mutate = async (kind: Mutation) => {
    const s = sessionRef.current;
    if (!s) return;
    const gen = generation.current;
    setMutating(true);
    validationEpoch.current++;
    setValidation(null);
    setError("");
    try {
      const versions = await api.current.mutate(s.session_id, kind);
      if (gen !== generation.current) return;
      const updated = { ...s, ...versions };
      sessionRef.current = updated;
      setSession(updated);
      setObservedAt(new Date().toISOString());
      setValidation(null);
      addEvent(
        {
          feature: "수취인 정보 변경",
          policy: "정책 버전 갱신",
          model: "활성 모델 교체",
        }[kind],
        `feature v${versions.feature_version} · policy v${versions.policy_version} · ${versions.model_version}`,
        "warning",
      );
      return updated;
    } catch (e) {
      if (gen === generation.current)
        setError(e instanceof Error ? e.message : "변경 요청 실패");
    } finally {
      if (gen === generation.current) setMutating(false);
    }
  };
  const run = async (overrides: Partial<DecisionInput> = {}) => {
    const s = sessionRef.current;
    if (!s) return;
    const gen = generation.current;
    setBusy(true);
    validationEpoch.current++;
    setValidating(false);
    setError("");
    setValidation(null);
    const body: DecisionInput = {
      amount,
      recipient: "demo-recipient",
      idempotency_key: crypto.randomUUID(),
      delay_ms: delay,
      fault,
      protected: protectedMode,
      ...overrides,
    };
    addEvent(
      "판단 요청 시작",
      `${money(body.amount)}원 · ${body.protected ? "보호 장치 적용" : "재검증 생략 기준선"} · feature v${s.feature_version}`,
    );
    try {
      const r = await api.current.decide(s.session_id, body);
      if (gen !== generation.current) return;
      receiptAmounts.current[r.id] = body.amount;
      setReceipts((items) => [r, ...items].slice(0, 30));
      addEvent(
        r.status === "clear"
          ? "판단 기록 생성"
          : r.status === "invalidated"
            ? "버전 불일치 감지"
            : "추가 확인으로 전환",
        getReason(r.reason),
        r.status === "clear" ? "ok" : "warning",
      );
      return r;
    } catch (e) {
      if (gen === generation.current) {
        setError(e instanceof Error ? e.message : "연결 오류");
        addEvent(
          "API 요청 실패",
          "연결 상태를 확인하세요. 실행 모드는 유지됩니다.",
          "warning",
        );
      }
    } finally {
      if (gen === generation.current) setBusy(false);
    }
  };
  const race = async (protection = protectedMode, raceAmount = amount) => {
    const gen = generation.current;
    setFault("none");
    setDelay(220);
    const pending = run({
      delay_ms: 220,
      fault: "none",
      protected: protection,
      amount: raceAmount,
    });
    await new Promise((resolve) => setTimeout(resolve, 70));
    if (gen !== generation.current) return;
    const mutation = await mutate("feature");
    const receipt = await pending;
    return raceReproduced(receipt, mutation) ? receipt : undefined;
  };
  const validate = async () => {
    if (!session || !current) return;
    const gen = generation.current;
    const epoch = validationEpoch.current;
    setValidating(true);
    setError("");
    try {
      const result = await api.current.validate(session.session_id, current.id);
      if (gen !== generation.current || epoch !== validationEpoch.current)
        return;
      setValidation(result);
      addEvent(
        result.valid ? "사용 시점 검증 통과" : "사용 시점 검증 거절",
        getReason(result.reason),
        result.valid ? "ok" : "warning",
      );
    } catch (e) {
      if (gen === generation.current)
        setError(e instanceof Error ? e.message : "검증 요청 실패");
    } finally {
      if (gen === generation.current) setValidating(false);
    }
  };
  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      const live = new LiveApi(base);
      await live.health();
      api.current = live;
      setMode("live");
      localStorage.setItem("recheck-api-base", base);
      setShowConnect(false);
      await newSession(live);
    } catch (e) {
      setError(e instanceof Error ? e.message : "API 연결 실패");
    } finally {
      setConnecting(false);
    }
  };
  const startGuide = () => {
    setGuided(0);
    setTab("lab");
    setAmount(150000);
    setDelay(0);
    setFault("none");
    setProtected(true);
    void newSession();
  };
  const step = async () => {
    if (guided === null) return;
    const gen = generation.current;
    let progressed = false;
    if (guided === 0) {
      setAmount(150000);
      setProtected(true);
      setFault("none");
      setDelay(0);
      progressed = !!(await run({
        amount: 150000,
        protected: true,
        fault: "none",
        delay_ms: 0,
      }));
    } else if (guided === 1) progressed = !!(await mutate("feature"));
    else if (guided === 2) {
      setFault("timeout");
      progressed = !!(await run({
        amount: 150000,
        fault: "timeout",
        protected: true,
      }));
    } else {
      setAmount(150000);
      setProtected(false);
      const baseline = await race(false, 150000);
      if (gen !== generation.current) return;
      if (!baseline) {
        addEvent(
          "경쟁 조건 재현 확인 필요",
          "정보 변경이 스냅샷보다 먼저 반영되었거나 요청이 실패했습니다. 타임라인과 오류를 확인하고 다시 실행하세요.",
          "warning",
        );
        return;
      }
      setProtected(true);
      const protectedReceipt = await race(true, 150000);
      if (gen !== generation.current) return;
      if (comparisonConfirmed(baseline, protectedReceipt)) {
        addEvent(
          "보호 장치 전후 비교 완료",
          "기준선은 오래된 결과를 생성했고, 보호 장치는 같은 버전 변경을 무효화했습니다.",
          "ok",
        );
        progressed = true;
      } else {
        addEvent(
          "비교 결과 확인 필요",
          "주의 신호 없음 기준선과 버전 변경 무효화 결과가 모두 확인되지 않았습니다. 기록과 오류를 확인하세요.",
          "warning",
        );
      }
    }
    if (progressed && gen === generation.current)
      setGuided(guided < 3 ? guided + 1 : null);
  };

  const sections = [
    { id: "lab" as Tab, label: "인터랙티브 데모" },
    { id: "receipts" as Tab, label: "판단 기록" },
    { id: "architecture" as Tab, label: "서버 설계" },
    { id: "story" as Tab, label: "지원자의 관점" },
  ];
  const versions = [
    {
      key: "F",
      label: "입력 특징",
      before: current ? `v${current.feature_version}` : "—",
      after: session ? `v${session.feature_version}` : "—",
      changed:
        !!current &&
        !!session &&
        current.feature_version !== session.feature_version,
    },
    {
      key: "P",
      label: "판단 정책",
      before: current ? `v${current.policy_version}` : "—",
      after: session ? `v${session.policy_version}` : "—",
      changed:
        !!current &&
        !!session &&
        current.policy_version !== session.policy_version,
    },
    {
      key: "M",
      label: "활성 모델",
      before: current?.model_version || "—",
      after: session?.model_version || "—",
      changed:
        !!current &&
        !!session &&
        current.model_version !== session.model_version,
    },
  ];
  const issueState = !current
    ? "미발급"
    : current.status === "clear"
      ? "CLEAR"
      : current.status === "invalidated"
        ? "INVALIDATED"
        : "REVIEW";
  const traceExtent = current
    ? Math.max(
        0,
        current.latency_ms,
        ...current.spans.map((span) => span.start_ms + span.duration_ms),
      )
    : 0;
  const traceMaximum = Math.max(1, traceExtent);
  const reset = () => {
    setDelay(0);
    setFault("none");
    setProtected(true);
    setAmount(150000);
    setGuided(null);
    void newSession();
  };

  return (
    <div className="recheck-workbench">
      <header className="site-header">
        <button
          className="wordmark"
          aria-label="RECHECK 홈"
          onClick={() => setTab("lab")}
        >
          recheck<span>↗</span>
        </button>
        <nav aria-label="주 메뉴">
          {sections.map(({ id, label }, index) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              aria-current={tab === id ? "page" : undefined}
              aria-label={label}
              onClick={() => setTab(id)}
            >
              <span className="nav-index">0{index + 1}</span>
              {label}
            </button>
          ))}
        </nav>
        <span className="edition-label">A TEMPORAL DECISION EXPERIMENT</span>
      </header>
      <main>
        <section className="page-intro">
          <div className="intro-title">
            <span className="eyebrow">
              RECHECK /{" "}
              {tab === "lab"
                ? "01. VERSION INTEGRITY"
                : tab === "receipts"
                  ? "02. DECISION RECORD"
                  : tab === "architecture"
                    ? "03. SYSTEM DESIGN"
                    : "04. ENGINEERING APPROACH"}
            </span>
            <h1>
              {tab === "lab" ? (
                <>
                  답은 그대로.
                  <br />
                  <em>상황은 달라졌다.</em>
                </>
              ) : tab === "receipts" ? (
                <>
                  판단이 남긴
                  <br />
                  <em>근거를 읽습니다.</em>
                </>
              ) : tab === "architecture" ? (
                <>
                  기다리는 연산.
                  <br />
                  <em>짧게 끝내는 검증.</em>
                </>
              ) : (
                <>
                  반복되는 오류를,
                  <br />
                  <em>다시 막는 데까지.</em>
                </>
              )}
            </h1>
          </div>
          <div className="intro-context">
            <p>
              {tab === "lab" ? (
                <>
                  AI가 답을 만드는 사이, 입력 정보가 바뀌면?
                  <br />
                  추론 당시의 기록과 현재 버전을 직접 비교하세요.
                </>
              ) : tab === "receipts" ? (
                <>
                  기록은 생성 당시의 답을 보존합니다.
                  <br />
                  지금 사용할 수 있는지는 따로 검증합니다.
                </>
              ) : tab === "architecture" ? (
                <>
                  시간 예산, 상태 일관성, 실패의 근거.
                  <br />
                  하나의 요청에서 세 가지를 함께 확인합니다.
                </>
              ) : (
                <>
                  Python · LLM · AI/ML을 경험한 신입 개발자.
                  <br />
                  AI의 답을 직접 조사하고, 해결 방법을 비교합니다.
                </>
              )}
            </p>
            {tab === "lab" && (
              <button className="text-button guide-start" onClick={startGuide}>
                <Play size={14} />
                90초 체험 시작
                <ArrowRight size={15} />
              </button>
            )}
          </div>
        </section>
        <div className={`mode-banner ${mode === "live" ? "is-live" : ""}`}>
          <div className="mode-label">
            <span className="mode-indicator" />
            {mode === "browser" ? "브라우저 시뮬레이션" : "실제 Python 서버"}
            <span className="mode-note">
              {mode === "browser"
                ? "로컬 상태 계산 · 합성 규칙 · Python 추론이나 서버 성능 측정이 아닙니다."
                : "HTTP API와 독립 모델 서버의 실제 응답을 표시합니다."}
            </span>
          </div>
          <div className="mode-actions">
            <span className="synthetic-label">
              합성 데이터 / 실제 송금 없음
            </span>
            <button
              className="text-button"
              onClick={() =>
                mode === "browser"
                  ? setShowConnect(!showConnect)
                  : ((api.current = new Simulation()),
                    setMode("browser"),
                    void newSession())
              }
            >
              {mode === "browser" ? (
                <>
                  <Wifi size={15} />
                  실제 Python 서버 연결
                </>
              ) : (
                <>
                  시뮬레이션으로 전환
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </div>
        </div>
        {showConnect && (
          <form
            className="connection-form"
            onSubmit={(event) => {
              event.preventDefault();
              void connect();
            }}
          >
            <label htmlFor="api-base">
              API 주소<small>비우면 현재 사이트 주소 사용</small>
            </label>
            <input
              id="api-base"
              type="url"
              placeholder={window.location.origin}
              value={base}
              onChange={(event) => setBase(event.target.value)}
            />
            <button className="ink-button" disabled={connecting}>
              {connecting ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Wifi size={16} />
              )}
              연결 확인
            </button>
            <button
              type="button"
              className="icon-button"
              onClick={() => setShowConnect(false)}
              aria-label="연결 설정 닫기"
            >
              <X size={18} />
            </button>
          </form>
        )}
        {error && (
          <div className="error-banner" role="alert">
            <TriangleAlert size={20} />
            <div>
              {error}
              <small>
                성공 결과를 만들거나 다른 모드로 자동 전환하지 않습니다.
              </small>
            </div>
            <button
              className="icon-button"
              onClick={() => setError("")}
              aria-label="오류 메시지 닫기"
            >
              <X size={18} />
            </button>
          </div>
        )}
        {tab === "lab" && (
          <>
            {guided !== null && (
              <section className="guided" aria-label="90초 체험 가이드">
                <span className="guide-number">
                  0{guided + 1}
                  <small>/ 04</small>
                </span>
                <div>
                  <span className="eyebrow">90 SECOND WALKTHROUGH</span>
                  <h2>{walkthrough[guided].title}</h2>
                  <p>{walkthrough[guided].text}</p>
                </div>
                <button
                  className="ink-button"
                  disabled={busy || mutating || !session}
                  onClick={() => void step()}
                >
                  {guided === 3 ? "보호 장치 전후 비교" : "이 단계 실행"}
                  <ArrowRight size={16} />
                </button>
                <button
                  className="icon-button"
                  onClick={() => setGuided(null)}
                  aria-label="체험 가이드 닫기"
                >
                  <X size={18} />
                </button>
              </section>
            )}
            <section className="instrument" aria-labelledby="instrument-title">
              <div className="instrument-heading">
                <div>
                  <span className="instrument-index">EXPERIMENT 01</span>
                  <h2 id="instrument-title">한 번의 판단, 두 개의 시간.</h2>
                </div>
                <div className="instrument-actions">
                  <button
                    className="text-button reset"
                    onClick={reset}
                    disabled={connecting}
                  >
                    <RefreshCw size={15} />
                    초기화
                  </button>
                  <button
                    className="signal-button"
                    disabled={busy || mutating || !session}
                    onClick={() => void race()}
                  >
                    {busy ? (
                      <LoaderCircle size={17} className="spin" />
                    ) : (
                      <ArrowUpRight size={19} />
                    )}
                    추론 중 변경 재현
                  </button>
                </div>
              </div>
              <div className="instrument-body">
                <div
                  className="version-canvas"
                  role="region"
                  aria-label="추론 당시와 현재 상태 비교"
                >
                  <div className="version-head">
                    <div className="axis-key">VERSION</div>
                    <div className="snapshot-heading">
                      <span className="time-label">T₀ / RECORDED</span>
                      <h3>추론 당시</h3>
                      <p>
                        {current
                          ? `판단 #${short(current.id)} · 생성 당시의 버전`
                          : "아직 판단 기록이 없습니다"}
                      </p>
                    </div>
                    <span className="axis-gap" />
                    <div className="current-heading">
                      <span className="time-label">T₁ / LAST OBSERVED</span>
                      <h3>현재</h3>
                      <p>
                        {session
                          ? `세션 ${short(session.session_id)} · 현재 활성 버전`
                          : "세션을 준비하고 있습니다"}
                      </p>
                    </div>
                  </div>
                  <div
                    className="version-ledger"
                    aria-label="추론 당시와 현재 버전 비교"
                  >
                    {versions.map((row) => (
                      <div
                        key={row.key}
                        className={`version-row ${row.changed ? "changed" : ""} ${row.key === "F" ? "feature-row" : ""}`}
                      >
                        <div className="version-key">
                          <strong>{row.key}</strong>
                          <span>{row.label}</span>
                        </div>
                        <div
                          role="group"
                          aria-label={`추론 당시 ${row.label}`}
                          className={`snapshot-version ${!current ? "unissued" : ""}`}
                        >
                          {row.before}
                        </div>
                        <span
                          className="version-arrow"
                          aria-label={row.changed ? "버전 변경" : "버전 관계"}
                        >
                          {row.changed ? "→" : "—"}
                        </span>
                        <div
                          className="live-version"
                          role="group"
                          aria-label={`현재 상태 ${row.label}`}
                        >
                          {row.after}
                          {row.changed && (
                            <span className="changed-mark">CHANGED</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="time-rail">
                    <div>
                      <span className="rail-tick" />
                      <span>생성</span>
                      <strong>
                        {current ? clock(current.created_at) : "— : — : —"}
                      </strong>
                    </div>
                    <span className="time-rail-line" />
                    <div>
                      <span className="rail-tick" />
                      <span>마지막 상태 확인</span>
                      <strong>
                        {observedAt ? clock(observedAt) : "— : — : —"}
                      </strong>
                    </div>
                    <p>
                      버전 관계를 비교하는 도식입니다. 간격은 경과 시간의 축척이
                      아닙니다.
                    </p>
                  </div>
                  <div className={`open-receipt ${current ? "issued" : ""}`}>
                    <div className="receipt-identity">
                      <span className="eyebrow">IMMUTABLE RECEIPT</span>
                      <p>
                        {current ? (
                          <>
                            <strong>{money(shownAmount)}원</strong>
                            <span>demo-recipient</span>
                          </>
                        ) : (
                          <>실행 전에는 기록을 채우지 않습니다.</>
                        )}
                      </p>
                      {current && (
                        <button
                          className="text-button"
                          onClick={() => setDetail(current)}
                        >
                          판단 JSON
                          <FileJson size={15} />
                        </button>
                      )}
                    </div>
                    <div
                      className={`receipt-stamp ${current?.status || "empty"}`}
                    >
                      <span>발급 결과</span>
                      <strong>{issueState}</strong>
                      {current && (
                        <small>
                          {current.protected
                            ? "버전 재검증 적용"
                            : "재검증 생략 기준선"}
                        </small>
                      )}
                    </div>
                  </div>
                  <div
                    className={`decision-status ${status}`}
                    aria-live="polite"
                  >
                    <span className="decision-marker" />
                    <div>
                      <span className="eyebrow">CURRENT CUSTOMER MESSAGE</span>
                      <h3>{statusText}</h3>
                      <p>
                        {busy
                          ? "추론을 기다리는 동안에도 정보와 정책은 바뀔 수 있습니다."
                          : !current
                            ? "추론 중 변경 재현을 실행하면, 실제로 바뀐 버전과 반환된 결과가 여기에 연결됩니다."
                            : unsafe
                              ? "재검증을 생략한 기준선의 오래된 답입니다. 실제 사용 검증에서는 거절됩니다."
                              : stale
                                ? "기록된 버전과 현재 버전이 다릅니다. 이전 답을 다시 사용하지 않습니다."
                                : expired
                                  ? "이 판단은 만료되었습니다. 현재 정보로 다시 확인해야 합니다."
                                  : getReason(current.reason)}
                      </p>
                    </div>
                  </div>
                </div>
                <aside className="scenario-console" aria-label="시나리오 설정">
                  <div className="console-heading">
                    <span>INPUT / CONDITIONS</span>
                    <span className="console-index">↙</span>
                  </div>
                  <label className="amount-field" htmlFor="amount">
                    다음 확인 금액
                    <div className="input-line">
                      <input
                        id="amount"
                        type="number"
                        min="1000"
                        max="10000000"
                        step="1000"
                        value={amount}
                        onChange={(event) =>
                          setAmount(
                            Math.max(
                              1000,
                              Math.min(10000000, Number(event.target.value)),
                            ),
                          )
                        }
                        disabled={busy}
                      />
                      <span>원</span>
                    </div>
                  </label>
                  <label className="delay-field" htmlFor="delay">
                    <span>
                      주입 지연<strong>{delay} ms</strong>
                    </span>
                    <input
                      id="delay"
                      type="range"
                      min="0"
                      max="1000"
                      step="20"
                      value={delay}
                      onChange={(event) => setDelay(Number(event.target.value))}
                    />
                    <span className="range-caption">
                      <span>0</span>
                      <span>예산 300ms</span>
                      <span>1,000ms</span>
                    </span>
                  </label>
                  <div className="fault-field">
                    <span className="field-label">모델 상태</span>
                    <div
                      className="segmented"
                      role="group"
                      aria-label="모델 장애 설정"
                    >
                      {(
                        [
                          { value: "none", label: "정상" },
                          { value: "timeout", label: "시간 초과" },
                          { value: "unavailable", label: "응답 불가" },
                        ] as const
                      ).map((item) => (
                        <button
                          key={item.value}
                          aria-pressed={fault === item.value}
                          className={fault === item.value ? "selected" : ""}
                          onClick={() => setFault(item.value)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="protection-control">
                    <div>
                      <span>판단 최신성 보호</span>
                      <small>
                        {protectedMode
                          ? "추론 완료 후 버전을 다시 비교"
                          : "의도적으로 취약한 기준선"}
                      </small>
                    </div>
                    <button
                      role="switch"
                      aria-checked={protectedMode}
                      aria-label="판단 최신성 보호"
                      className={`toggle ${protectedMode ? "on" : ""}`}
                      onClick={() => setProtected(!protectedMode)}
                    >
                      <span />
                    </button>
                  </div>
                  <div className="mutation-controls">
                    <span className="field-label">
                      추론 중에도 변경 가능합니다
                    </span>
                    <button
                      aria-label="수취인 정보 변경"
                      onClick={() => void mutate("feature")}
                      disabled={!session || mutating}
                    >
                      F<span>수취인 정보 변경</span>
                      <ArrowUpRight size={16} />
                    </button>
                    <button
                      aria-label="정책 갱신"
                      onClick={() => void mutate("policy")}
                      disabled={!session || mutating}
                    >
                      P<span>정책 갱신</span>
                      <ArrowUpRight size={16} />
                    </button>
                    <button
                      aria-label="모델 교체"
                      onClick={() => void mutate("model")}
                      disabled={!session || mutating}
                    >
                      M<span>모델 교체</span>
                      <ArrowUpRight size={16} />
                    </button>
                  </div>
                  <button
                    className="ink-button run-button"
                    disabled={busy || !session}
                    onClick={() => void run()}
                  >
                    {busy ? (
                      <LoaderCircle className="spin" size={17} />
                    ) : (
                      <Play size={15} fill="currentColor" />
                    )}
                    판단 요청 실행
                    <ArrowRight size={16} />
                  </button>
                  <p className="console-note">
                    합성 거래 특징을 사용합니다.
                    <br />
                    금융 안전 보증이나 송금 승인이 아닙니다.
                  </p>
                </aside>
              </div>
              <div className="validation-rail">
                <div>
                  <span className="eyebrow">THE CHECK AT USE</span>
                  <p>사용하는 순간, 다시 확인합니다.</p>
                </div>
                <button
                  className="outline-button"
                  disabled={!current || validating || busy}
                  onClick={() => void validate()}
                >
                  {validating ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <ShieldCheck size={16} />
                  )}
                  현재 판단 사용 검증
                  <ArrowRight size={16} />
                </button>
                {current && (
                  <span className={`expiry ${expired ? "expired" : ""}`}>
                    <Clock3 size={14} />
                    {expired
                      ? "유효기간 만료"
                      : `만료까지 ${Math.max(0, Math.ceil((Date.parse(current.expires_at) - Date.now()) / 1000))}초`}
                  </span>
                )}
                {shownValidation && (
                  <div
                    className={`validation-result ${shownValidation.valid ? "valid" : "invalid"}`}
                    role="status"
                  >
                    <strong>
                      {shownValidation.valid ? "사용 가능" : "사용 거절"}
                    </strong>
                    <span>{getReason(shownValidation.reason)}</span>
                  </div>
                )}
              </div>
            </section>
            <section className="trace-section" aria-labelledby="trace-title">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">
                    REQUEST RULER /{" "}
                    {mode === "browser" ? "LOCAL OBSERVATION" : "API TRACE"}
                  </span>
                  <h2 id="trace-title">답이 만들어진 과정</h2>
                </div>
                <span className="trace-state">
                  {busy
                    ? "REQUEST IN PROGRESS"
                    : current
                      ? `TRACE ${short(current.trace_id)}`
                      : "NO REQUEST YET"}
                </span>
              </div>
              {current ? (
                <>
                  <div className="trace-ruler">
                    <span>0 ms</span>
                    <span>{(traceExtent / 2).toFixed(0)} ms</span>
                    <span>{traceExtent.toFixed(0)} ms</span>
                  </div>
                  <div className="waterfall">
                    {current.spans.map((span, index) => (
                      <div
                        key={index}
                        className={`span-row ${span.status === "error" ? "span-error" : ""}`}
                      >
                        <span className="span-index">0{index + 1}</span>
                        <span className="span-name">{span.name}</span>
                        <div className="span-track">
                          <span
                            style={{
                              left: `${Math.max(0, Math.min(100, (span.start_ms / traceMaximum) * 100))}%`,
                              width: `${Math.max(0, Math.min(100, (span.duration_ms / traceMaximum) * 100))}%`,
                            }}
                            title={`${span.name}: ${span.duration_ms} ms`}
                          />
                          {span.duration_ms === 0 && (
                            <i
                              style={{
                                left: `${Math.max(0, Math.min(99.5, (span.start_ms / traceMaximum) * 100))}%`,
                              }}
                            />
                          )}
                        </div>
                        <span className="span-duration">
                          {span.duration_ms.toFixed(0)} ms
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="trace-footer">
                    <span>
                      {mode === "browser"
                        ? "브라우저 관측 시간"
                        : "API 기록 지연"}{" "}
                      <strong>{current.latency_ms.toFixed(0)} ms</strong>
                    </span>
                    <span
                      className={
                        current.status === "clear"
                          ? "recorded-color"
                          : "signal-color"
                      }
                    >
                      {current.status === "clear"
                        ? "주의 신호 없음"
                        : current.status === "invalidated"
                          ? "이전 결과 무효"
                          : "추가 확인 필요"}
                    </span>
                  </div>
                </>
              ) : (
                <div className="empty-ruler">
                  <span>01</span>
                  <span>snapshot → inference → recheck → receipt</span>
                  <p>첫 요청 전입니다. 실제 반환된 span만 표시합니다.</p>
                </div>
              )}
              <p className="trace-note">
                {mode === "browser"
                  ? "로컬 규칙과 주입 대기의 관측 시간입니다. Python 분산 추적이나 모델 성능 수치가 아닙니다. 0ms 단계는 관측된 경과 구간이 없음을 뜻합니다."
                  : "API가 반환한 span의 시작 시각과 경과 시간을 표시합니다. 지연 주입은 모델 자체 성능과 구분해야 합니다."}
              </p>
            </section>
            <section className="event-section">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">SESSION FIELD NOTES</span>
                  <h2>이 세션에서 일어난 일</h2>
                </div>
                <span>{events.length} EVENTS</span>
              </div>
              <ol className="event-list" aria-live="polite">
                {events.slice(0, 6).map((event) => (
                  <li key={event.id} className={event.tone}>
                    <time>{clock(event.at)}</time>
                    <strong>{event.title}</strong>
                    <p>{event.detail}</p>
                  </li>
                ))}
              </ol>
            </section>
          </>
        )}
        {tab === "receipts" && (
          <section className="receipts-page">
            <div className="section-heading">
              <h2>
                이 세션의 판단 기록{" "}
                <span className="count">{receipts.length}</span>
              </h2>
              <span>최근 30개 / 생성 당시 기록 보존</span>
            </div>
            {receipts.length ? (
              <div
                className="receipt-table"
                role="table"
                aria-label="판단 기록"
              >
                <div className="receipt-row table-head" role="row">
                  <span>판단 / 시각</span>
                  <span>발급 결과 · 사유</span>
                  <span>기록된 버전</span>
                  <span>보호 장치</span>
                  <span>원본</span>
                </div>
                {receipts.map((receipt) => (
                  <div className="receipt-row" key={receipt.id} role="row">
                    <div>
                      <code>#{short(receipt.id)}</code>
                      <small>{clock(receipt.created_at)}</small>
                    </div>
                    <div>
                      <strong className={`receipt-status ${receipt.status}`}>
                        {receipt.status === "clear"
                          ? "주의 신호 없음"
                          : receipt.status === "review"
                            ? "추가 확인"
                            : "무효화"}
                      </strong>
                      <small>{getReason(receipt.reason)}</small>
                    </div>
                    <div>
                      <code>
                        F{receipt.feature_version} / P{receipt.policy_version}
                      </code>
                      <small>{receipt.model_version}</small>
                    </div>
                    <span>{receipt.protected ? "적용" : "기준선"}</span>
                    <button
                      className="text-button"
                      onClick={() => setDetail(receipt)}
                    >
                      상세
                      <ArrowUpRight size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="large-empty">
                <span className="empty-number">00</span>
                <h3>아직 판단 기록이 없습니다.</h3>
                <p>첫 요청을 실행한 뒤, 그 답의 근거를 열어 보세요.</p>
                <button className="ink-button" onClick={() => setTab("lab")}>
                  데모로 이동
                  <ArrowRight size={16} />
                </button>
              </div>
            )}
            <p className="record-note">
              생성 당시의 기록은 바꾸지 않습니다. 현재 사용 가능 여부는 별도의
              검증 API로 확인합니다. 새 세션을 시작하면 화면의 기록 목록이
              초기화됩니다.
            </p>
          </section>
        )}
        {tab === "architecture" && (
          <section className="architecture-page">
            <div className="section-heading">
              <div>
                <span className="eyebrow">
                  HTTP BOUNDARIES / SHORT TRANSACTIONS
                </span>
                <h2>연산은 분리하고, 검증은 짧게.</h2>
              </div>
              <span>Python / FastAPI</span>
            </div>
            <div className="system-flow">
              <article>
                <span className="system-number">01</span>
                <h3>React UI</h3>
                <p>
                  확인 요청
                  <br />
                  사용 시점 재검증
                </p>
                <code>TypeScript</code>
              </article>
              <span className="flow-arrow">
                →<small>HTTP</small>
              </span>
              <article>
                <span className="system-number">02</span>
                <h3>API Gateway</h3>
                <p>
                  스냅샷 · 시간 예산
                  <br />
                  멱등성 · 버전 비교
                </p>
                <code>FastAPI / SQLAlchemy</code>
              </article>
              <span className="flow-arrow">
                →<small>trace context</small>
              </span>
              <article>
                <span className="system-number">03</span>
                <h3>Model Worker</h3>
                <p>
                  독립 프로세스 추론
                  <br />
                  동시 실행·대기 상한
                </p>
                <code>scikit-learn / OTel</code>
              </article>
            </div>
            <div className="storage-line">
              <span>↓ 짧은 최종 검증 트랜잭션</span>
              <strong>SQLite / PostgreSQL</strong>
              <p>
                Python 호스팅 구성: SQLite · 로컬 Docker Compose: PostgreSQL
                <br />
                GitHub Pages·브라우저 모드: 메모리 계산
              </p>
            </div>
            <div className="design-decisions">
              {[
                {
                  n: "01",
                  title: "답이 돌아온 뒤, 다시 읽기",
                  body: "추론을 기다리는 동안 DB 잠금을 잡지 않습니다. 결과가 돌아오면 현재 버전과 스냅샷을 짧은 트랜잭션에서 비교합니다.",
                  trade:
                    "추가 DB 조회의 비용으로, 오래된 결과 발급을 차단합니다.",
                },
                {
                  n: "02",
                  title: "시간 초과도 하나의 결과",
                  body: "기본 300ms는 실험 정책입니다. 타임아웃·모델 응답 불가를 숨기지 않고 각각의 원인과 추가 확인 안내로 연결합니다.",
                  trade: "확인 필요 응답을 허용하고, 무제한 대기를 방지합니다.",
                },
                {
                  n: "03",
                  title: "기술보다 먼저 재현 가능한 증거",
                  body: "합성 규칙으로 동작하는 브라우저 모드와 실제 Python 추론을 구분합니다. 구성 파일과 실측·검증 기록도 구분해 설명합니다.",
                  trade:
                    "Redis·Kafka 없이 시작하고, 측정 근거가 생길 때 확장합니다.",
                },
              ].map((item) => (
                <article key={item.n}>
                  <span>{item.n}</span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <small>{item.trade}</small>
                </article>
              ))}
            </div>
            <div className="scope-note">
              <strong>보장 범위를 분명하게.</strong>
              <p>
                버전 검증 시점 이후의 미래 변경까지 막지 않습니다. 실제 송금
                승인과 원장 커밋의 원자성은 이 프로젝트의 범위 밖입니다. 합성
                모델의 점수는 실제 사기 탐지 성능을 뜻하지 않습니다.
              </p>
            </div>
          </section>
        )}
        {tab === "story" && (
          <section className="story-page">
            <div className="story-statement">
              <span className="eyebrow">THE ENGINEER BEHIND THE QUESTION</span>
              <h2>
                AI가 만든 답을,
                <br />
                그대로 믿는 대신
                <br />
                <em>직접 확인하는 개발자.</em>
              </h2>
              <p>
                저는 Python과 LLM·AI/ML을 경험한 신입 개발자입니다. AI와 함께
                개발하며 반복되는 오류를 직접 조사하고, 서로 다른 해결 방법을
                비교해 해결해 왔습니다.
              </p>
              <p>
                RECHECK에서는 그 태도를 서버 설계로 확장합니다. 실패를 재현하고,
                원인 가설을 검증하고, 같은 오류의 재발을 막는 과정을 보여주고
                싶습니다.
              </p>
            </div>
            <div className="story-method">
              <span className="eyebrow">HOW I APPROACH A PROBLEM</span>
              {[
                {
                  n: "01",
                  title: "반복되는 증상을 재현하기",
                  text: "‘가끔 틀린다’를 ‘추론 중 정보가 바뀌면 틀린다’로 좁힙니다.",
                },
                {
                  n: "02",
                  title: "서로 다른 해결책을 비교하기",
                  text: "긴 잠금, 결과 폐기, 사용 시점 재검증의 비용과 복잡도를 따집니다.",
                },
                {
                  n: "03",
                  title: "선택을 코드와 테스트로 남기기",
                  text: "버전 스냅샷과 최종 재검증을 연결하고, 세션 격리와 경쟁 조건을 검증합니다.",
                },
                {
                  n: "04",
                  title: "확인한 것만 성과로 말하기",
                  text: "브라우저 모사와 실측을 구분하고, AI의 도움과 직접 검토한 판단을 설명합니다.",
                },
              ].map((item) => (
                <div key={item.n}>
                  <span>{item.n}</span>
                  <section>
                    <h3>{item.title}</h3>
                    <p>{item.text}</p>
                  </section>
                </div>
              ))}
            </div>
            <div className="contribution">
              <span className="eyebrow">WHERE I WANT TO CONTRIBUTE</span>
              <h3>
                AI 기능을 붙이는 팀들이,
                <br />
                같은 안전장치를 매번 다시 만들지 않도록.
              </h3>
              <p>
                시간 예산, 최신성 검증, 장애 시 응답, 관측 방법을 공통 서버 구성
                요소로 제공하는 데 기여하고 싶습니다. 입사 후에는 현행 구조와
                실제 필요를 먼저 확인하겠습니다.
              </p>
              <small>
                이 프로젝트는 실제 은행 운영 경력이 아닌, 설계·구현·검증을
                보여주는 지원 프로젝트입니다.
              </small>
            </div>
          </section>
        )}
        <footer>
          <span>
            RECHECK<span className="footer-mark">↗</span>
          </span>
          <p>추론의 성공 ≠ 판단의 유효성</p>
          <small>BUILT TO BE QUESTIONED.</small>
        </footer>
      </main>
      <dialog
        ref={dialog}
        className="receipt-dialog"
        aria-labelledby="receipt-title"
        onClose={() => setDetail(null)}
      >
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">DECISION RECEIPT / SOURCE RECORD</span>
            <h2 id="receipt-title">판단의 근거를 열어 봅니다.</h2>
          </div>
          <button
            className="icon-button"
            onClick={() => dialog.current?.close()}
            aria-label="판단 상세 닫기"
          >
            <X size={22} />
          </button>
        </div>
        {detail && (
          <>
            <div className="dialog-meta">
              <code>#{short(detail.id)}</code>
              <span>
                {detail.protected ? "보호 장치 적용" : "재검증 생략 기준선"}
              </span>
              <span>
                {mode === "browser" ? "브라우저 시뮬레이션" : "실제 API 기록"}
              </span>
            </div>
            <pre>{JSON.stringify(detail, null, 2)}</pre>
            <div className="dialog-footer">
              <span>버전 · 사유 · trace를 함께 기록합니다.</span>
              <button
                className="ink-button"
                onClick={() => exportReceipt(detail)}
              >
                <Download size={16} />
                JSON 다운로드
              </button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}
