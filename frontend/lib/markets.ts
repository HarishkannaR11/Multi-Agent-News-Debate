// Types and pure helpers for the Markets pages (the daily market debate). Nothing here touches the browser, so it is
// all unit-tested. The data shapes mirror what GET /api/markets/{date} returns.
import { request } from "./api";

export const MARKET_ROLES = ["bull", "bear", "skeptic"] as const;
export type MarketRole = (typeof MARKET_ROLES)[number];
export const ROLE_LABELS: Record<MarketRole, string> = { bull: "Bull", bear: "Bear", skeptic: "Macro skeptic" };
export const ROLE_BLURBS: Record<MarketRole, string> = {
  bull: "Argues the constructive case from the data packet.",
  bear: "Argues the cautious case from the data packet.",
  skeptic: "Asks one question: was the move domestic, or imported (dollar, rupee, commodities, US yields)?",
};

export type MarketFact = { id: string; series: string; kind: string; text: string; numbers: number[]; as_of: string };
export type SeriesInfo = {
  label: string;
  unit: string;
  status: "ok" | "missing" | "stale";
  detail: string;
  source: string;
  source_url: string;
  last_date: string;
  points: [string, number][];
};
export type AttributionFactor = { series: string; lag: number; today_change: number; contribution_pct: number };
export type Attribution = {
  status: "ok" | "insufficient";
  reason?: string;
  label?: "imported" | "domestic" | "mixed" | "no_significant_move";
  confidence?: "low" | "moderate";
  actual_pct?: number;
  explained_pct?: number;
  residual_pct?: number;
  r2?: number;
  n_obs?: number;
  factors?: AttributionFactor[];
  method?: string;
};
export type Regime = { label: string; risk_off_signals: string[]; risk_on_signals: string[] };
export type Rejection = { code: string; message: string; claim: number | null };
export type AuditEntry = { attempt: number; at: string; outcome: string; rejections: Rejection[] };
export type MarketClaim = { id: string; text: string; kind: "observation" | "inference"; fact_ids: string[] };
export type MarketAgentContent = {
  stance: string;
  thesis: string;
  claims: MarketClaim[];
  caveats: string[];
  attribution?: string;
  attribution_reasoning?: string;
};
export type AgentState = {
  status: "pending" | "generating" | "completed" | "failed";
  attempts: number;
  error: string | null;
  content: MarketAgentContent | null;
  audit: AuditEntry[];
};
export type MarketVerdict = {
  summary: string;
  attribution_view: string;
  key_drivers: { text: string; fact_ids: string[] }[];
  bull_strongest: string;
  bear_strongest: string;
  what_would_change: string[];
  data_gaps: string[];
  conclusion: string;
  confidence: "low" | "moderate";
  limitations: string[];
  based_on: { analysts: number; of: number; facts: number };
};
export type MarketDay = {
  date: string;
  status: string;
  stage: string;
  created_at: string;
  packet: {
    as_of: string;
    requested_date: string;
    series: Record<string, SeriesInfo>;
    facts: MarketFact[];
    attribution: Attribution;
    regime: Regime;
    missing: { series: string; reason: string }[];
  };
  packet_sha256: string;
  verdict: Partial<MarketVerdict>;
  verdict_error: string;
  verdict_audit: AuditEntry[];
  agents: Record<MarketRole, AgentState>;
};
export type MarketSummary = {
  date: string;
  status: string;
  completed: number;
  nifty_close: number | null;
  nifty_pct: number | null;
  regime: string;
  attribution: string;
};

export function fetchMarketDay(date: string): Promise<MarketDay> {
  return request(`/api/markets/${encodeURIComponent(date)}`, undefined, "Failed to load the market day");
}

export function fetchMarketDays(limit = 20): Promise<{ items: MarketSummary[]; total: number }> {
  return request(`/api/markets?limit=${limit}`, undefined, "Failed to load the market days");
}

