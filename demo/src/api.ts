import type {
  Adapter,
  DecisionInput,
  Mutation,
  Receipt,
  Session,
  Validation,
  Versions,
} from "./types";
export class LiveApi implements Adapter {
  readonly base: string;
  constructor(base: string) {
    base = base || globalThis.location.origin;
    const parsed = new URL(base);
    if (!["http:", "https:"].includes(parsed.protocol))
      throw new Error("HTTP 또는 HTTPS API 주소를 입력하세요.");
    this.base = base.replace(/\/$/, "");
  }
  private async request<T>(path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(this.base + path, {
        method: body === undefined ? "GET" : "POST",
        headers:
          body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`API ${response.status} · ${detail.slice(0, 200)}`);
      }
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError")
        throw new Error(
          "API 연결 시간이 초과되었습니다. 서버 주소와 상태를 확인하세요.",
        );
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  async health() {
    const result = await this.request<{
      status: string;
      service: string;
      mode: string;
    }>("/health");
    if (
      result.status !== "ok" ||
      result.service !== "recheck-api" ||
      result.mode !== "live"
    )
      throw new Error("RECHECK live API의 정상 응답이 아닙니다.");
    return result;
  }
  createSession() {
    return this.request<Session>("/api/sessions", {});
  }
  decide(id: string, body: DecisionInput) {
    return this.request<Receipt>(
      `/api/sessions/${encodeURIComponent(id)}/decisions`,
      body,
    );
  }
  mutate(id: string, kind: Mutation) {
    return this.request<Versions>(
      `/api/sessions/${encodeURIComponent(id)}/mutations`,
      { kind },
    );
  }
  async receipts(id: string) {
    return (
      await this.request<{ receipts: Receipt[] }>(
        `/api/sessions/${encodeURIComponent(id)}/decisions`,
      )
    ).receipts;
  }
  validate(id: string, receipt: string) {
    return this.request<Validation>(
      `/api/sessions/${encodeURIComponent(id)}/decisions/${encodeURIComponent(receipt)}/validate`,
    );
  }
}
