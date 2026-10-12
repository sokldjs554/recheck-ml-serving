import data from "./serving-evidence.json";
const docs = "https://github.com/sokldjs554/recheck-ml-serving/blob/main/docs/";
const names: Record<string, string> = {
  normal: "정상",
  overload: "과부하",
  recovery: "정상 복귀",
};
const n = (value: number) => value.toLocaleString("ko-KR");

export function SustainedReview() {
  const run = data.sustained;
  return (
    <article className="measured-review" data-testid="sustained-review">
      <div className="review-question">
        <span>실험 질문</span>
        <h2>부하를 낮추면, 같은 서버가 다시 제시간에 답할까?</h2>
        <p>
          모델의 HTTP 200만 세면 보류 응답도 성공으로 보입니다. 요청을 예정한
          시점부터 300ms 안에 도착한 유효 모델 결과를 따로 셌습니다.
        </p>
      </div>
      <section className="review-section">
        <h3>조건</h3>
        <div>
          <p>
            실제 HTTP <code>/decisions</code> → CPU 추론 프로세스 2개 →
            PostgreSQL. 30초씩 <strong>10 → 120 → 10 req/s</strong>를 2회,
            재시작 없이 총 180초 실행했습니다. 상담 정합성 체험과 다른
            경로입니다.
          </p>
          <p className="review-note">
            시작·학습과 5초 워밍업은 제외. 단일 공유 호스트의 CPU quota 4코어,
            affinity 5개이며 전용 자원이 아닙니다. 공개 무료 서버에는 부하를
            보내지 않았습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>관측 결과</h3>
        <div>
          <div
            className="phase-chart"
            role="img"
            aria-label="두 회차 모두 정상 구간 300건 전부 유효. 과부하에서는 3600건 중 각각2032건과2040건 유효. 정상 복귀 구간 다시300건 전부 유효."
          >
            {run.phases.map((phase) => (
              <div
                className={`phase-column phase-${phase.name}`}
                key={phase.index}
              >
                <span>
                  {phase.cycle}회 · {names[phase.name]}
                </span>
                <div className="phase-track">
                  <i style={{ height: `${(phase.target_rps / 120) * 100}%` }} />
                  <b
                    style={{
                      height: `${(phase.cohort_rates_rps.good / 120) * 100}%`,
                    }}
                  />
                </div>
                <strong>
                  {phase.cohort_rates_rps.good.toFixed(1)}
                  <small> 유효 req/s</small>
                </strong>
                <span>
                  {n(phase.good)} / {n(phase.attempted)}
                </span>
              </div>
            ))}
          </div>
          <p className="chart-key">
            <i /> 목표 요청률 <b /> 300ms 내 유효 응답률 · 각 막대 30초
          </p>
          <p>
            과부하 두 구간 합계 7,200건 중 유효 응답 4,072건.{" "}
            <strong>보류 2,983건 · HTTP 429 거절 144건 · HTTP 504 1건</strong>을
            성공에서 제외했습니다. 정상·복귀 네 구간은 각 300 / 300건이었습니다.
          </p>
          <p>
            두 회차 모두 복귀 직후 시작한 5초 창 2개가 회복 조건을 만족해{" "}
            <strong>10초 시점에 회복을 확인</strong>했습니다. 실제 회복에 10초가
            걸렸다는 의미는 아닙니다. 최대 모델 대기 4개, 종료 시 0개였습니다.
          </p>
          <dl className="review-metrics">
            <div>
              <dt>API·모델 최대 합산 RSS</dt>
              <dd>{(run.cost.peak_rss_bytes / 1048576).toFixed(1)} MiB</dd>
            </div>
            <div>
              <dt>유효 응답당 CPU</dt>
              <dd>{run.cost.cpu_ms_per_good_response.toFixed(1)} ms</dd>
            </div>
            <div>
              <dt>SQL과 일치한 HTTP 200</dt>
              <dd>{n(run.reconciliation.delivered_equal_sql)}건</dd>
            </div>
          </dl>
          <p className="review-callout">
            504 응답 한 건은 DB 기록 이후 시간 예산을 넘겼습니다. 최종 SQL
            8,306건과 수신 응답 8,305건의 차이를 숨기지 않았으며, 원본에는 해당
            키·receipt·trace가 있습니다. 중복·누락·불일치·pending 기록은
            0건입니다. SQL 대조에는 워밍업 50건이 포함됩니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>설계 판단</h3>
        <div>
          <p>
            CPU 연산을 프로세스로 분리하고 수용량을 제한해 API 이벤트 루프와
            대기열을 보호합니다. 감당하지 못하는 요청은 거절하거나 보류합니다.
            요청 시간 예산이 끝나도 이미 시작된 CPU 작업의 슬롯은 실제 종료까지
            점유합니다.
          </p>
          <p>
            비용은 프로세스 메모리, 처리 가능한 요청의 제한, 그리고 저장 이후
            응답 실패를 구분해야 하는 복잡도입니다. 기존 worker 단독 비교와 이번
            전체 경로 측정은 측정 경계가 달라 수치를 합산하지 않습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>한계</h3>
        <div>
          <p>
            3분·2사이클 관측으로 장기 처리 용량이나 SLA를 보장할 수 없습니다.
            CPU·메모리는 API/모델 트리만 측정했고 DB·생성기는 제외했습니다.
            RSS는 공유 메모리를 중복 집계할 수 있습니다. 큐·시간 예산의 최적값을
            탐색한 실험도 아닙니다.
          </p>
          <p>
            세션 TTL {run.settings.session_ttl_seconds}초, 최대 세션 나이{" "}
            {run.retention.oldest_session_age_seconds.toFixed(1)}초. 세션당 최대
            기록 {run.retention.max_receipts_in_any_session} /{" "}
            {run.settings.max_receipts_per_session}건으로 만료·기록 제한에
            도달하지 않았습니다. 생성기 지연을 아래에 함께 남겼습니다.
          </p>
        </div>
      </section>
      <details className="review-details">
        <summary>구간별 전송·처리율, 지연, 대기열과 원본</summary>
        <div
          className="review-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="지속 부하 구간별 측정"
        >
          <table>
            <thead>
              <tr>
                <th>회차 / 구간</th>
                <th>목표</th>
                <th>전송 / 완료 / 유효 req/s</th>
                <th>p50 / p95 / p99 ms</th>
                <th>생성 지연 p99</th>
                <th>대기 최대</th>
              </tr>
            </thead>
            <tbody>
              {run.phases.map((p) => (
                <tr key={p.index}>
                  <th>
                    {p.cycle} / {names[p.name]}
                  </th>
                  <td>{p.target_rps}</td>
                  <td>
                    {[
                      p.wall_window_rates_rps.sent,
                      p.wall_window_rates_rps.completed,
                      p.wall_window_rates_rps.good,
                    ]
                      .map((v) => v.toFixed(2))
                      .join(" / ")}
                  </td>
                  <td>
                    {Object.values(p.scheduled_latency_ms)
                      .map((v) => v.toFixed(1))
                      .join(" / ")}
                  </td>
                  <td>{p.generator_lag_ms.p99.toFixed(1)} ms</td>
                  <td>{p.resources.peak_worker_queue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          처리율은 고정 30초 창 안의 실제 전송·완료 기준입니다. 위 그래프는 해당
          구간에 예정한 요청의 최종 유효 응답 수를 응답 tail 포함 시간으로 나눈
          값입니다. 지연은 실패를 포함한 전체 시도 기준입니다.
        </p>
        <a target="_blank" rel="noreferrer" href={docs + "fullpath-sustained.md"}>정의·조건·재현 명령 ↗</a>
        <a target="_blank" rel="noreferrer" href={docs + "evidence/" + run.raw_file}>
          모든 요청·자원 표본·최종 SQL 원본 ↗
        </a>
      </details>
    </article>
  );
}

export function FailureReview() {
  const failed = data.failure.failed;
  const recovered = data.failure.recovered;
  return (
    <article className="measured-review" data-testid="failure-review">
      <div className="review-question">
        <span>실험 질문</span>
        <h2>HTTP 200인데 추론이 실패했다면, 어디까지 처리됐을까?</h2>
        <p>
          한 요청의 trace와 로그를 따라가고, 반환된 receipt를 PostgreSQL에서
          별도로 조회했습니다.
        </p>
      </div>
      <section className="review-section">
        <h3>조건</h3>
        <div>
          <p>
            로컬 API·모델·독립 PostgreSQL에서 <code>/decisions</code>의 모델
            unavailable 오류를 주입했습니다. 실제 SDK의 OTLP export를 로컬
            수신기로 수집했습니다. CPU 지속 부하와 별도인 lightweight 추론
            조건입니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>관측 결과</h3>
        <div>
          <ol className="failure-chain">
            <li>
              <strong>API 접수</strong>
              <span>같은 trace의 decision → snapshot → model.http</span>
            </li>
            <li>
              <strong>모델 실패</strong>
              <span>worker span에 exception. 예측은 실행되지 않음</span>
            </li>
            <li>
              <strong>실패를 기록</strong>
              <span>
                HTTP {failed.http_status} / {failed.receipt.status} /{" "}
                {failed.receipt.reason}. 유효 응답으로 집계하지 않음
              </span>
            </li>
            <li>
              <strong>SQL 대조</strong>
              <span>
                반환 receipt와 커밋된 row 일치. trace ID로 API 로그 연결
              </span>
            </li>
          </ol>
          <code className="review-trace">{failed.receipt.trace_id}</code>
          <p>
            오류 주입을 해제한 다음 요청은{" "}
            <strong>{recovered.receipt.status}</strong> 응답과 유효성 검증을
            통과했고, 그 receipt도 SQL 기록과 일치했습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>복구 사례</h3>
        <div>
          <p>
            기존의 별도 Kubernetes 실험에서는{" "}
            <strong>
              PostgreSQL Pod 교체 → readiness 실패·HTTP 503 탐지 → Pod/준비 상태
              확인 → 같은 PVC로 DB 재기동 → 정상 추론과 기존 기록 보존 확인
            </strong>
            을 연결했습니다.
          </p>
          <p>
            전환 중 HTTP 503 표본 5건. 첫 실패부터 첫 성공까지 관측 간격은
            2.502초였습니다. 전체 단계 32.717초는 조작·대기·검증 시간도
            포함합니다. 위 trace 실험과 같은 실행으로 묶지 않습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>설계 판단</h3>
        <div>
          <p>
            모델 실패를 작업 가능 상태로 내보내지 않고 review receipt로
            남깁니다. liveness와 readiness를 나눠 API 프로세스 생존과 의존
            서비스 장애를 구분합니다. 복구는 health 응답뿐 아니라 새 추론과 저장
            성공까지 확인합니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>한계</h3>
        <div>
          <p>
            <code>fence.commit</code>은 ORM flush/commit 이전에 끝나는
            애플리케이션 span입니다. SQL 커밋 시간으로 읽으면 안 됩니다.
            네이티브 SQL span은 없고, 영속화는 독립 SQL 조회로 확인했습니다.
            Kubernetes는 단일 노드 kind이며 공개 Render 배포의 장애 복구 실적이
            아닙니다.
          </p>
        </div>
      </section>
      <details className="review-details">
        <summary>실패·복구 trace, 로그, SQL 대조 원본</summary>
        <p>
          실패 trace: <code>{failed.receipt.trace_id}</code>
          <br />
          복구 요청 trace: <code>{recovered.receipt.trace_id}</code>
        </p>
        <a target="_blank" rel="noreferrer" href={docs + "failure-walkthrough.md"}>
          실패부터 복구까지 재현·해석 ↗
        </a>
        <a target="_blank" rel="noreferrer" href={docs + "evidence/failure-trace-proof.json"}>
          실제 span·로그·SQL 행 ↗
        </a>
        <a target="_blank" rel="noreferrer" href={docs + "evidence/kubernetes-proof.json"}>
          별도 Kubernetes 복구 원본 ↗
        </a>
      </details>
    </article>
  );
}

export function ConsistencyReview() {
  const cells = data.consistency.cells;
  const rows = cells.filter(
    (c) => c.parameters.workers === 8 && c.parameters.profile === "near_cap",
  );
  return (
    <article
      className="measured-review consistency-reading"
      data-testid="consistency-review"
    >
      <div className="review-question">
        <span>별도 SQL 실험</span>
        <h2>정합성을 지키기 위해 얼마나 기다리는가?</h2>
        <p>
          세션 잠금과 JSON 저장을 없애기 전에, 경합과 상태 크기에 따른 비용부터
          측정했습니다.
        </p>
      </div>
      <section className="review-section">
        <h3>조건</h3>
        <div>
          <p>
            같은 세션 / 서로 다른 세션 × 동시 요청 1·4·8개 × 문서 변경
            0·25·50%의 wave × 지원 범위 내 상태 3종 × 3회. 총 162개 짧은
            실행입니다. 총 4개 wave이며, 매 wave의 모든 요청이 끝난 뒤 다음
            wave를 시작하는 SQL 직접 호출입니다. HTTP나 CPU 모델 부하가 아닙니다.
          </p>
          <p className="review-note">
            DB 연결 풀 4개, lock timeout 100ms. 기록·평가·문서 길이 제한을
            늘리지 않았습니다. JSON은 실제 SQL 저장 바이트를 측정했습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>관측 결과</h3>
        <div>
          <p>
            동시 8개·큰 상태·문서 변경 없음에서 같은 세션은{" "}
            <strong>91.89건/s · p95 86.87ms</strong>, 다른 세션은{" "}
            <strong>111.43건/s · p95 78.64ms</strong>였습니다. 같은 세션·동시
            1개에서 작은→큰 상태로 바꾸면 p95는 7.71→15.98ms였습니다.
          </p>
          <p>
            2,808회 실행 요청 중{" "}
            <strong>
              기록 2,095 · 원문 변경 거절 711 · 잠금 시간 초과 2건
            </strong>
            . 별도 변경 요청 432건은 성공했습니다. 최종 SQL의 오래된
            기록·중복·수신 기록 누락은 0건이며, 시간 초과 두 키도 저장되지
            않았습니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>설계 판단</h3>
        <div>
          <p>
            세션 단위 직렬화와 상태 저장 비용은 관측됐지만, JSON이 유일한
            병목이라는 근거는 없습니다. 지원 범위를 유지하고 트랜잭션 보호를
            보존했습니다. 문서가 자주 바뀌면 빠른 거절이 늘어도 새 기록의
            처리량은 감소하므로 둘을 나눠 표시합니다.
          </p>
        </div>
      </section>
      <section className="review-section">
        <h3>한계</h3>
        <div>
          <p>
            짧은 동기화 wave, 고정 풀, Python 스케줄링, JSON 처리와 SQL 잠금이
            함께 영향을 줍니다. 행 획득 시간은 풀 획득과 SQL 실행도 포함하므로
            순수 잠금 대기 시간이 아닙니다. 같은 세션은 기록이 한곳에 쌓여 최종
            상태 크기도 다릅니다. 인과적 병목 진단이나 지속 처리 용량으로
            해석하지 않습니다.
          </p>
        </div>
      </section>
      <details className="review-details">
        <summary>변경 빈도별 비용과 전체 54조건·162회 원본</summary>
        <div
          className="review-table-scroll"
          role="region"
          aria-label="정합성 비용 비교"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>세션</th>
                <th>변경 wave</th>
                <th>변경 요청 수</th>
                <th>새 기록 / 실행</th>
                <th>p95 ms</th>
                <th>새 기록/s</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={`${c.parameters.sharing}-${c.parameters.edit_every}`}>
                  <th>
                    {c.parameters.sharing === "shared" ? "동일" : "서로 다름"}
                  </th>
                  <td>
                    {c.parameters.edit_every
                      ? 100 / c.parameters.edit_every
                      : 0}
                    %
                  </td>
                  <td>{c.edit_requests}</td>
                  <td>
                    {c.sql_new_actions} / {c.execute_requests}
                  </td>
                  <td>{c.execute_p95_ms.toFixed(2)}</td>
                  <td>{c.useful_new_actions_per_second.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          동시 8개·near-cap, 3회 합산. 서로 다른 세션은 동일한 세션당 변경
          빈도를 만들기 위해 변경 요청 수도 많습니다. 같은 요청 혼합비의 비교가
          아닙니다. 지원 상태의 SQL JSON은 약 49.7KB에서 226.3KB까지
          관측했습니다.
        </p>
        <a target="_blank" rel="noreferrer" href={docs + "consistency-costs.md"}>전체 결과와 재현 명령 ↗</a>
        <a target="_blank" rel="noreferrer" href={docs + "evidence/consistency-costs.json.gz"}>
          요청·잠금 표본·최종 SQL 원본 ↗
        </a>
      </details>
    </article>
  );
}
