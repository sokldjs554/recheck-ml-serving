import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import CaseStudy from "./CaseStudy";
import { CaseFlow } from "./caseFlow";
import { CaseApi } from "./caseApi";
// Render the actual component; effects/subscriptions belong to browser checks.
vi.mock("react", async (original) => ({ ...await original<typeof import("react")>(), useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot() }));
function restoredView(step: number) {
  const flow = new CaseFlow(new CaseApi("http://localhost:8000"));
  const snapshot = { ...flow.getSnapshot(), step, restored: true };
  flow.getSnapshot = () => snapshot;
  return renderToStaticMarkup(<CaseStudy flow={flow} configuredBase="http://localhost:8000" onConfigure={() => {}} onExplore={() => {}} onEvidence={() => {}} />);
}
it("completed restoration directs to saved results without offering a nonexistent resume", () => {
  const html = restoredView(6);
  expect(html).toContain("저장된 차단 결과와 작업 ID");
  expect(html).not.toContain("‘이어서 실행’");
  expect(html).toContain("브라우저에 복원한 과거 기록");
});
it("interrupted restoration points to an actual resume button", () => {
  const html = restoredView(3);
  expect(html).toContain("‘이어서 실행’");
  expect(html).toMatch(/data-testid="case-run-all"[^>]*>/);
  expect(html).toContain("서버 확인 전");
});
