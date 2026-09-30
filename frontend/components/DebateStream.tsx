"use client";

import { useEffect, useState } from "react";
import { connectDebateStream, type ConnectionState, type DebateStreamEvent } from "@/lib/api";
import { AgentCard } from "./AgentCard";
import { AgentStatusDots, type AgentDotState } from "./AgentStatusDots";
import { OpinionBox } from "./OpinionBox";
import { VerdictPanel } from "./VerdictPanel";

const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"];

function statusMessage(connection: ConnectionState, status: string): string {
  if (connection === "failed") return "Connection lost. Refresh the page to try again.";
  if (connection === "reconnecting") return "Connection lost. Reconnecting...";
  if (status === "fetching") return "Loading the debate...";
  if (status === "debating") return "Opening arguments";
  if (status === "rebuttal") return "Rebuttals";
  if (status === "done") return "Debate complete.";
  return "Connecting...";
}

export function DebateStream({ debateId }: { debateId: string }) {
  const [status, setStatus] = useState("connecting");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [topic, setTopic] = useState("");
  const [resolvedId, setResolvedId] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, string>>({});
  const [rebuttals, setRebuttals] = useState<Record<string, string>>({});
  const [verdict, setVerdict] = useState("");
  const [biasScores, setBiasScores] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStatus("connecting");
    setTopic("");
    setResolvedId(null);
    setArgs({});
    setRebuttals({});
    setVerdict("");
    setBiasScores({});
    setError(null);

    const stream = connectDebateStream(
      debateId,
      (event: DebateStreamEvent) => {
        if (event.error) {
          setError(event.message ?? "Debate not found.");
          return;
        }
        if (event.status) setStatus(event.status);
        if (event.debate_id) setResolvedId(event.debate_id);
        if (event.topic) setTopic(event.topic);
        if (event.data) setArgs((prev) => ({ ...prev, ...event.data }));
        if (event.rebuttals) setRebuttals((prev) => ({ ...prev, ...event.rebuttals }));
        if (event.verdict) setVerdict(event.verdict);
        if (event.bias_scores && Object.keys(event.bias_scores).length > 0) {
          setBiasScores(event.bias_scores);
        }
      },
      setConnection
    );
    return () => stream.close();
  }, [debateId]);

  if (error) {
    return (
      <div role="alert" className="py-12 text-center">
        <p className="font-serif text-xl text-ink">{error}</p>
        <p className="mt-2 font-sans text-sm text-muted">
          Today&rsquo;s debate may not have been generated yet. Check the archive for earlier ones.
        </p>
      </div>
    );
  }

  const dotStates: Record<string, AgentDotState> = Object.fromEntries(
    PERSONAS.map((persona) => [
      persona,
      status === "done" ? "done" : args[persona] ? "active" : "waiting",
    ])
  );
  const debateDate = resolvedId?.split(":")[0];

  return (
    <div>
      {topic && (
        <div className="fade-in pb-6">
          {debateDate && (
            <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Debate of {debateDate}</p>
          )}
          <h2 className="mt-2 font-serif text-2xl font-semibold leading-snug text-ink">{topic}</h2>
        </div>
      )}
      <AgentStatusDots states={dotStates} />
      <p
        role="status"
        aria-live="polite"
        className="mt-4 font-sans text-xs uppercase tracking-[0.04em] text-muted"
      >
        {statusMessage(connection, status)}
      </p>
      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
        {PERSONAS.map((persona) => (
          <AgentCard key={persona} persona={persona} argument={args[persona]} rebuttal={rebuttals[persona]} />
        ))}
      </div>
      <VerdictPanel verdict={verdict} biasScores={biasScores} />
      {status === "done" && <OpinionBox debateId={resolvedId ?? debateId} />}
    </div>
  );
}
