import { afterEach, expect, it, vi } from "vitest";
import { EvidenceApi, EvidenceApiError } from "./evidenceApi";

afterEach(() => vi.unstubAllGlobals());
it("retains the machine-readable expiry reason on non-execute evidence requests", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "session_missing_or_expired" }), {
          status: 404,
        }),
      ),
  );
  const request = new EvidenceApi("http://localhost:8023").state("expired");
  await expect(request).rejects.toBeInstanceOf(EvidenceApiError);
  await expect(request).rejects.toMatchObject({
    status: 404,
    detail: "session_missing_or_expired",
  });
});
