import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultApiBase, LiveApi, PUBLIC_API_BASE } from "./api";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("API connection defaults", () => {
  it("offers the public API on GitHub Pages", () => {
    expect(defaultApiBase("sokldjs554.github.io", null)).toBe(PUBLIC_API_BASE);
  });
  it.each(["localhost", "127.0.0.1", "recheck-ml-serving.onrender.com", "github.io.evil.example"])("keeps %s on the same origin", (host) => {
    expect(defaultApiBase(host, null)).toBe("");
  });
  it.each(["", "https://my-api.example"])("honors a saved override including %j", (saved) => {
    expect(defaultApiBase("sokldjs554.github.io", saved)).toBe(saved);
  });
});

it("allows a cold-start health check longer than a normal request", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", (_: string, options: RequestInit) => new Promise((_resolve, reject) => {
    options.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }));
  let settled = false;
  const health = new LiveApi("https://api.example").health().catch(error => {
    settled = true;
    return error.message;
  });
  await vi.advanceTimersByTimeAsync(10001);
  expect(settled).toBe(false);
  await vi.advanceTimersByTimeAsync(80000);
  expect(await health).toContain("서버 시작");
});
