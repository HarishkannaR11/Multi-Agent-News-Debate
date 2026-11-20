import { describe, expect, it } from "vitest";
import {
  attributionLabel,
  barPercent,
  factIndex,
  isMarketGenerating,
  latestOf,
  marketStatusLabel,
  outcomeLabel,
  regimeLabel,
  rejectedAttempts,
  signedPct,
  signedPp,
  sparkPath,
  stageText,
  type AgentState,
  type SeriesInfo,
} from "./markets";

const agent = (status: AgentState["status"]): AgentState => ({ status, attempts: 1, error: null, content: null, audit: [] });
const agents = (a: AgentState["status"], b: AgentState["status"], c: AgentState["status"]) => ({
  bull: agent(a),
  bear: agent(b),
  skeptic: agent(c),
});

describe("labels", () => {
  it("names regimes and attributions, falling back to readable text", () => {
    expect(regimeLabel("global_risk_off")).toBe("Global risk-off");
    expect(regimeLabel("something_new")).toBe("something new");
    expect(regimeLabel("")).toBe("Unknown");
    expect(attributionLabel("imported")).toBe("Mostly imported");
    expect(attributionLabel("")).toBe("Not computed");
  });
  it("describes validator outcomes", () => {
    expect(outcomeLabel("rejected")).toBe("Rejected by the validator");
    expect(outcomeLabel("odd")).toBe("odd");
  });
  it("reports day status honestly", () => {
    expect(marketStatusLabel({ status: "done", agents: agents("completed", "completed", "completed") })).toBe("Complete");
    expect(marketStatusLabel({ status: "partial", agents: agents("completed", "failed", "completed") })).toBe("Partial (2 of 3 analysts)");
    expect(marketStatusLabel({ status: "generating", agents: agents("pending", "pending", "pending") })).toBe("Generating");
    expect(marketStatusLabel({ status: "failed", agents: agents("failed", "failed", "failed") })).toBe("Generation failed");
    expect(isMarketGenerating({ status: "generating" })).toBe(true);
    expect(stageText("verdict")).toContain("verdict");
  });
});

describe("numbers", () => {
  it("formats signed percentages and points", () => {
    expect(signedPct(0.824)).toBe("+0.82%");
    expect(signedPct(-1.2)).toBe("−1.20%");
    expect(signedPct(null)).toBe("—");
    expect(signedPp(-0.554)).toBe("−0.55 pp");
  });
  it("scales bars to a shared maximum and clamps", () => {
    expect(barPercent(-0.45, 0.9)).toBe(50);
    expect(barPercent(2, 0.9)).toBe(100);
    expect(barPercent(1, 0)).toBe(0);
  });
});

describe("series", () => {
  const info = (points: [string, number][]): SeriesInfo => ({
    label: "x", unit: "u", status: "ok", detail: "", source: "s", source_url: "", last_date: "", points,
  });
  it("draws a path from first to last point within the box", () => {
    const path = sparkPath([["a", 1], ["b", 3], ["c", 2]], 100, 20);
    expect(path.startsWith("M2.0 18.0")).toBe(true);
    expect(path.split("L")).toHaveLength(3);
    expect(sparkPath([["a", 1]], 100, 20)).toBe("");
    expect(sparkPath([["a", 5], ["b", 5]], 100, 20)).toContain("M2.0");
  });
  it("finds the latest value and its change", () => {
    const latest = latestOf(info([["a", 100], ["b", 101]]));
    expect(latest?.date).toBe("b");
    expect(latest?.changePct).toBeCloseTo(1, 6);
    expect(latestOf(info([["a", 100]]))?.changePct).toBeNull();
    expect(latestOf(info([]))).toBeNull();
  });
  it("indexes facts and counts failed attempts", () => {
    expect(factIndex([{ id: "M1", series: "S", kind: "k", text: "t", numbers: [], as_of: "d" }]).get("M1")?.text).toBe("t");
    expect(rejectedAttempts([
      { attempt: 1, at: "", outcome: "rejected", rejections: [] },
      { attempt: 2, at: "", outcome: "accepted", rejections: [] },
    ])).toBe(1);
  });
});
