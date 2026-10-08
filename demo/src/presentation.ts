import type { Receipt, Validation, Versions } from "./types";
/** A successful server check is historical evidence, not a perpetual valid badge. */
export function currentValidation(
  validation: Validation | null,
  receipt: Receipt | null,
  versions: Versions | null,
  now: number,
): Validation | null {
  if (!validation || !receipt || !versions || !validation.valid)
    return validation;
  const changed =
    receipt.feature_version !== versions.feature_version ||
    receipt.policy_version !== versions.policy_version ||
    receipt.model_version !== versions.model_version;
  const reason = changed
    ? "versions_changed"
    : now >= Date.parse(receipt.expires_at)
      ? "receipt_expired"
      : null;
  return reason
    ? { valid: false, reason, current_versions: versions }
    : validation;
}
export function comparisonConfirmed(
  baseline: Receipt | undefined,
  protectedReceipt: Receipt | undefined,
): boolean {
  return (
    !!baseline &&
    !!protectedReceipt &&
    !baseline.protected &&
    protectedReceipt.protected &&
    baseline.status === "clear" &&
    protectedReceipt.status === "invalidated" &&
    protectedReceipt.reason === "versions_changed"
  );
}

/** A submitted-before-change request may still snapshot after the change over HTTP. */
export function raceReproduced(receipt: Receipt | undefined, mutation: Versions | undefined): boolean {
  return !!receipt && !!mutation && receipt.feature_version !== mutation.feature_version;
}
