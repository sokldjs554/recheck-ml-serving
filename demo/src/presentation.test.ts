import { describe, it, expect } from "vitest";
import { currentValidation, comparisonConfirmed, raceReproduced } from "./presentation";
import type { Receipt, Validation } from "./types";
const versions = {
  feature_version: 1,
  policy_version: 1,
  model_version: "risk-v1",
};
const receipt: Receipt = {
  ...versions,
  id: "receipt",
  session_id: "session",
  status: "clear",
  reason: "no_current_warning",
  risk_score: 0.1,
  created_at: "2026-10-08T00:00:00.000Z",
  expires_at: "2026-10-08T00:00:20.000Z",
  latency_ms: 12,
  trace_id: "trace",
  spans: [],
  protected: true,
  model_hash: "hash",
};
const validation: Validation = {
  valid: true,
  reason: "current",
  current_versions: versions,
};
describe("honest outcome presentation", () => {
  it("does not claim a stale race when live inference snapshots the already mutated version", () => {
    expect(raceReproduced(receipt, versions)).toBe(false);
    expect(raceReproduced(receipt, { ...versions, feature_version: 2 })).toBe(true);
    expect(raceReproduced(undefined, { ...versions, feature_version: 2 })).toBe(false);
  });
  it("stops showing a previous successful validation at expiry", () => {
    expect(
      currentValidation(
        validation,
        receipt,
        versions,
        Date.parse(receipt.expires_at),
      )?.valid,
    ).toBe(false);
    expect(
      currentValidation(
        validation,
        receipt,
        versions,
        Date.parse(receipt.expires_at),
      )?.reason,
    ).toBe("receipt_expired");
  });
  it("stops showing a previous successful validation after a version change", () => {
    expect(
      currentValidation(
        validation,
        receipt,
        { ...versions, feature_version: 2 },
        Date.parse(receipt.created_at),
      )?.valid,
    ).toBe(false);
  });
  it("does not claim comparison success if either run failed or returned review", () => {
    const baseline = { ...receipt, protected: false };
    const protectedReceipt = {
      ...receipt,
      status: "invalidated" as const,
      reason: "versions_changed",
    };
    expect(comparisonConfirmed(undefined, protectedReceipt)).toBe(false);
    expect(comparisonConfirmed(baseline, undefined)).toBe(false);
    expect(
      comparisonConfirmed({ ...baseline, status: "review" }, protectedReceipt),
    ).toBe(false);
    expect(
      comparisonConfirmed(baseline, { ...protectedReceipt, status: "review" }),
    ).toBe(false);
    expect(comparisonConfirmed(baseline, protectedReceipt)).toBe(true);
  });
});
