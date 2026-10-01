"use client";

import { useEffect, useState } from "react";
import { ApiError, MAX_OPINION_CHARS, fetchOpinions, submitOpinion, type OpinionResponse } from "@/lib/api";
import { getAnonymousUserId } from "@/lib/user";
import { OpinionResponseView } from "./OpinionResponse";

export function OpinionBox({ debateId }: { debateId: string }) {
  const [userId, setUserId] = useState<string | null>(null);
  const [opinion, setOpinion] = useState("");
  const [thread, setThread] = useState<OpinionResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // localStorage only exists in the browser, so resolve the id after mount.
  useEffect(() => setUserId(getAnonymousUserId()), []);

  // Earlier takes on this debate. Best effort: the box works without them.
  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;
    fetchOpinions(debateId, userId)
      .then((history) => {
        if (!cancelled) setThread(history);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [debateId, userId]);

  const canSubmit = !loading && userId !== null && opinion.trim().length > 0;

  async function handleSubmit() {
    if (!canSubmit || userId === null) return;
    setLoading(true);
    setError(null);
    try {
      const entry = await submitOpinion(debateId, userId, opinion.trim());
      setThread((prev) => [...prev, entry]);
      setOpinion("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="pb-16 pt-8" aria-labelledby="your-take">
      <h2 id="your-take" className="font-sans text-xs uppercase tracking-[0.04em] text-warm">
        Your take
      </h2>
      <textarea
        aria-label="Your opinion on this debate"
        className="mt-4 min-h-[80px] w-full rounded border border-line bg-surface p-4 font-sans text-base text-ink outline-none focus:border-ink"
        placeholder="What's your take on this?"
        maxLength={MAX_OPINION_CHARS}
        value={opinion}
        onChange={(event) => setOpinion(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) handleSubmit();
        }}
      />
      <div className="mt-3 flex items-center justify-between">
        <p className="font-mono text-xs text-muted">
          {opinion.length}/{MAX_OPINION_CHARS}
        </p>
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="font-sans text-sm font-medium text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          {loading ? "Thinking..." : "Submit"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 font-sans text-sm text-agents-left">
          {error}
        </p>
      )}
      {thread.length > 0 && (
        <ol aria-label="Your conversation" className="mt-8 flex flex-col gap-10">
          {[...thread].reverse().map((entry) => (
            <li key={entry.timestamp}>
              <p className="border-l-2 border-ink pl-4 font-sans text-sm italic text-warm">
                You: {entry.user_opinion}
              </p>
              <OpinionResponseView response={entry} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
