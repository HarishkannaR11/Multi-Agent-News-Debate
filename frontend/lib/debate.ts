// Types and pure helpers for showing a debate. Nothing here touches the network or the browser, so it is all unit-tested.
import type { Debate } from "./api";

// The five analysts in display order, with their names.
export const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"] as const;
export type Persona = (typeof PERSONAS)[number];
export const PERSONA_LABELS: Record<Persona, string> = {
  left: "Left Analyst",
  right: "Right Analyst",
  economist: "Economist",
  geopolitical: "Geopolitical Analyst",
  devil: "Devil's Advocate",
};
// Shorter names for tabs on narrow screens.
export const PERSONA_SHORT: Record<Persona, string> = {
  left: "Left",
  right: "Right",
  economist: "Economist",
  geopolitical: "Geopolitical",
  devil: "Devil's Advocate",
};

// What an analyst can be doing.
export type PerspectiveState = "pending" | "generating" | "completed" | "failed";

// A claim's label. "verified" is part of the vocabulary but the app never assigns it: no fact-checking step exists.
export type ClaimStatus = "opinion" | "assumption" | "unverified" | "disputed" | "verified";
export type Claim = {
  id: string;
  text: string;
  type: "factual" | "opinion" | "assumption";
  status: ClaimStatus;
  source_ids: string[];
};

export type PerspectiveContent = {
  position_summary: string;
  strongest_argument: string;
  claims: Claim[];
  counterargument: string;
  assumptions: string[];
  uncertainties: string[];
};

export type PerspectiveRecord = {
  status: PerspectiveState;
  attempts: number;
  error: string | null;
  content: PerspectiveContent | null;
};

// A related news article found for the question (never invented; not fact-checked evidence).
export type Source = { id: string; title: string; publisher: string; url: string; published_at: string; excerpt: string };

export type MapItem = { id: string; summary: string; claim_ids: string[] };
export type MapGroup = "agreements" | "interpretations" | "conflicts" | "unresolved" | "evidence_needed";
export type Disagreements = Partial<Record<MapGroup, MapItem[]>> & { central_question?: string; error?: string };

export type Verdict = {
  summary: string;
  strongest_arguments: { perspective: Persona; argument: string }[];
  evidence_supports: string;
  strongest_counterargument: string;
  conflicting_or_insufficient_evidence: string;
  unresolved_questions: string[];
  criteria: { name: string; assessment: string }[];
  reasoning: string;
  conclusion: string;
  evidence_sufficiency: "sufficient" | "limited" | "insufficient";
  could_change_conclusion: string[];
  limitations: string[];
  based_on: { perspectives: number; of: number; sources: number };
};

// ---- the question the visitor types -----------------------------------------------------------------------------

export type QuestionCheck = { ok: true; value: string } | { ok: false; message: string };

// Mirrors the server's rules so mistakes are caught before sending. The server still validates everything itself.
export function checkQuestion(raw: string, min: number, max: number): QuestionCheck {
  // Trim and collapse all whitespace (newlines included), exactly as the server does.
  const value = raw.split(/\s+/).filter(Boolean).join(" ");
  if (!value) return { ok: false, message: "Enter a question or topic to debate." };
  if (value.length < min) return { ok: false, message: `Make it at least ${min} characters so the analysts have something to debate.` };
  if (value.length > max) return { ok: false, message: `Keep it under ${max} characters (yours is ${value.length}).` };
  const words = value.match(/[\p{L}\p{N}]+/gu) ?? [];
  if (words.length < 2) return { ok: false, message: "Write a full question or statement (at least two words)." };
  const alnum = (value.match(/[\p{L}\p{N}]/gu) ?? []).length;
  if (alnum / value.length < 0.5) return { ok: false, message: "That does not look like a question or topic. Use words rather than symbols." };
  return { ok: true, value };
}

// A random id for one form, used to make a double submit safe.
export function newRequestId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// ---- reading the stored debate ------------------------------------------------------------------------------------

// Is the server still working on this debate?
export function isGenerating(debate: Debate): boolean {
  return debate.status === "generating";
}

// A debate started by a visitor has structured perspectives; a daily debate has plain text only.
export function isStructured(debate: Debate): boolean {
  return Boolean(debate.perspectives && Object.keys(debate.perspectives).length > 0);
}

// What the page shows for one analyst, whether the debate is structured or an older plain-text one.
export type PerspectiveView = {
  persona: Persona;
  state: PerspectiveState;
  error: string | null;
  attempts: number;
  content: PerspectiveContent | null;
  // For older debates: the plain opening argument and rebuttal.
  legacy: { argument: string; rebuttal?: string; closing?: string } | null;
};