// ---- display helpers --------------------------------------------------------------------------------------------

const REGIME_LABELS: Record<string, string> = {
  global_risk_off: "Global risk-off",
  global_risk_on: "Global risk-on",
  domestic_led: "Domestic-led",
  mixed: "Mixed",
};
export function regimeLabel(code: string): string {
  return REGIME_LABELS[code] ?? (code ? code.replace(/_/g, " ") : "Unknown");
}

const ATTRIBUTION_LABELS: Record<string, string> = {
  imported: "Mostly imported",
  domestic: "Mostly domestic",
  mixed: "Mixed",
  unclear: "Unclear",
  no_significant_move: "No significant move",
};
export function attributionLabel(code: string): string {
  return ATTRIBUTION_LABELS[code] ?? (code ? code.replace(/_/g, " ") : "Not computed");
}

// A validator attempt's outcome in plain words.
const OUTCOMES: Record<string, string> = {
  accepted: "Accepted",
  rejected: "Rejected by the validator",
  unusable: "Reply was not usable JSON",
  blocked: "Blocked by the content filter",
  timeout: "Timed out",
  provider_error: "AI provider error",
};
export function outcomeLabel(code: string): string {
  return OUTCOMES[code] ?? code;
}

export function isMarketGenerating(day: Pick<MarketDay, "status">): boolean {
  return day.status === "generating";
}

export function marketStatusLabel(day: Pick<MarketDay, "status" | "agents">): string {
  const done = MARKET_ROLES.filter((r) => day.agents[r]?.status === "completed").length;
  if (day.status === "generating") return "Generating";
  if (day.status === "failed") return "Generation failed";
  if (day.status === "partial") return `Partial (${done} of ${MARKET_ROLES.length} analysts)`;
  return "Complete";
}

export function stageText(stage: string): string {
  if (stage === "agents") return "The analysts are writing their cases from the data packet…";
  if (stage === "verdict") return "The moderator is writing the verdict…";
  return "Starting…";
}

// "+0.82%" / "-1.20%" with an explicit sign, or an em dash when there is no value.
export function signedPct(value: number | null | undefined, places = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(places)}%`;
}

// Percentage points with a sign (for contributions to a move).
export function signedPp(value: number, places = 2): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(places)} pp`;
}

// The width (0 to 100) of a bar for `value`, given the largest absolute value shown (so bars share one scale).
export function barPercent(value: number, maxAbs: number): number {
  if (!maxAbs || maxAbs <= 0) return 0;
  return Math.min(100, Math.round((Math.abs(value) / maxAbs) * 100));
}

// The SVG path of a small trend line for a series. Returns "" when there are fewer than two points.
export function sparkPath(points: [string, number][], width: number, height: number, pad = 2): string {
  if (points.length < 2) return "";
  const values = points.map((p) => p[1]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (width - 2 * pad) / (points.length - 1);
  return points
    .map(([, v], i) => {
      const x = pad + i * step;
      const y = height - pad - ((v - min) / span) * (height - 2 * pad);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

// The latest value of a series with its day-over-day change in percent (null when there is no earlier point).
export function latestOf(info: SeriesInfo): { date: string; value: number; changePct: number | null } | null {
  const pts = info.points;
  if (pts.length === 0) return null;
  const [date, value] = pts[pts.length - 1];
  const prev = pts.length > 1 ? pts[pts.length - 2][1] : null;
  return { date, value, changePct: prev ? (value / prev - 1) * 100 : null };
}

// Facts by id, for linking a claim to the figures it rests on.
export function factIndex(facts: MarketFact[]): Map<string, MarketFact> {
  return new Map(facts.map((f) => [f.id, f]));
}

// How many validator attempts failed before the final result, for the audit summary line.
export function rejectedAttempts(audit: AuditEntry[]): number {
  return audit.filter((a) => a.outcome !== "accepted").length;
}
