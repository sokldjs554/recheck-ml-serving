import type { CaseSnapshot } from "./caseFlow";

export type CaseStorage = { read: () => string | null; write: (value: string) => void; clear: () => void };
export type CaseCheckpoint = { version: 1; base: string; snapshot: CaseSnapshot; actionKey: string; oldActionKey: string };
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const reference = (v: unknown) => object(v) && text(v.source_id) && text(v.title) && text(v.text) && Number.isInteger(v.revision);
const source = (v: unknown) => reference(v) && object(v) && typeof v.deleted === "boolean";
const receipt = (v: unknown) => object(v) && text(v.id) && text(v.output) && typeof v.expires_at === "number" && Number.isFinite(v.expires_at) && Array.isArray(v.references) && v.references.every(reference);

/** Local display data is untrusted. Writes are always checked again by the API. */
export function parseCheckpoint(raw: string, base: string): CaseCheckpoint {
  if (raw.length > 1_000_000) throw new Error("checkpoint too large");
  const v: unknown = JSON.parse(raw);
  if (!object(v) || v.version !== 1 || v.base !== base || !text(v.actionKey) || !v.actionKey || !text(v.oldActionKey) || !v.oldActionKey || !object(v.snapshot)) throw new Error("checkpoint identity mismatch");
  const s = v.snapshot;
  if (!Number.isInteger(s.step) || (s.step as number) < 0 || (s.step as number) > 6 ||
      !["canReprepare", "busy", "running", "sessionExpired"].every(k => typeof s[k] === "boolean") ||
      !["session", "error", "status"].every(k => text(s[k])) ||
      !Array.isArray(s.events) || s.events.length > 512 || !s.events.every(e => object(e) && text(e.label) && text(e.at) && Number.isFinite(Date.parse(e.at))) ||
      (s.state !== null && (!object(s.state) || !Array.isArray(s.state.sources) || !s.state.sources.every(source))) ||
      (s.oldReceipt !== null && !receipt(s.oldReceipt)) || (s.freshReceipt !== null && !receipt(s.freshReceipt)) ||
      (s.report !== null && (!object(s.report) || !text(s.report.id) || typeof s.report.passed !== "boolean")) ||
      (s.action !== null && (!object(s.action) || !text(s.action.action_id) || !text(s.action.receipt_id) || !text(s.action.output) || typeof s.action.replayed !== "boolean"))) throw new Error("invalid checkpoint shape");
  const step = s.step as number;
  if ((step > 0 && (!s.session || !s.state || !s.oldReceipt)) ||
      (step >= 4 && !s.freshReceipt) || (step >= 5 && !s.action) ||
      (object(s.action) && object(s.freshReceipt) && s.action.receipt_id !== s.freshReceipt.id)) throw new Error("incomplete checkpoint");
  return v as unknown as CaseCheckpoint;
}

/** Same-tab only: no cross-tab coordination or persistence after closing the tab. */
export function browserCaseStorage(): CaseStorage {
  const key = "recheck-case-checkpoint-v1";
  return {
    read: () => window.sessionStorage.getItem(key),
    write: value => window.sessionStorage.setItem(key, value),
    clear: () => window.sessionStorage.removeItem(key),
  };
}

export function savedCaseBase(fallback: string, storage = browserCaseStorage()): string {
  try {
    const raw = storage.read();
    if (!raw || raw.length > 1_000_000) return fallback;
    const base = JSON.parse(raw).base;
    if (typeof base !== "string" || !["http:", "https:"].includes(new URL(base).protocol)) return fallback;
    return parseCheckpoint(raw, base).base;
  } catch { return fallback; }
}
