import type { EvidenceReceipt, EvidenceState, UseResult } from "./evidenceApi";
export function visibleValidation(
  validation: UseResult | null,
  receipt: EvidenceReceipt | null,
  state: EvidenceState | null,
  now: number,
): UseResult | null {
  if (
    !validation ||
    !receipt ||
    !state ||
    validation.receipt_id !== receipt.id ||
    now >= receipt.expires_at * 1000
  )
    return null;
  if (
    validation.valid &&
    (state.active_release.release_epoch !== receipt.release_epoch ||
      receipt.references.some((ref) => {
        const source = state.sources.find((s) => s.source_id === ref.source_id);
        return !source || source.deleted || source.revision !== ref.revision;
      }))
  )
    return null;
  return validation;
}

export function staleRelease(
  report: import("./evidenceApi").ReleaseReport | null,
  state: EvidenceState | null,
): boolean {
  return (
    !!report &&
    !!state &&
    (report.base_release_epoch !== state.active_release.release_epoch ||
      report.corpus_hash !== state.corpus_hash)
  );
}
