// Marks this file as a client component: it uses state and a WebSocket, which only work in the browser.
"use client";

// React tools: useState keeps values that re-draw the screen when changed; useEffect runs code after rendering.
import { useEffect, useState } from "react";
// The WebSocket helper and the types for its messages and connection states.
import { connectDebateStream, type ConnectionState, type DebateStreamEvent } from "@/lib/api";
// The card that shows one analyst's argument and rebuttal.
import { AgentCard } from "./AgentCard";
// The row of progress dots, and the type of one dot's state.
import { AgentStatusDots, type AgentDotState } from "./AgentStatusDots";
// The box where the reader types their own opinion.
import { OpinionBox } from "./OpinionBox";
// The panel with the moderator's verdict and the bias chart.
import { VerdictPanel } from "./VerdictPanel";

// The five analysts, in the order their cards are shown.
const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"];

// Chooses the one-line status text shown above the cards.
function statusMessage(connection: ConnectionState, status: string): string {
  // Connection problems take priority over the debate stage.
  if (connection === "failed") return "Connection lost. Refresh the page to try again.";
  if (connection === "reconnecting") return "Connection lost. Reconnecting...";
  // Otherwise describe the stage of the debate.
  if (status === "fetching") return "Loading the debate...";
  if (status === "debating") return "Opening arguments";
  if (status === "rebuttal") return "Rebuttals";
  if (status === "done") return "Debate complete.";
  // Nothing has arrived yet.
  return "Connecting...";
}

// The main debate view: connects to the server, receives the debate in stages and shows it.
export function DebateStream({ debateId }: { debateId: string }) {
  // The debate stage: "connecting", "debating", "rebuttal" or "done".
  const [status, setStatus] = useState("connecting");
  // The WebSocket connection state, used for the status message.
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  // The debate topic (empty until it arrives).
  const [topic, setTopic] = useState("");
  // The real debate id as the server resolved it (e.g. "latest" becomes "2026-10-01:some-topic").
  const [resolvedId, setResolvedId] = useState<string | null>(null);
  // Opening arguments, keyed by analyst.
  const [args, setArgs] = useState<Record<string, string>>({});
  // Rebuttals, keyed by analyst.
  const [rebuttals, setRebuttals] = useState<Record<string, string>>({});
  // The moderator's verdict.
  const [verdict, setVerdict] = useState("");
  // Bias scores, keyed by analyst.
  const [biasScores, setBiasScores] = useState<Record<string, number>>({});
  // An error message to show instead of the debate (null = no error).
  const [error, setError] = useState<string | null>(null);

  // Runs after the first render, and again whenever debateId changes.
  useEffect(() => {
    // Clear everything from any previous debate before starting.
    setStatus("connecting");
    setTopic("");
    setResolvedId(null);
    setArgs({});
    setRebuttals({});
    setVerdict("");
    setBiasScores({});
    setError(null);

    // Open the WebSocket and handle each message the server sends.
    const stream = connectDebateStream(
      debateId,
      (event: DebateStreamEvent) => {
        // The server reported a problem (e.g. no such debate): show it and stop processing this message.
        if (event.error) {
          setError(event.message ?? "Debate not found.");
          return;
        }
        // Copy each piece of the message into state, but only the pieces that are present.
        if (event.status) setStatus(event.status);
        if (event.debate_id) setResolvedId(event.debate_id);
        if (event.topic) setTopic(event.topic);
        // Merge new arguments into the existing ones (the spread "..." copies the old values first).
        if (event.data) setArgs((prev) => ({ ...prev, ...event.data }));
        if (event.rebuttals) setRebuttals((prev) => ({ ...prev, ...event.rebuttals }));
        if (event.verdict) setVerdict(event.verdict);
        // Ignore empty bias-score objects so earlier messages do not wipe the chart.
        if (event.bias_scores && Object.keys(event.bias_scores).length > 0) {
          setBiasScores(event.bias_scores);
        }
      },
      // Whenever the connection state changes, store it.
      setConnection
    );
    // Cleanup: when the component goes away (or debateId changes), close the connection.
    return () => stream.close();
  }, [debateId]);

  // If an error is set, show only the error message and nothing else.
  if (error) {
    return (
      // role="alert" makes screen readers announce it immediately.
      <div role="alert" className="py-12 text-center">
        <p className="font-serif text-xl text-ink">{error}</p>
        <p className="mt-2 font-sans text-sm text-muted">
          Today&rsquo;s debate may not have been generated yet. Check the archive for earlier ones.
        </p>
      </div>
    );
  }

  // Work out each analyst's dot: everyone is "done" at the end; before that, "active" once their argument arrived, else "waiting".
  const dotStates: Record<string, AgentDotState> = Object.fromEntries(
    PERSONAS.map((persona) => [
      persona,
      status === "done" ? "done" : args[persona] ? "active" : "waiting",
    ])
  );
  // The date is the part of the id before the ":" (undefined until the id is known).
  const debateDate = resolvedId?.split(":")[0];

  return (
    <div>
      {/* Show the topic block only once the topic has arrived. */}
      {topic && (
        // "fade-in" is a small animation from globals.css.
        <div className="fade-in pb-6">
          {/* The date label, if known. */}
          {debateDate && (
            <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Debate of {debateDate}</p>
          )}
          <h2 className="mt-2 font-serif text-2xl font-semibold leading-snug text-ink">{topic}</h2>
        </div>
      )}
      {/* The row of five progress dots. */}
      <AgentStatusDots states={dotStates} />
      {/* The live status line; aria-live="polite" makes screen readers announce changes politely. */}
      <p
        role="status"
        aria-live="polite"
        className="mt-4 font-sans text-xs uppercase tracking-[0.04em] text-muted"
      >
        {statusMessage(connection, status)}
      </p>
      {/* The analyst cards: one column on phones, two columns from the "md" breakpoint up. */}
      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* One card per analyst, given that analyst's argument and rebuttal (undefined until they arrive). */}
        {PERSONAS.map((persona) => (
          <AgentCard key={persona} persona={persona} argument={args[persona]} rebuttal={rebuttals[persona]} />
        ))}
      </div>
      {/* The verdict and bias chart (they show placeholders until the data arrives). */}
      <VerdictPanel verdict={verdict} biasScores={biasScores} />
      {/* Once the debate is complete, let the reader add their own opinion. */}
      {status === "done" && <OpinionBox debateId={resolvedId ?? debateId} />}
    </div>
  );
}
