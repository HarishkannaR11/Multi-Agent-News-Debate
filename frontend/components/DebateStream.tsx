"use client";

import { useEffect, useState } from "react";
import { connectDebateStream, type DebateStreamEvent } from "@/lib/api";
import { AgentCard } from "./AgentCard";
import { AgentStatusDots, type AgentDotState } from "./AgentStatusDots";
import { OpinionBox } from "./OpinionBox";
import { VerdictPanel } from "./VerdictPanel";

const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"];

export function DebateStream({ debateId }: { debateId: string }) {
  const [status, setStatus] = useState("connecting");
  const [args, setArgs] = useState<Record<string, string>>({});
  const [verdict, setVerdict] = useState("");
  const [biasScores, setBiasScores] = useState<Record<string, number>>({});

  useEffect(() => {
    const ws = connectDebateStream(debateId, (event: DebateStreamEvent) => {
      if (event.status) setStatus(event.status);
      if (event.data) setArgs((prev) => ({ ...prev, ...event.data }));
      if (event.verdict) setVerdict(event.verdict);
      if (event.bias_scores && Object.keys(event.bias_scores).length > 0) {
        setBiasScores(event.bias_scores);
      }
    });
    return () => ws.close();
  }, [debateId]);

  const dotStates: Record<string, AgentDotState> = Object.fromEntries(
    PERSONAS.map((persona) => [
      persona,
      status === "done" ? "done" : args[persona] ? "active" : "waiting",
    ])
  );

  return (
    <div>
      <AgentStatusDots states={dotStates} />
      <p className="mt-4 font-sans text-xs uppercase tracking-[0.04em] text-muted">
        {status === "fetching" && "Fetching today's story..."}
        {status === "debating" && "Analysts are drafting opening arguments..."}
        {status === "rebuttal" && "Analysts are drafting rebuttals..."}
        {status === "done" && "Debate complete."}
      </p>
      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
        {PERSONAS.map((persona) => (
          <AgentCard key={persona} persona={persona} argument={args[persona]} />
        ))}
      </div>
      <VerdictPanel verdict={verdict} biasScores={biasScores} />
      <OpinionBox debateId={debateId} userId="guest" />
    </div>
  );
}