export function perspectiveViews(debate: Debate): PerspectiveView[] {
  return PERSONAS.map((persona) => {
    const record = debate.perspectives?.[persona];
    if (record) {
      return { persona, state: record.status, error: record.error, attempts: record.attempts, content: record.content, legacy: null };
    }
    const argument = debate.arguments?.[persona];
    if (argument) {
      return {
        persona,
        state: "completed" as const,
        error: null,
        attempts: 1,
        content: null,
        legacy: { argument, rebuttal: debate.rebuttals?.[persona], closing: debate.crossfire?.[persona] },
      };
    }
    // An older debate whose analyst never produced text: honestly shown as not completed.
    return { persona, state: "failed" as const, error: "This analyst did not produce a perspective.", attempts: 0, content: null, legacy: null };
  });
}

// How many analysts have finished.
export function completedCount(views: PerspectiveView[]): number {
  return views.filter((v) => v.state === "completed").length;
}

// A short label for the debate's overall state.
export function statusLabel(debate: Debate, views: PerspectiveView[]): string {
  const done = completedCount(views);
  if (debate.status === "generating") return "Generating";
  if (debate.status === "failed") return "Generation failed";
  if (debate.status === "partial") return `Partially complete (${done} of ${views.length} perspectives)`;
  return "Complete";
}

// What the server is doing right now, in words. Never a percentage: the server does not know one.
export function stageLabel(stage: string | undefined): string {
  switch (stage) {
    case "sources":
      return "Looking for related news coverage…";
    case "perspectives":
      return "The analysts are writing their perspectives…";
    case "synthesis":
      return "Comparing the positions and writing the verdict…";
    default:
      return "Starting…";
  }
}

// ---- claims, sources and the disagreement map -------------------------------------------------------------------------

export const CLAIM_LABELS: Record<ClaimStatus, string> = {
  opinion: "Opinion",
  assumption: "Assumption",
  unverified: "Unverified",
  disputed: "Disputed",
  verified: "Verified",
};

// Explains a claim's label in plain words (shown on hover/focus and in the legend).
export function claimExplanation(claim: Claim): string {
  switch (claim.status) {
    case "opinion":
      return "A value judgement or prediction. Evidence cannot settle it.";
    case "assumption":
      return "Something the analyst takes for granted.";
    case "disputed":
      return "A factual claim that another analyst contradicts (see the disagreement map). Not fact-checked.";
    case "verified":
      return "Checked against evidence.";
    default:
      return claim.source_ids.length > 0
        ? "A factual claim made by an AI analyst. It cites a related article, but it has not been fact-checked."
        : "A factual claim made by an AI analyst, with no source. It has not been fact-checked.";
  }
}

export type ClaimRef = { claim: Claim; persona: Persona };

// Every claim of the debate by id.
export function claimIndex(views: PerspectiveView[]): Map<string, ClaimRef> {
  const index = new Map<string, ClaimRef>();
  for (const view of views) for (const claim of view.content?.claims ?? []) index.set(claim.id, { claim, persona: view.persona });
  return index;
}

export const MAP_GROUPS: { key: MapGroup; title: string; hint: string }[] = [
  { key: "agreements", title: "Areas of agreement", hint: "Points that claims from different analysts share." },
  { key: "interpretations", title: "Different readings of shared facts", hint: "The same facts, read differently." },
  { key: "conflicts", title: "Directly conflicting claims", hint: "Claims that cannot all be true." },
  { key: "unresolved", title: "Unresolved questions", hint: "What the claims leave open." },
  { key: "evidence_needed", title: "Evidence needed to resolve this", hint: "What would settle a disagreement." },
];

// Which disagreement items mention a claim (so a claim can link to them).
export function itemsForClaim(claimId: string, disagreements: Disagreements | undefined): { group: MapGroup; item: MapItem }[] {
  if (!disagreements) return [];
  const found: { group: MapGroup; item: MapItem }[] = [];
  for (const { key } of MAP_GROUPS) {
    for (const item of disagreements[key] ?? []) if (item.claim_ids.includes(claimId)) found.push({ group: key, item });
  }
  return found;
}

// Which claims cite a source (so a source can link back to them).
export function claimsCiting(sourceId: string, index: Map<string, ClaimRef>): ClaimRef[] {
  return [...index.values()].filter((ref) => ref.claim.source_ids.includes(sourceId));
}

// Splits text into plain pieces and references like [left-1] or [S2]. Only ids that really exist become references;
// anything else stays plain text, so a made-up id can never become a link.
export type TextPart = { type: "text"; text: string } | { type: "ref"; id: string };
export function splitReferences(text: string, valid: Set<string>): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[([A-Za-z]+-\d+|S\d+)\]/g)) {
    if (!valid.has(match[1])) continue;
    if (match.index > last) parts.push({ type: "text", text: text.slice(last, match.index) });
    parts.push({ type: "ref", id: match[1] });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}

// Only http(s) links are ever shown as links (a source URL from outside is never trusted blindly).
export function safeHttpUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

// "2026-10-17" as "17 Oct 2026" (the date part is used as-is; no timezone guessing).
export function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(match[3])} ${months[Number(match[2]) - 1] ?? ""} ${match[1]}`;
}
