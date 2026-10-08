export type Mutation = "feature" | "policy" | "model";
export type Versions = {
  feature_version: number;
  policy_version: number;
  model_version: string;
};
export type Session = Versions & { session_id: string };
export type DecisionInput = {
  amount: number;
  recipient: string;
  idempotency_key: string;
  delay_ms: number;
  fault: "none" | "timeout" | "unavailable";
  protected: boolean;
};
export type Receipt = Versions & {
  id: string;
  session_id: string;
  status: "clear" | "review" | "invalidated";
  reason: string;
  risk_score: number | null;
  created_at: string;
  expires_at: string;
  latency_ms: number;
  trace_id: string;
  spans: {
    name: string;
    start_ms: number;
    duration_ms: number;
    status: "ok" | "error";
  }[];
  protected: boolean;
  model_hash: string;
};
export type Validation = {
  valid: boolean;
  reason: string;
  current_versions: Versions;
};
export interface Adapter {
  createSession(): Promise<Session>;
  decide(id: string, body: DecisionInput): Promise<Receipt>;
  mutate(id: string, kind: Mutation): Promise<Versions>;
  receipts(id: string): Promise<Receipt[]>;
  validate(id: string, receipt: string): Promise<Validation>;
}
