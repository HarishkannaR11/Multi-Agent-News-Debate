import { describe, expect, it } from "vitest";
import type { Debate } from "./api";
import {
  checkQuestion,
  claimIndex,
  claimsCiting,
  formatDay,
  isGenerating,
  isStructured,
  itemsForClaim,
  perspectiveViews,
  safeHttpUrl,
  splitReferences,
  stageLabel,
  statusLabel,
  type PerspectiveRecord,
} from "./debate";

const claim = (id: string, text = "A claim", source_ids: string[] = []) =>
  ({ id, text, type: "factual", status: "unverified", source_ids }) as const;
const done = (persona: string, claims = [claim(`${persona}-1`)]): PerspectiveRecord => ({
  status: "completed",
  attempts: 1,
  error: null,
  content: { position_summary: "p", strongest_argument: "s", claims, counterargument: "c", assumptions: [], uncertainties: [] },
});
const base = {
  id: "2026-10-18:q-1",
  date: "2026-10-18",
  topic: "T",
  news_context: "",
  verdict: "",
  status: "done",
  arguments: {},
  rebuttals: {},
  bias_scores: {},
};

describe("checkQuestion", () => {
  it("rejects empty and whitespace-only input", () => {
    for (const raw of ["", "   ", "\n\t \n"]) expect(checkQuestion(raw, 10, 500)).toMatchObject({ ok: false });
  });
  it("collapses whitespace but keeps the wording", () => {
    expect(checkQuestion("  Should   AI code\n be reviewed?  ", 10, 500)).toEqual({ ok: true, value: "Should AI code be reviewed?" });
  });
  it("enforces length, word count and symbol ratio like the server", () => {
    expect(checkQuestion("Too short", 10, 500)).toMatchObject({ ok: false });
    expect(checkQuestion("x ".repeat(400), 10, 500)).toMatchObject({ ok: false });
    expect(checkQuestion("Hello?????????????", 10, 500)).toMatchObject({ ok: false });
    expect(checkQuestion("ab cd ??????????????", 10, 500)).toMatchObject({ ok: false });
  });
  it("accepts other languages", () => {
    expect(checkQuestion("¿Debería regularse la inteligencia artificial?", 10, 500).ok).toBe(true);
  });
});

describe("splitReferences", () => {
  const valid = new Set(["left-1", "S2"]);
  it("turns only real ids into references", () => {
    expect(splitReferences("See [left-1], not [ghost-4], and [S2].", valid)).toEqual([
      { type: "text", text: "See " },
      { type: "ref", id: "left-1" },
      { type: "text", text: ", not [ghost-4], and " },
      { type: "ref", id: "S2" },
      { type: "text", text: "." },
    ]);
  });
  it("returns plain text when there is nothing to link", () => {
    expect(splitReferences("No refs [S9]", valid)).toEqual([{ type: "text", text: "No refs [S9]" }]);
  });
});

describe("safeHttpUrl", () => {
  it("allows only http and https", () => {
    expect(safeHttpUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,x")).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
  });
});

describe("perspectiveViews", () => {
  it("uses structured records, including failed and pending ones, as they are", () => {
    const debate = {
      ...base,
      status: "partial",
      perspectives: {
        left: done("left"),
        right: { status: "failed", attempts: 3, error: "The AI provider took too long to respond.", content: null },
        economist: { status: "generating", attempts: 0, error: null, content: null },
      },
    } as Debate;
    const views = perspectiveViews(debate);
    expect(views.map((v) => v.state)).toEqual(["completed", "failed", "generating", "failed", "failed"]);
    expect(views[1].error).toMatch(/too long/);
    expect(statusLabel(debate, views)).toBe("Partially complete (1 of 5 perspectives)");
    expect(isStructured(debate)).toBe(true);
  });
  it("shows older plain-text debates as completed analysts without invented structure", () => {
    const debate = { ...base, status: "done", arguments: { left: "L", devil: "D" }, rebuttals: { left: "LR" } } as Debate;
    const views = perspectiveViews(debate);
    expect(views[0]).toMatchObject({ state: "completed", content: null, legacy: { argument: "L", rebuttal: "LR" } });
    expect(views[1].state).toBe("failed");
    expect(isStructured(debate)).toBe(false);
  });
  it("labels the states and stages without inventing progress numbers", () => {
    expect(isGenerating({ ...base, status: "generating" } as Debate)).toBe(true);
    expect(statusLabel({ ...base, status: "done" } as Debate, [])).toBe("Complete");
    expect(stageLabel("perspectives")).toMatch(/analysts/);
    expect(stageLabel(undefined)).toBe("Starting…");
    expect(stageLabel("synthesis")).not.toMatch(/%/);
  });
});

describe("claim links", () => {
  const debate = {
    ...base,
    perspectives: { left: done("left", [claim("left-1", "x", ["S1"])]), right: done("right", [claim("right-1", "y", ["S1", "S2"])]) },
    disagreements: { conflicts: [{ id: "C1", summary: "s", claim_ids: ["left-1", "right-1"] }], agreements: [] },
  } as Debate;
  const index = claimIndex(perspectiveViews(debate));
  it("finds the disagreement items a claim belongs to", () => {
    expect(itemsForClaim("left-1", debate.disagreements).map((x) => x.item.id)).toEqual(["C1"]);
    expect(itemsForClaim("left-9", debate.disagreements)).toEqual([]);
  });
  it("finds the claims that cite a source", () => {
    expect(claimsCiting("S1", index).map((r) => r.claim.id)).toEqual(["left-1", "right-1"]);
    expect(claimsCiting("S2", index).map((r) => r.claim.id)).toEqual(["right-1"]);
  });
});

describe("formatDay", () => {
  it("formats a stored date", () => {
    expect(formatDay("2026-10-07")).toBe("7 Oct 2026");
    expect(formatDay("garbage")).toBe("garbage");
  });
});
