import { ArrowUpRight, Check, Clock3, FlaskConical } from "lucide-react";
import evidenceData from "./operations-evidence.json";
import { PUBLIC_API_BASE } from "./api";

export type EvidenceRecord = {
  id: string;
  title: string;
  status: "pending" | "observed" | "partial" | "failed";
  observedAt: string | null;
  environment: string;
  summary: string;
  metrics: { label: string; value: string | number; unit?: string }[];
  findings: string[];
  table: { columns: string[]; rows: (string | number)[][] } | null;
  source: { label: string; href: string };
};
export type OperationsEvidence = {
  updatedAt: string | null;
  scope: string;
  records: EvidenceRecord[];
};
const evidence = evidenceData as OperationsEvidence;
const statusLabels: Record<EvidenceRecord["status"], string> = {
  pending: "검증 대기",
  observed: "관측 완료",
  partial: "일부 확인",
  failed: "실패 관측",
};
const dateLabel = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        hour12: false,
      }) + " KST"
    : "아직 기록되지 않음";

export default function Evidence() {
  const observed = evidence.records.filter(
    (record) => record.status === "observed",
  ).length;
  return (
    <section className="evidence-page" aria-label="운영 검증 기록">
      <div className="evidence-summary">
        <div>
          <span className="eyebrow">실행으로 남긴 근거</span>
          <h2>운영 실험 결과</h2>
          <p>
            실험 환경과 관측 시각을 함께 남깁니다. 이 페이지는 저장된 검증
            기록이며 실시간 상태판이 아닙니다.
          </p>
        </div>
        <div className="evidence-count">
          <strong>
            {String(observed).padStart(2, "0")}
            <span> / {String(evidence.records.length).padStart(2, "0")}</span>
          </strong>
          <span>관측 완료 · 전체 검증 항목</span>
        </div>
      </div>
      <div className="evidence-updated">
        <Clock3 size={14} /> 기록 갱신: {dateLabel(evidence.updatedAt)}
      </div>
      <div className="evidence-records">
        {evidence.records.map((record, index) => (
          <article className="evidence-record" key={record.id}>
            <div className="evidence-record-heading">
              <span className="evidence-number">0{index + 1}</span>
              <div>
                <h3>{record.title}</h3>
                <p>{record.environment}</p>
              </div>
              <span className={`evidence-status ${record.status}`}>
                {record.status === "observed" ? (
                  <Check size={13} />
                ) : (
                  <FlaskConical size={13} />
                )}
                {statusLabels[record.status]}
              </span>
            </div>
            <div className="evidence-record-body">
              <p>{record.summary}</p>
              {record.metrics.length > 0 && (
                <dl className="evidence-metrics">
                  {record.metrics.map((metric) => (
                    <div key={metric.label}>
                      <dt>{metric.label}</dt>
                      <dd>
                        {metric.value}
                        <small>{metric.unit}</small>
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
              {record.table && record.table.rows.length > 0 && (
                <div
                  className="evidence-table-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label={`${record.title} 결과 표`}
                >
                  <table className="evidence-table">
                    <thead>
                      <tr>
                        {record.table.columns.map((column) => (
                          <th key={column} scope="col">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {record.table.rows.map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {record.findings.length > 0 && (
                <ul className="evidence-findings">
                  {record.findings.map((finding) => (
                    <li key={finding}>{finding}</li>
                  ))}
                </ul>
              )}
              {record.status === "pending" && (
                <p className="evidence-pending">
                  측정값을 아직 게시하지 않았습니다. 구성과 검증 절차는 아래
                  원본에서 확인할 수 있습니다.
                </p>
              )}
              <div className="evidence-record-footer">
                <span>관측: {dateLabel(record.observedAt)}</span>
                <a href={record.source.href} target="_blank" rel="noreferrer">
                  {record.source.label}
                  <ArrowUpRight size={15} />
                </a>
              </div>
            </div>
          </article>
        ))}
      </div>
      <div className="section-heading evidence-decisions-heading">
        <div>
          <span className="eyebrow">설계 선택과 비용</span>
          <h2>성능·복잡도·비용 비교</h2>
        </div>
      </div>
      <div className="design-decisions evidence-decisions">
        <article>
          <span>01 / 격리</span>
          <h3>느린 추론이 API를 막지 않게</h3>
          <p>
            CPU 작업과 요청 처리를 분리하면 장애 경계도 나뉩니다. 네트워크
            왕복과 프로세스 메모리 비용은 추가로 지불합니다.
          </p>
          <small>확인할 근거 · 지연 분포, 이벤트 루프 지연, 과부하 응답</small>
        </article>
        <article>
          <span>02 / 복제</span>
          <h3>복제본 수보다 상태의 일관성</h3>
          <p>
            인스턴스를 늘려도 멱등성과 버전 검증은 유지되어야 합니다. 공유
            저장소와 재시작 검증을 함께 확인합니다.
          </p>
          <small>확인할 근거 · 동시 요청, 롤아웃, 준비 상태</small>
        </article>
        <article>
          <span>03 / 비용</span>
          <h3>한도 안에서 먼저 측정하기</h3>
          <p>
            동시 실행과 대기열에 상한을 두고, 지연과 자원 사용을 관측한 뒤
            용량을 늘립니다. 무료 공개 데모에는 시작 지연이 생길 수 있습니다.
          </p>
          <small>확인할 근거 · CPU·메모리, 처리량, 거절 비율</small>
        </article>
      </div>
      <div className="scope-note evidence-scope">
        <strong>이 기록이 말해주는 범위</strong>
        <p>{evidence.scope}</p>
        <a href={`${PUBLIC_API_BASE}/health`} target="_blank" rel="noreferrer">
          공개 API 상태 응답 열기 <ArrowUpRight size={15} />
        </a>
      </div>
    </section>
  );
}
