import data from "./safety-evidence.json";
import "./safetyComparison.css";
const labels: Record<string, string> = {
  trust_at_creation: "생성 당시 결과 신뢰",
  check_then_act: "사용 직전 확인 → 별도 기록",
  atomic_guard: "검증과 기록을 한 트랜잭션으로",
};
const repo = "https://github.com/sokldjs554/recheck-ml-serving/blob/main/";
export default function SafetyComparison() {
  return (
    <section
      className="safety-comparison"
      aria-label="같은 사건의 세 가지 처리 방식"
    >
      <div className="safety-comparison-head">
        <span className="eyebrow">비교 실험 · 저장된 실행 기록</span>
        <h2>확인만으로는 부족한 순간</h2>
        <p>
          답변 준비 → 유효성 확인 → 원문 변경 → 작업 기록. 확인과 기록 사이에
          변경을 넣었습니다.
        </p>
      </div>
      <div className="safety-tables">
        {data.databases.map((db) => (
          <div key={db.database}>
            <h3>{db.database}</h3>
            <div
              className="safety-table-scroll"
              tabIndex={0}
              role="region"
              aria-label={`${db.database} 비교 결과`}
            >
              <table>
                <thead>
                  <tr>
                    <th>처리 방식</th>
                    <th>
                      오래된 결과 허용
                      <br />
                      <small>낮을수록 좋음</small>
                    </th>
                    <th>
                      정상 결과 오거절
                      <br />
                      <small>낮을수록 좋음</small>
                    </th>
                    <th>
                      중복 기록
                      <br />
                      <small>낮을수록 좋음</small>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {db.results.map((r) => (
                    <tr
                      key={r.strategy}
                      className={
                        r.strategy === "atomic_guard" ? "safety-guard-row" : ""
                      }
                    >
                      <th>{labels[r.strategy]}</th>
                      <td>
                        {r.totals.stale_accepts} /{" "}
                        {r.totals.stale_opportunities}
                      </td>
                      <td>
                        {r.totals.false_rejects} /{" "}
                        {r.totals.valid_first_action_opportunities}
                      </td>
                      <td>
                        {r.totals.duplicate_commits} /{" "}
                        {r.totals.retry_opportunities}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
      <p className="safety-scope">
        DB별·방식별 고정 시나리오 9개, 제출 10회입니다. 두 DB의 결과를 합쳐
        성공률을 부풀리지 않습니다. 무작위 부하·검색 정확도·실서비스 안전성
        평가는 아닙니다. 기록 시각: {data.measured_at.slice(0, 10)} UTC.
      </p>
      <div className="safety-links">
        <a
          href={repo + "docs/safety-case-study.md"}
          target="_blank"
          rel="noreferrer"
        >
          사건 순서와 비교 조건 ↗
        </a>
        <a
          href={repo + "docs/evidence/safety-evaluation.json"}
          target="_blank"
          rel="noreferrer"
        >
          실행 원본 JSON ↗
        </a>
        <a
          href={repo + "docs/action-contract.md"}
          target="_blank"
          rel="noreferrer"
        >
          보장 범위와 한계 ↗
        </a>
      </div>
    </section>
  );
}
