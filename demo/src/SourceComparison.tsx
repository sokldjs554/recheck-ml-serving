import type { EvidenceReceipt, Source } from "./evidenceApi";

/** Compare the receipt's own citations, never the currently selected editor document. */
export default function SourceComparison({ receipt, sources, historical = false }: {
  receipt: EvidenceReceipt; sources: Source[]; historical?: boolean;
}) {
  const changed = receipt.references.some(ref => sources.some(source => source.source_id === ref.source_id && (source.deleted || source.revision !== ref.revision)));
  return <details className="source-comparison" data-testid="source-comparison" aria-label="답변의 근거 대조" open={changed}>
    <summary>{changed ? "인용 원문과 변경된 원문" : "인용 원문과 확인한 버전"}</summary>
    {receipt.references.map(ref => {
      const current = sources.find(source => source.source_id === ref.source_id);
      const changed = !!current && (current.deleted || current.revision !== ref.revision);
      return <div className={`source-pair ${changed ? "is-changed" : ""}`} key={ref.source_id}>
        <p className="source-pair-name">{ref.title}</p>
        <div className="source-pair-texts">
          <div><h4>답변에 인용된 원문</h4><p data-testid="cited-source">{ref.text}</p></div>
          <div><h4>{historical ? "마지막 확인 원문" : "현재 원문"}</h4><p data-testid="current-source">{!current ? "아직 확인하지 못했습니다." : current.deleted ? "삭제된 문서입니다." : current.text}</p></div>
        </div>
        <p className="source-pair-state">{!current ? "원문 확인 필요" : changed ? "인용 이후 원문 변경 · 이 답변으로는 새 기록을 만들 수 없습니다." : "확인한 원문과 인용 버전 일치 · 기록 요청 시 서버에서 다시 검사합니다."}</p>
        <details><summary>문서 버전</summary><p>인용 v{ref.revision} / 확인 {current ? `v${current.revision}` : "전"}</p></details>
      </div>;
    })}
  </details>;
}
