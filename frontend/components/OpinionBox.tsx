"use client";

import { useState } from "react";
import { submitOpinion, type OpinionResponse } from "@/lib/api";
import { OpinionResponseView } from "./OpinionResponse";

export function OpinionBox({ debateId, userId }: { debateId: string; userId: string }) {
  const [opinion, setOpinion] = useState("");
  const [response, setResponse] = useState<OpinionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!opinion.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await submitOpinion(debateId, userId, opinion);
      setResponse(result);
    } catch {
      setError("Could not reach the debate agents. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="pb-16 pt-8">
      <h2 className="font-sans text-xs uppercase tracking-[0.04em] text-warm">Your take</h2>
      <textarea
        className="mt-4 min-h-[80px] w-full rounded border border-line bg-surface p-4 font-sans text-base text-ink outline-none focus:border-ink"
        placeholder="What's your take on this?"
        value={opinion}
        onChange={(event) => setOpinion(event.target.value)}
      />
      <div className="mt-3 flex justify-end">
        <button
          onClick={handleSubmit}
          disabled={loading || !opinion.trim()}
          className="font-sans text-sm font-medium text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          {loading ? "Thinking..." : "Submit"}
        </button>
      </div>
      {error && <p className="mt-3 font-sans text-sm text-agents-left">{error}</p>}
      {response && <OpinionResponseView response={response} />}
    </section>
  );
}
