import audit from "../../docs/evidence/submission-2026-10-19/measurement-audit.json";

const repo = "https://github.com/sokldjs554/recheck-ml-serving/";

/** Archived measurements stay tied to their original source, never current HEAD. */
export default function MeasurementOrigin({ file }: { file: string }) {
  const record = audit.find((item) => item.file === file);
  if (!record) throw new Error(`Missing measurement provenance: ${file}`);
  const timestamp = record.dates.measured_at ?? record.dates.timestamp ?? record.dates.started_at;
  const date = new Date(timestamp!).toLocaleString("sv-SE", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
  const source = record.matching_revisions[0];
  const revision = source ?? record.stored_commit;
  return <p className="measurement-origin" data-testid="measurement-origin" data-evidence-file={file}>
    과거 실험 · <time dateTime={timestamp}>{date} KST</time>{" · "}
    <a href={`${repo}tree/${revision}`} target="_blank" rel="noreferrer">
      {source ? "소스 대조" : "자료 보관"} {revision.slice(0, 7)}
    </a>{" · "}현재 코드의 재측정값 아님{" · "}
    <a href={`${repo}blob/main/docs/measurement-provenance.md`} target="_blank" rel="noreferrer">조건·출처</a>
  </p>;
}
