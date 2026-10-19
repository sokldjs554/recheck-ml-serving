import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import CaseStudy from "./CaseStudy";
import CaseRunButton from "./CaseRunButton";
import { CaseFlow } from "./caseFlow";
import { CaseApi } from "./caseApi";
// Render the actual component; effects/subscriptions belong to browser checks.
vi.mock("react", async (original) => ({ ...await original<typeof import("react")>(), useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot() }));
function restoredView(step: number) {
  const flow = new CaseFlow(new CaseApi("http://localhost:8000"));
  const snapshot = { ...flow.getSnapshot(), step, restored: true };
  flow.getSnapshot = () => snapshot;
  return renderToStaticMarkup(<><CaseRunButton flow={flow} top /><CaseStudy flow={flow} configuredBase="http://localhost:8000" onConfigure={() => {}} onExplore={() => {}} onEvidence={() => {}} /></>);
}
it("completed restoration directs to saved results without offering a nonexistent resume", () => {
  const html = restoredView(6);
  expect(html).toContain("저장된 차단 결과와 작업 ID");
  expect(html).not.toContain("‘이어서 실행’");
  expect(html).toContain("브라우저 저장본");
  expect(html).toContain("복원만으로 새 요청을 보내거나 현재 서버 상태를 다시 확인하지 않습니다.");
});
it("interrupted restoration points to an actual resume button", () => {
  const html = restoredView(3);
  expect(html).toContain("‘이어서 실행’");
  expect(html).toMatch(/data-testid="case-run-top"[^>]*>/);
  expect(html).toContain("서버 확인 전");
});
