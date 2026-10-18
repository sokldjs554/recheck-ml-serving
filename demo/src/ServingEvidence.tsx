import { useState } from "react";
import data from "./serving-evidence.json";
import fullpath from "./fullpath-evidence.json";
import PublicOperations from "./PublicOperations";
import ModelHandoff from "./ModelHandoff";
import MeasurementOrigin from "./MeasurementOrigin";
import {
  SustainedReview,
  FailureReview,
  ConsistencyReview,
} from "./MeasuredReview";
import "./servingEvidence.css";

const evidenceRoot =
  "https://github.com/sokldjs554/recheck-ml-serving/blob/main/docs/evidence/";
const number = (n: number) => n.toLocaleString("en-US");
const date = (value: string) =>
  new Date(value).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    hour12: false,
  }) + " KST";
const names: Record<string, string> = {
  api_pod_replacement: "API Pod 교체",
  model_pod_replacement: "모델 Pod 교체",
  rolling_restart: "롤링 재시작",
  bad_model_rollout: "준비 실패 모델 배포",
  rollback: "이전 모델로 롤백",
  postgres_pod_replacement: "PostgreSQL Pod 교체",
};

export default function ServingEvidence({
  view,
}: {
  view: "serving" | "recovery";
}) {
  const [selected, select] = useState(0);
  const sample = data.samples[selected];
  const outcomes = [
    { label: "200ms 내 성공", count: sample.good, className: "good" },
    { label: "늦게 도착한 HTTP 200", count: sample.late, className: "late" },
    {
      label: "수용 한도 초과 · 429",
      count: sample.rejected,
      className: "rejected",
    },
    { label: "시간 초과 · 504", count: sample.timeout, className: "timeout" },
  ];
  const observed = data.observability;
  return (
    <section
      className="serving-sheet"
      aria-label={view === "serving" ? "모델 부하 실험" : "장애 복구 실험"}
    >
      <header className="serving-heading">
        <span className="serving-index">
          {view === "serving" ? "02" : "03"}
        </span>
        <div>
          <h1>
            {view === "serving" ? <>모델 부하와<br /><em>처리 한계</em></> : <>모델 장애와<br /><em>복구 기록</em></>}
          </h1>
          <p>
            {view === "serving"
              ? "요청량 증가에 따른 유효 응답·거절과 부하 감소 후 회복 결과"
              : "모델 오류의 추적·저장 기록과 별도 Kubernetes 복구 실험"}
          </p>
        </div>
      </header>
      <p className="serving-record-note" data-testid="stored-evidence-note">
        {view === "serving"
          ? "저장된 로컬 실험 · API → CPU 모델 → PostgreSQL"
          : "저장된 장애·복구 실험 · 공개 API 운영 기록은 별도 조회"}
      </p>
      {view === "serving" ? (
        <>
          <SustainedReview />
          <ConsistencyReview />
          <details className="review-details" data-testid="prior-serving">
            <summary>
              기존 비교 근거 · 프로세스 격리·모델 인계·짧은 회귀 실험
            </summary>
            <ModelHandoff />
            <section
              className="public-observation"
              aria-label="API 모델 PostgreSQL 전체 경로 부하"
            >
              <h2>API에서 SQL 기록까지</h2>
              <MeasurementOrigin file="fullpath-load.json" />
              <p>
                HTTP API → CPU 추론 프로세스 2개 → PostgreSQL. 아래는 전체
                경로를 호출한 별도 실험입니다. 각 요청률을 5초씩 2회 측정했고,
                성공·보류·오류를 모두 셌습니다.
              </p>
              <div className="recovery-table-scroll">
                <table className="recovery-table">
                  <thead>
                    <tr>
                      <th>요청률 / 회차</th>
                      <th>500ms 내 유효 응답</th>
                      <th>전체 p95</th>
                      <th>HTTP 오류</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fullpath.cases.map((c) => (
                      <tr key={`${c.rate_rps}-${c.repeat}`}>
                        <th>
                          {c.rate_rps} req/s · {c.repeat}회
                        </th>
                        <td>
                          {c.good} / {c.requested}
                        </td>
                        <td>{c.p95_ms.toFixed(1)} ms</td>
                        <td>
                          {Object.entries(c.outcomes)
                            .filter(([k]) => k !== "200")
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(", ") || "0"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                HTTP 200으로 받은{" "}
                {fullpath.checks.all_delivered_receipts_equal_sql}개 응답을 DB
                원본과 대조했습니다. 중복 저장 0건. 연결 중단 후 재시도와 API
                재시작 후에도 같은 기록을 돌려받았습니다.
              </p>
              <p>
                첫 구간의 DB 오류 1건도 포함합니다. 이 실행에서는 다른 SQL
                검증이 같은 로컬 DB를 사용했습니다. 공유 호스트의 짧은 측정이며
                공개 Render 서버의 처리 용량은 아닙니다.
              </p>
              <a
                href={evidenceRoot + "fullpath-load.json"}
                target="_blank"
                rel="noreferrer"
              >
                전체 시도·조건·실패 원본 ↗
              </a>
              <h3>요청률별 응답 결과</h3>
              <MeasurementOrigin file="fullpath-saturation.json.gz" />
              <p>
                전용 테스트 DB로 분리한 뒤 60·120 req/s를 각각 2초씩 2회
                실행했습니다. HTTP 200이라도 추론이 보류되면 성공에서 뺐습니다.
              </p>
              <div className="recovery-table-scroll">
                <table className="recovery-table">
                  <thead>
                    <tr>
                      <th>요청률 / 회차</th>
                      <th>500ms 내 유효 응답</th>
                      <th>과부하 보류·거절</th>
                      <th>전체 p95</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fullpath.saturation.cases.map((c) => (
                      <tr key={`${c.rate_rps}-${c.repeat}`}>
                        <th>
                          {c.rate_rps} req/s · {c.repeat}회
                        </th>
                        <td>
                          {c.good} / {c.requested}
                        </td>
                        <td>{c.reasons.overloaded ?? 0}</td>
                        <td>{c.p95_ms.toFixed(1)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                120 req/s 두 회차에서 전체 480건 중 250건이 유효 응답이었습니다.
                나머지 230건에는 HTTP 429 거절 17건과 HTTP 200 보류 213건이
                포함됩니다. 모두 같은 분모에 남겼습니다.
              </p>
              <a
                href={evidenceRoot + "fullpath-saturation.json.gz"}
                target="_blank"
                rel="noreferrer"
              >
                과부하 원본 내려받기 · JSON.gz ↗
              </a>
            </section>
            <div className="serving-instrument">
              <MeasurementOrigin file={sample.source} />
              <aside className="serving-settings">
                <h2>요청률 선택</h2>
                <div
                  className="serving-switch"
                  role="group"
                  aria-label="저장된 부하 실험 선택"
                >
                  {data.samples.map((item, i) => (
                    <button
                      key={item.rate}
                      aria-pressed={selected === i}
                      onClick={() => select(i)}
                    >
                      {item.rate} req/s
                    </button>
                  ))}
                </div>
                <dl>
                  <div>
                    <dt>모델</dt>
                    <dd>ExtraTrees · 128 trees</dd>
                  </div>
                  <div>
                    <dt>요청당 연산</dt>
                    <dd>4,096개 불확실성 시나리오</dd>
                  </div>
                  <div>
                    <dt>서버 / 프로세스</dt>
                    <dd>서버 2개 · 각각 추론 프로세스 1개</dd>
                  </div>
                  <div>
                    <dt>관측 시간</dt>
                    <dd>{sample.duration}초</dd>
                  </div>
                  <div>
                    <dt>호스트</dt>
                    <dd>공유 5 CPU · 단일 호스트</dd>
                  </div>
                </dl>
                <p>
                  학습된 CPU 모델을 실제 연산합니다. 공개 상담 데모의 TF-IDF
                  검색과는 별도 실험입니다.
                </p>
              </aside>
              <div className="serving-readout" aria-live="polite">
                <div className="serving-result">
                  <span>200ms 안에 끝난 요청</span>
                  <strong data-testid="serving-good">
                    {number(sample.good)} / {number(sample.requested)}
                  </strong>
                  <span>
                    {((sample.good / sample.requested) * 100).toFixed(2)}% ·
                    전체 시도 기준
                  </span>
                </div>
                <div className="serving-bar" aria-hidden="true">
                  {outcomes
                    .filter((o) => o.count > 0)
                    .map((o) => (
                      <span
                        key={o.className}
                        className={o.className}
                        style={{
                          width: `${(o.count / sample.requested) * 100}%`,
                        }}
                      />
                    ))}
                </div>
                <dl className="serving-outcomes" data-testid="serving-outcomes">
                  {outcomes.map((o) => (
                    <div key={o.label}>
                      <dt>
                        <i className={o.className} />
                        {o.label}
                      </dt>
                      <dd>
                        {number(o.count)}
                        <small>건</small>
                      </dd>
                    </div>
                  ))}
                </dl>
                <div className="serving-ruler">
                  <span>
                    전체 응답 p95 <b>{sample.p95.toFixed(1)} ms</b>
                  </span>
                  <span>
                    프로세스 합산 최대 RSS{" "}
                    <b>{(sample.rssBytes / 1048576).toFixed(1)} MiB</b>
                  </span>
                  <span>
                    상태 확인 p95 <b>{sample.healthP95.toFixed(1)} ms</b>
                  </span>
                </div>
              </div>
            </div>
            <div className="serving-reading">
              <span>해석</span>
              <p>
                {selected === 0
                  ? "30 req/s에서는 900건 중 896건이 시간 기준을 만족했습니다. 짧은 측정에서 확인한 시작점이며, 장기 처리 용량이나 SLA 보장은 아닙니다."
                  : "60 req/s에서는 HTTP 200 중 148건도 200ms를 넘겼습니다. 거절 775건과 시간 초과 105건을 포함하면, 제시간에 끝난 비율은 71.44%입니다. HTTP 성공률만 보면 부하 한계를 놓칩니다."}
              </p>
            </div>
            <p className="serving-boundary" data-testid="serving-boundary">
              측정 경계: 모델 서버 HTTP 직접 호출. API·DB·브라우저 지연은
              제외합니다. 두 실험의 지속 시간이 달라 요청률만의 인과 효과로
              단정할 수 없습니다. RSS는 공유 페이지를 중복 집계할 수 있습니다.
            </p>
            <footer className="serving-source">
              <time>{date(sample.measuredAt)}</time>
              <a
                href={evidenceRoot + sample.source}
                target="_blank"
                rel="noreferrer"
              >
                측정 원본 ↗
              </a>
              <a
                href="https://github.com/sokldjs554/recheck-ml-serving/blob/main/docs/compute-experiments.md"
                target="_blank"
                rel="noreferrer"
              >
                조건과 재현 명령 ↗
              </a>
            </footer>
          </details>
        </>
      ) : (
        <>
          <FailureReview />
          <PublicOperations />
          <details className="review-details" data-testid="prior-recovery">
            <summary>
              기존 운영 근거 · Jaeger·알림·Kubernetes·공개 API 점검
            </summary>
            <div className="recovery-proof" data-testid="recovery-proof">
              <MeasurementOrigin file="observability-latest.json" />
              <div className="recovery-wiring">
                <span>Python API</span>
                <b>→</b>
                <span>모델 서버</span>
                <b>→</b>
                <span>Collector / Jaeger</span>
              </div>
              <p>
                같은 trace의 {observed.trace.span_count}개 span에서 API 호출과
                모델 추론의 부모 관계를 확인했습니다.
              </p>
              <code className="recovery-trace">
                trace / {observed.trace.trace_id}
              </code>
              <div className="recovery-states">
                <div>
                  <span>모델 중단 시 API 생존</span>
                  <strong>{observed.probes.live}</strong>
                </div>
                <div>
                  <span>모델 중단 시 준비 상태</span>
                  <strong>{observed.probes.ready}</strong>
                </div>
                <div>
                  <span>복구 후 실제 추론</span>
                  <strong>{observed.recovered.status}</strong>
                </div>
              </div>
              <p>
                로컬 수신기에 알림 발화 {date(observed.firingAt)} → 해제{" "}
                {date(observed.resolvedAt)}를 기록했습니다. 복구 후 새 추론의
                모델 해시와 유효성까지 확인했습니다.
              </p>
              <a
                href={evidenceRoot + "observability-latest.json"}
                target="_blank"
                rel="noreferrer"
              >
                추적·알림 원본 ↗
              </a>
            </div>
            <div className="recovery-table-heading">
              <h2>Kubernetes 장애 주입과 복구 기록</h2>
              <span>단일 노드 kind · 저장된 1회 실행</span>
            </div>
            <div
              className="recovery-table-scroll"
              role="region"
              aria-label="Kubernetes 복구 결과"
              tabIndex={0}
            >
              <table className="recovery-table">
                <thead>
                  <tr>
                    <th>주입한 사건</th>
                    <th>단계 소요 시간</th>
                    <th>HTTP 오류 / 표본</th>
                    <th>복구 후 판단</th>
                  </tr>
                </thead>
                <tbody>
                  {data.kubernetes.events.map((event) => {
                    const phase =
                      data.kubernetes.phases[
                        event.name as keyof typeof data.kubernetes.phases
                      ];
                    return (
                      <tr
                        key={event.name}
                        data-testid={
                          event.name === "postgres_pod_replacement"
                            ? "postgres-recovery"
                            : undefined
                        }
                      >
                        <th>{names[event.name]}</th>
                        <td>{event.duration_seconds.toFixed(3)} s</td>
                        <td>
                          {phase.http_errors} / {phase.attempts}
                        </td>
                        <td>
                          {event.recovered_inference.valid
                            ? "유효함"
                            : "확인 필요"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="serving-reading">
              <span>남은 한계</span>
              <p>
                DB 교체 중 HTTP 오류 5건, 준비 실패 모델 배포 중 HTTP 200의 확인
                필요 응답 1건을 관측했습니다. 단계 소요 시간에는
                조작·대기·검증이 포함됩니다. 장애 지속 시간이나 무중단 실적으로
                해석하지 않습니다.
              </p>
            </div>
            <p className="serving-boundary">
              0.5초 간격의 합성 요청 표본입니다. 관측 사이의 장애를 놓칠 수
              있습니다. 공개 데모는 Render에서 실행하며, 이 Kubernetes 실험과
              별도입니다. 실제 온콜·장기 가용성 실적은 없습니다.
            </p>
            <section
              className="public-observation"
              aria-label="공개 API 최근 관측"
            >
              <h2>공개 API 점검의 처리 시간 초과</h2>
              <p>
                기능 검증 3 / 3 통과 · 5초 내 완료 {data.public.summary.good} /{" "}
                {data.public.summary.total}. 첫 표본은{" "}
                {(data.public.rows[0].duration_ms / 1000).toFixed(1)}초가
                걸렸습니다. 첫 표본을 포함해 이 점검은 시간 기준 실패로
                기록됐습니다. 단계별 시간이 없어 지연 원인은 확인되지 않았습니다.
              </p>
              <ol>
                {data.public.rows.map((row, i) => (
                  <li key={row.at}>
                    <span>표본 {i + 1}</span>
                    <time>{date(row.at)}</time>
                    <b>{(row.duration_ms / 1000).toFixed(2)} s</b>
                  </li>
                ))}
              </ol>
              <p>
                실제 외부 점검의 전체 과정 소요 시간입니다. 단일 추론 지연이 아니며 점검
                사이의 가용성은 알 수 없으며, 저장된 이 실행의 결과를 현재
                상태나 장기 SLA로 표시하지 않습니다.
              </p>
              <a href={data.public.source_url} target="_blank" rel="noreferrer">
                실패한 원본 실행 ↗
              </a>
            </section>
            <footer className="serving-source">
              <time>
                {date(data.kubernetes.start)} — {date(data.kubernetes.end)}
              </time>
              <a
                href={evidenceRoot + "kubernetes-proof.json"}
                target="_blank"
                rel="noreferrer"
              >
                모든 사건·오류 원본 ↗
              </a>
            </footer>
          </details>
        </>
      )}
    </section>
  );
}
