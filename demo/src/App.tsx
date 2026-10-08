import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronRight,
  Clock3,
  Code2,
  Download,
  FileJson,
  FlaskConical,
  GitBranch,
  History,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Network,
  Play,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Sparkles,
  Terminal,
  Timer,
  TriangleAlert,
  Wifi,
  X,
} from "lucide-react";
import { Simulation } from "./simulation";
import { LiveApi } from "./api";
import { comparisonConfirmed, currentValidation, raceReproduced } from "./presentation";
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
    sessionRef.current = null;
    try {
      const next = await adapter.createSession();
      if (gen !== generation.current) return;
      sessionRef.current = next;
      setSession(next);
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
  const shownAmount =
    current && !busy ? (receiptAmounts.current[current.id] ?? amount) : amount;
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
    { id: "lab" as Tab, label: "인터랙티브 데모", icon: FlaskConical },
    { id: "receipts" as Tab, label: "판단 기록", icon: History },
    { id: "architecture" as Tab, label: "서버 설계", icon: Network },
    { id: "story" as Tab, label: "지원자의 관점", icon: Code2 },
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => setTab("lab")}
          aria-label="RECHECK 홈"
        >
          <span className="brand-mark">
            <CheckCheck size={23} />
          </span>
          recheck<span className="brand-dot">.</span>
        </button>
        <div className="sidebar-tag">ML SERVING LAB</div>
        <div className="nav-label">EXPLORE</div>
        <nav aria-label="주 메뉴">
          {sections.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              aria-current={tab === id ? "page" : undefined}
              aria-label={label}
              onClick={() => setTab(id)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {tab === id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="tiny-index">01 / ENGINEERING QUESTION</span>
          <p>
            모델이 답한 뒤에도,
            <br />그 답을 믿을 수 있을까?
          </p>
          <span className="sidebar-rule" />
          <small>최신성 · 시간 예산 · 추적</small>
        </div>
        <div className="sidebar-bottom">
          <span className="status-dot" />
          <span>INTERVIEW EDITION</span>
          <small>Python · AI/ML</small>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span className="breadcrumb">
            RECHECK <ChevronRight size={13} />
            <span>{sections.find((s) => s.id === tab)?.label}</span>
          </span>
          <div className="top-meta">
            <span className="synthetic">
              <FlaskConical size={12} /> 합성 데이터
            </span>
            <span className="edition">PORTFOLIO / 2026</span>
          </div>
        </header>
        <div className="content">
          <section className="hero">
            <div className="hero-eyebrow">
              <span /> FROM INFERENCE TO TRUST
            </div>
            <div className="hero-row">
              <div>
                <h1>
                  {tab === "lab" ? (
                    <>
                      AI의 답에도,
                      <br />
                      유효기간이 있습니다<span className="accent">.</span>
                    </>
                  ) : tab === "receipts" ? (
                    <>
                      답은 사라져도,
                      <br />
                      근거는 남아야 합니다<span className="accent">.</span>
                    </>
                  ) : tab === "architecture" ? (
                    <>
                      빠른 응답과 올바른 답을,
                      <br />
                      함께 설계합니다<span className="accent">.</span>
                    </>
                  ) : (
                    <>
                      오류를 발견하는 데서,
                      <br />
                      다시 막는 데까지<span className="accent">.</span>
                    </>
                  )}
                </h1>
                <p className="hero-description">
                  {tab === "lab"
                    ? "AI 판단 이후 정보가 바뀌면, 그 결과는 아직 유효할까요? 직접 바꿔 보고 확인해 보세요."
                    : tab === "receipts"
                      ? "입력 버전, 모델, 정책, 실패 원인까지. 각 판단을 되짚을 수 있는 작은 증거 묶음입니다."
                      : tab === "architecture"
                        ? "AI 연산을 기다리는 시간과, 현재 상태를 검증하는 짧은 순간을 분리합니다."
                        : "Python · LLM · AI/ML을 경험한 신입 개발자가, 반복되는 오류를 조사하는 태도를 서버 설계로 확장합니다."}
                </p>
              </div>
              {tab === "lab" && (
                <button className="walkthrough-button" onClick={startGuide}>
                  <Play size={15} fill="currentColor" />
                  90초 체험 시작
                  <ArrowUpRight size={17} />
                </button>
              )}
            </div>
          </section>
          <div className={`mode-banner ${mode === "live" ? "is-live" : ""}`}>
            <div className="mode-label">
              <span className="status-dot" />
              {mode === "browser" ? "브라우저 시뮬레이션" : "실제 Python 서버"}
              <span className="mode-note">
                {mode === "browser"
                  ? "이 화면의 상태를 직접 계산합니다. Python 추론·서버 성능 측정이 아닙니다."
                  : "HTTP API와 독립 모델 서버의 실제 응답을 표시합니다."}
              </span>
            </div>
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
                  <Wifi size={14} />
                  실제 Python 서버 연결
                </>
              ) : (
                <>
                  시뮬레이션으로 전환
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
          {showConnect && (
            <form
              className="connection-form"
              onSubmit={(e) => {
                e.preventDefault();
                void connect();
              }}
            >
              <label htmlFor="api-base">
                API 주소 <small>비우면 현재 사이트 주소 사용</small>
              </label>
              <input
                id="api-base"
                type="url"
                placeholder={window.location.origin}
                value={base}
                onChange={(e) => setBase(e.target.value)}
              />
              <button className="primary-button" disabled={connecting}>
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
              <TriangleAlert size={18} />
              <span>
                {error}
                <small>
                  자동으로 다른 모드로 바꾸거나 성공 결과를 만들지 않습니다.
                </small>
              </span>
              <button
                className="icon-button"
                onClick={() => setError("")}
                aria-label="오류 메시지 닫기"
              >
                <X size={16} />
              </button>
            </div>
          )}
          {tab === "lab" && (
            <>
              {guided !== null && (
                <section className="guided" aria-label="90초 체험 가이드">
                  <div className="guided-progress">
                    {walkthrough.map((_, i) => (
                      <span key={i} className={i <= guided ? "done" : ""} />
                    ))}
                  </div>
                  <div>
                    <span className="eyebrow">
                      90 SECOND WALKTHROUGH · {guided + 1}/4
                    </span>
                    <h3>{walkthrough[guided].title}</h3>
                    <p>{walkthrough[guided].text}</p>
                  </div>
                  <button
                    className="primary-button"
                    disabled={busy || mutating || !session}
                    onClick={() => void step()}
                  >
                    {guided === 3 ? "보호 장치 전후 비교" : "이 단계 실행"}
                    <ArrowRight size={15} />
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => setGuided(null)}
                    aria-label="체험 가이드 닫기"
                  >
                    <X size={16} />
                  </button>
                </section>
              )}
              <div className="lab-grid">
                <section className="customer-panel">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">01 / CUSTOMER VIEW</span>
                      <h2>고객이 보는 한 문장</h2>
                    </div>
                    <span className="mini-badge">송금 전 확인</span>
                  </div>
                  <div className="phone">
                    <div className="phone-top">
                      <span>9:41</span>
                      <div className="phone-island" />
                      <span className="phone-signal">
                        ▮▮▮ <span>▰</span>
                      </span>
                    </div>
                    <div className="phone-app-bar">
                      <span className="phone-logo">
                        r<span>·</span>
                      </span>
                      <span>안심 확인</span>
                      <LockKeyhole size={16} />
                    </div>
                    <div className="recipient">
                      <span className="recipient-avatar">김</span>
                      <p>
                        김리체크 님에게
                        <small>가상 수취인 · demo-recipient</small>
                      </p>
                    </div>
                    <div className="phone-amount">
                      {money(shownAmount)}
                      <span>원</span>
                    </div>
                    <div
                      className={`phone-result ${status}`}
                      aria-live="polite"
                    >
                      <div className="result-icon">
                        {busy ? (
                          <LoaderCircle size={30} className="spin" />
                        ) : status === "clear" ? (
                          <Check size={31} strokeWidth={2.5} />
                        ) : status === "ready" ? (
                          <ShieldCheck size={30} />
                        ) : (
                          <RefreshCw size={28} />
                        )}
                      </div>
                      <h3>{statusText}</h3>
                      <p>
                        {busy
                          ? "이 시간에도 정보와 정책이 바뀔 수 있어요."
                          : !current
                            ? "현재 정보에 맞는 판단을 준비할게요."
                            : unsafe
                              ? "재검증을 생략한 교육용 기준선입니다. 실제 사용 검증에서는 거절됩니다."
                              : stale
                                ? "이전 답을 사용하지 않고 현재 정보를 다시 확인해요."
                                : expired
                                  ? "이전 판단이 만료되었어요. 다시 확인해 주세요."
                                  : getReason(current.reason)}
                      </p>
                      {current && (
                        <span className="phone-receipt">
                          판단 #{short(current.id)} ·{" "}
                          {current.protected
                            ? "버전 검증 적용"
                            : "검증 생략 기준선"}
                        </span>
                      )}
                    </div>
                    <div className="phone-bottom">
                      <button
                        className="phone-cta"
                        onClick={() => void run()}
                        disabled={busy || !session}
                      >
                        {busy
                          ? "확인 중…"
                          : current && blocked
                            ? "다시 확인하기"
                            : "보내기 전 확인하기"}
                        <ArrowRight size={17} />
                      </button>
                      <p>
                        <LockKeyhole size={11} />
                        실제 송금은 실행되지 않습니다
                      </p>
                    </div>
                  </div>
                  <div className="customer-caption">
                    <span className="caption-line" />
                    <p>
                      모델의 점수보다,
                      <br />
                      <strong>지금 쓸 수 있는 답인지</strong>가 먼저입니다.
                    </p>
                  </div>
                </section>
                <div className="engineering-panel">
                  <section className="scenario-panel">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">02 / SCENARIO CONTROL</span>
                        <h2>상황을 바꿔 보세요</h2>
                      </div>
                      <button
                        className="text-button reset"
                        onClick={() => {
                          setDelay(0);
                          setFault("none");
                          setProtected(true);
                          setAmount(150000);
                          setGuided(null);
                          void newSession();
                        }}
                        disabled={connecting}
                      >
                        <RefreshCw size={13} />
                        초기화
                      </button>
                    </div>
                    <div className="version-strip">
                      <span>
                        <i className="status-dot" />
                        SESSION{" "}
                        <code>
                          {session ? short(session.session_id) : "준비 중"}
                        </code>
                      </span>
                      <div>
                        <span>
                          특징 <strong>v{session?.feature_version || 1}</strong>
                        </span>
                        <span>
                          정책 <strong>v{session?.policy_version || 1}</strong>
                        </span>
                        <span>
                          모델{" "}
                          <strong>{session?.model_version || "risk-v1"}</strong>
                        </span>
                      </div>
                    </div>
                    <div className="scenario-fields">
                      <label className="amount-field" htmlFor="amount">
                        다음 확인 금액
                        <div className="input-wrap">
                          <input
                            id="amount"
                            type="number"
                            min="1000"
                            max="10000000"
                            step="1000"
                            value={amount}
                            onChange={(e) =>
                              setAmount(
                                Math.max(
                                  1000,
                                  Math.min(10000000, Number(e.target.value)),
                                ),
                              )
                            }
                            disabled={busy}
                          />
                          <span>원</span>
                        </div>
                      </label>
                      <label className="delay-field" htmlFor="delay">
                        주입 지연 <strong>{delay} ms</strong>
                        <input
                          id="delay"
                          type="range"
                          min="0"
                          max="1000"
                          step="20"
                          value={delay}
                          onChange={(e) => setDelay(Number(e.target.value))}
                        />
                        <span className="range-caption">
                          <span>0ms</span>
                          <span>시간 예산 300ms</span>
                          <span>1,000ms</span>
                        </span>
                      </label>
                    </div>
                    <div className="fault-row">
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
                        ).map((f) => (
                          <button
                            key={f.value}
                            aria-pressed={fault === f.value}
                            className={fault === f.value ? "selected" : ""}
                            onClick={() => setFault(f.value)}
                          >
                            {f.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="protection-row">
                      <div>
                        {protectedMode ? (
                          <ShieldCheck size={19} />
                        ) : (
                          <ShieldOff size={19} />
                        )}
                        <span>
                          판단 최신성 보호
                          <small>
                            {protectedMode
                              ? "추론 완료 후 버전을 다시 비교합니다."
                              : "재검증을 생략하는 의도적으로 취약한 기준선"}
                          </small>
                        </span>
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
                    <div className="mutation-label">
                      <span>추론 중에도 변경할 수 있습니다</span>
                      <ArrowDown size={12} />
                    </div>
                    <div className="mutation-buttons">
                      <button
                        onClick={() => void mutate("feature")}
                        disabled={!session || mutating}
                      >
                        <RefreshCw size={14} />
                        수취인 정보 변경
                      </button>
                      <button
                        onClick={() => void mutate("policy")}
                        disabled={!session || mutating}
                      >
                        <Layers3 size={14} />
                        정책 갱신
                      </button>
                      <button
                        onClick={() => void mutate("model")}
                        disabled={!session || mutating}
                      >
                        <GitBranch size={14} />
                        모델 교체
                      </button>
                    </div>
                    <div className="scenario-actions">
                      <button
                        className="primary-button"
                        disabled={busy || !session}
                        onClick={() => void run()}
                      >
                        {busy ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <Play size={14} fill="currentColor" />
                        )}
                        판단 요청 실행
                        <ArrowRight size={15} />
                      </button>
                      <button
                        className="race-button"
                        disabled={busy || mutating || !session}
                        onClick={() => void race()}
                      >
                        <Timer size={15} />
                        추론 중 변경 재현
                      </button>
                    </div>
                  </section>
                  <section className="trace-panel">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">03 / DECISION TRACE</span>
                        <h2>답이 만들어진 과정</h2>
                      </div>
                      <span
                        className={`trace-status ${busy ? "processing" : ""}`}
                      >
                        <span className="status-dot" />
                        {busy
                          ? "REQUEST IN PROGRESS"
                          : current
                            ? "REQUEST COMPLETE"
                            : "WAITING FOR REQUEST"}
                      </span>
                    </div>
                    {current ? (
                      <>
                        <div className="trace-summary">
                          <div>
                            <span>결과</span>
                            <strong
                              className={
                                current.status === "clear" ? "teal" : "amber"
                              }
                            >
                              {current.status === "clear"
                                ? "주의 신호 없음"
                                : current.status === "invalidated"
                                  ? "이전 결과 무효"
                                  : "추가 확인 필요"}
                            </strong>
                          </div>
                          <div>
                            <span>
                              {mode === "browser"
                                ? "브라우저 관측 시간"
                                : "API 응답 시간"}
                            </span>
                            <strong>
                              {current.latency_ms.toFixed(0)}
                              <small> ms</small>
                            </strong>
                          </div>
                          <div>
                            <span>입력 버전</span>
                            <strong>
                              v{current.feature_version}
                              {current.feature_version !==
                                session?.feature_version && (
                                <span className="version-changed">
                                  {" "}
                                  → v{session?.feature_version}
                                </span>
                              )}
                            </strong>
                          </div>
                        </div>
                        <div className="waterfall">
                          {current.spans.map((span, i) => (
                            <div
                              key={i}
                              className={`span-row ${span.status === "error" ? "span-error" : ""}`}
                            >
                              <span className="span-index">0{i + 1}</span>
                              <span className="span-name">{span.name}</span>
                              <div className="span-track">
                                <span
                                  style={{
                                    marginLeft: `${Math.min(90, (span.start_ms / Math.max(1, current.latency_ms)) * 88)}%`,
                                    width: `${Math.max(3, Math.min(90, (span.duration_ms / Math.max(1, current.latency_ms)) * 88))}%`,
                                  }}
                                />
                              </div>
                              <span className="span-duration">
                                {span.duration_ms.toFixed(0)}ms
                              </span>
                            </div>
                          ))}
                        </div>
                        <div className="trace-footer">
                          <code>trace {short(current.trace_id)}</code>
                          <button
                            className="text-button"
                            onClick={() => setDetail(current)}
                          >
                            판단 JSON
                            <FileJson size={14} />
                          </button>
                        </div>
                        {mode === "browser" && (
                          <p className="simulation-footnote">
                            로컬 규칙·주입 대기를 표시한 타임라인입니다. Python
                            분산 추적이나 모델 성능 수치가 아닙니다.
                          </p>
                        )}
                      </>
                    ) : (
                      <div className="trace-empty">
                        <div className="empty-trace-lines">
                          <span />
                          <span />
                          <span />
                        </div>
                        <p>
                          첫 요청을 실행하면
                          <br />
                          <strong>버전 읽기 → 추론 → 재검증</strong>이 여기에
                          연결됩니다.
                        </p>
                        <ArrowUpRight size={20} />
                      </div>
                    )}
                  </section>
                </div>
              </div>
              <div className="below-grid">
                <section className="validation-panel">
                  <span className="eyebrow">THE LAST CHECK</span>
                  <h3>사용하는 순간, 다시 확인합니다.</h3>
                  <p>
                    화면에 답이 남아 있어도, 버전과 유효기간이 맞아야 사용할 수
                    있습니다.
                  </p>
                  <div className="validation-controls">
                    <button
                      className="secondary-button"
                      disabled={!current || validating || busy}
                      onClick={() => void validate()}
                    >
                      {validating ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : (
                        <ShieldCheck size={15} />
                      )}
                      현재 판단 사용 검증
                      <ArrowRight size={15} />
                    </button>
                    {current && (
                      <span className="expiry">
                        <Clock3 size={12} />
                        {expired
                          ? "유효기간 만료"
                          : `만료까지 ${Math.max(0, Math.ceil((Date.parse(current.expires_at) - Date.now()) / 1000))}초`}
                      </span>
                    )}
                  </div>
                  {shownValidation && (
                    <div
                      className={`validation-result ${shownValidation.valid ? "valid" : "invalid"}`}
                      role="status"
                    >
                      {shownValidation.valid ? (
                        <Check size={17} />
                      ) : (
                        <TriangleAlert size={17} />
                      )}
                      <span>
                        <strong>
                          {shownValidation.valid ? "사용 가능" : "사용 거절"}
                        </strong>{" "}
                        · {getReason(shownValidation.reason)}
                      </span>
                    </div>
                  )}
                </section>
                <section className="event-panel">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">LIVE EVENT LOG</span>
                      <h3>이 세션에서 일어난 일</h3>
                    </div>
                    <span className="event-count">{events.length} EVENTS</span>
                  </div>
                  <ol className="event-list" aria-live="polite">
                    {events.slice(0, 4).map((event) => (
                      <li key={event.id} className={event.tone}>
                        <span className="event-dot" />
                        <div>
                          <strong>{event.title}</strong>
                          <p>{event.detail}</p>
                        </div>
                        <time>{clock(event.at)}</time>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
              <section className="takeaway">
                <span className="takeaway-number">→</span>
                <div>
                  <span className="eyebrow">
                    A SMALL ANSWER TO A BIG QUESTION
                  </span>
                  <p>추론의 성공과, 판단의 유효성은 다릅니다.</p>
                </div>
                <button
                  className="text-button"
                  onClick={() => setTab("architecture")}
                >
                  설계 의도 보기
                  <ArrowUpRight size={16} />
                </button>
              </section>
            </>
          )}
          {tab === "receipts" && (
            <section className="receipts-page">
              <div className="section-heading">
                <h2>
                  이 세션의 판단 기록{" "}
                  <span className="count-badge">{receipts.length}</span>
                </h2>
                <span className="muted">최근 30개 · 생성 당시 기록 보존</span>
              </div>
              {receipts.length ? (
                <div
                  className="receipt-table"
                  role="table"
                  aria-label="판단 기록"
                >
                  <div className="receipt-row table-head" role="row">
                    <span>판단 / 시각</span>
                    <span>생성 결과</span>
                    <span>버전</span>
                    <span>보호 장치</span>
                    <span>기록</span>
                  </div>
                  {receipts.map((r) => (
                    <div className="receipt-row" key={r.id} role="row">
                      <div>
                        <code>#{short(r.id)}</code>
                        <small>{clock(r.created_at)}</small>
                      </div>
                      <div>
                        <span className={`receipt-status ${r.status}`}>
                          {r.status === "clear"
                            ? "주의 신호 없음"
                            : r.status === "review"
                              ? "추가 확인"
                              : "무효화"}
                        </span>
                        <small>{getReason(r.reason)}</small>
                      </div>
                      <div>
                        <code>
                          F{r.feature_version} / P{r.policy_version}
                        </code>
                        <small>{r.model_version}</small>
                      </div>
                      <span>{r.protected ? "적용" : "기준선"}</span>
                      <button
                        className="text-button"
                        onClick={() => setDetail(r)}
                      >
                        상세
                        <ArrowUpRight size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="large-empty">
                  <FileJson size={37} />
                  <h3>아직 판단 기록이 없습니다.</h3>
                  <p>데모에서 첫 요청을 실행해 기록을 남겨 보세요.</p>
                  <button
                    className="primary-button"
                    onClick={() => setTab("lab")}
                  >
                    데모로 이동
                    <ArrowRight size={15} />
                  </button>
                </div>
              )}
              <p className="record-note">
                기록은 생성 당시의 결과입니다. 현재 사용 가능 여부는 별도의 검증
                API로 확인합니다. 새 세션을 시작하면 화면의 기록 목록이
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
                <span className="mini-badge">Python · FastAPI</span>
              </div>
              <div className="architecture-flow">
                <div className="architecture-node client">
                  <span className="node-number">01</span>
                  <Layers3 size={27} />
                  <h3>React UI</h3>
                  <p>
                    확인 요청
                    <br />
                    사용 시점 재검증
                  </p>
                  <code>TypeScript</code>
                </div>
                <div className="flow-arrow">
                  <span>HTTP</span>
                  <ArrowRight size={27} />
                </div>
                <div className="architecture-node gateway">
                  <span className="node-number">02</span>
                  <ShieldCheck size={27} />
                  <h3>API Gateway</h3>
                  <p>
                    스냅샷 · 시간 예산
                    <br />
                    멱등성 · 버전 비교
                  </p>
                  <code>FastAPI / SQLAlchemy</code>
                </div>
                <div className="flow-arrow">
                  <span>trace context</span>
                  <ArrowRight size={27} />
                </div>
                <div className="architecture-node worker">
                  <span className="node-number">03</span>
                  <Sparkles size={27} />
                  <h3>Model Worker</h3>
                  <p>
                    독립 프로세스 추론
                    <br />
                    동시 실행·대기 상한
                  </p>
                  <code>scikit-learn / OTel</code>
                </div>
              </div>
              <div className="database-line">
                <ArrowDown size={18} />
                <span>짧은 최종 검증 트랜잭션</span>
                <div>
                  <Layers3 size={17} />
                  <strong>SQLite / PostgreSQL</strong>
                  <span>버전 · 판단 기록</span>
                </div>
                <small className="storage-note">
                  공개 데모: SQLite · 로컬 Docker Compose: PostgreSQL
                  <br />
                  브라우저 모드: DB 없이 메모리에서 계산
                </small>
              </div>
              <div className="design-decisions">
                {[
                  {
                    n: "01",
                    title: "답이 돌아온 뒤, 다시 읽기",
                    body: "추론을 기다리는 동안 DB 잠금을 잡지 않습니다. 결과가 돌아오면 현재 버전과 스냅샷을 짧은 트랜잭션에서 비교합니다.",
                    trade: "비용: 추가 DB 조회 / 이점: 오래된 결과 발급 차단",
                  },
                  {
                    n: "02",
                    title: "시간 초과도 하나의 결과",
                    body: "기본 300ms는 실험 정책입니다. 타임아웃·모델 응답 불가를 숨기지 않고, 각각의 원인과 추가 확인 안내로 연결합니다.",
                    trade: "비용: 확인 필요 응답 증가 / 이점: 무제한 대기 방지",
                  },
                  {
                    n: "03",
                    title: "기술보다 먼저 재현 가능한 증거",
                    body: "단순한 규칙으로 동작하는 브라우저 모드와 실제 Python 추론을 구분합니다. 구성 파일과 실측·검증 기록도 구분해 설명합니다.",
                    trade:
                      "선택: Redis·Kafka 없이 시작 / 확장: 측정 근거에 따라",
                  },
                ].map((d) => (
                  <article key={d.n}>
                    <span className="decision-number">{d.n}</span>
                    <h3>{d.title}</h3>
                    <p>{d.body}</p>
                    <small>{d.trade}</small>
                  </article>
                ))}
              </div>
              <div className="architecture-note">
                <Terminal size={20} />
                <div>
                  <h3>보장 범위를 분명하게</h3>
                  <p>
                    버전 검증 시점 이후의 미래 변경까지 막지 않습니다. 실제 송금
                    승인과 원장 커밋의 원자성은 이 프로젝트의 범위 밖입니다.
                    합성 모델의 점수는 실제 사기 탐지 성능을 뜻하지 않습니다.
                  </p>
                </div>
              </div>
            </section>
          )}
          {tab === "story" && (
            <section className="story-page">
              <div className="story-quote">
                <span className="eyebrow">
                  THE ENGINEER BEHIND THE QUESTION
                </span>
                <h2>
                  AI가 만든 답을,
                  <br />
                  그대로 믿는 대신
                  <br />
                  <span>직접 확인하는 개발자.</span>
                </h2>
                <p>
                  저는 Python과 LLM·AI/ML을 경험한 신입 개발자입니다. AI와 함께
                  개발하며 반복되는 오류를 직접 조사하고, 서로 다른 해결 방법을
                  비교해 해결해 왔습니다.
                </p>
                <p>
                  RECHECK에서는 그 태도를 서버 설계로 확장합니다. 실패를
                  재현하고, 원인 가설을 검증하고, 같은 오류의 재발을 막는 과정을
                  보여주고 싶습니다.
                </p>
              </div>
              <div className="story-method">
                <span className="eyebrow">HOW I APPROACH A PROBLEM</span>
                {[
                  {
                    n: "01",
                    title: "반복되는 증상을 재현하기",
                    text: "“가끔 틀린다”를 “추론 중 정보가 바뀌면 틀린다”로 좁힙니다.",
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
                  시간 예산, 최신성 검증, 장애 시 응답, 관측 방법을 공통 서버
                  구성 요소로 제공하는 데 기여하고 싶습니다. 입사 후에는 현행
                  구조와 실제 필요를 먼저 확인하겠습니다.
                </p>
                <small>
                  이 프로젝트는 실제 은행 운영 경력이 아닌, 설계·구현·검증을
                  보여주는 지원 프로젝트입니다.
                </small>
              </div>
            </section>
          )}
          <footer className="footer">
            <span>
              <CheckCheck size={16} />
              recheck<span className="accent">.</span>
            </span>
            <p>합성 시나리오로 확인하는 AI 서빙의 신뢰성</p>
            <span>BUILT TO BE QUESTIONED.</span>
          </footer>
        </div>
      </main>
      <dialog
        ref={dialog}
        className="receipt-dialog"
        aria-labelledby="receipt-title"
        onClose={() => setDetail(null)}
      >
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">DECISION RECEIPT</span>
            <h2 id="receipt-title">판단의 근거를 열어 봅니다.</h2>
          </div>
          <button
            className="icon-button"
            onClick={() => dialog.current?.close()}
            aria-label="판단 상세 닫기"
          >
            <X size={20} />
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
              <span>버전·사유·trace를 함께 기록합니다.</span>
              <button
                className="primary-button"
                onClick={() => exportReceipt(detail)}
              >
                <Download size={15} />
                JSON 다운로드
              </button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}
