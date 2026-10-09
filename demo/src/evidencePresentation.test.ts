import { expect, test } from "vitest";
import * as presentation from "./evidencePresentation";
import type { EvidenceReceipt, EvidenceState, UseResult } from "./evidenceApi";
const receipt = {
  id: "r",
  release_epoch: 1,
  expires_at: 200,
  references: [{ source_id: "transfer", revision: 1 }],
} as EvidenceReceipt;
const valid = { valid: true, receipt_id: "r", reason: "current" } as UseResult;
const current = {
  sources: [{ source_id: "transfer", revision: 1, deleted: false }],
  active_release: { release_epoch: 1 },
} as EvidenceState;
test("a later state read cannot revive a validation issued before a source update", () => {
  expect(
    presentation.visibleValidation(valid, receipt, current, 100000)?.valid,
  ).toBe(true);
  expect(
    presentation.visibleValidation(
      valid,
      receipt,
      { ...current, sources: [{ ...current.sources[0], revision: 2 }] },
      100000,
    ),
  ).toBeNull();
});
test("expired or replaced releases suppress an old valid badge; explicit refusal remains visible", () => {
  expect(
    presentation.visibleValidation(valid, receipt, current, 200000),
  ).toBeNull();
  expect(
    presentation.visibleValidation(
      valid,
      receipt,
      {
        ...current,
        active_release: { ...current.active_release, release_epoch: 2 },
      },
      100000,
    ),
  ).toBeNull();
  const refused = { ...valid, valid: false, reason: "source_changed" };
  expect(
    presentation.visibleValidation(refused, receipt, current, 100000),
  ).toEqual(refused);
});

test("external content changes mark a passing report stale even while index needs rebuild", () => {
  const state = {
    sources: [],
    index_stale: true,
    corpus_hash: "new-content",
    active_release: { release_epoch: 1, corpus_hash: "old-content" },
  } as unknown as EvidenceState;
  const report = {
    passed: true,
    base_release_epoch: 1,
    corpus_hash: "old-content",
  } as import("./evidenceApi").ReleaseReport;
  expect(presentation.staleRelease(report, state)).toBe(true);
});
