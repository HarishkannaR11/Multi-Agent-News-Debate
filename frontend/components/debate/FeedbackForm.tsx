// Runs in the browser: the rating buttons and the submit are interactive.
"use client";

import { useState } from "react";
import { ApiError, sendFeedback } from "@/lib/api";

// A 1 to 5 scale as a radio group.
function Scale({ name, legend, value, onChange }: { name: string; legend: string; value: number; onChange: (n: number) => void }) {
  return (
    <fieldset>
      <legend className="font-sans text-sm font-medium text-ink">{legend}</legend>
      <div className="mt-1.5 flex gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <label
            key={n}
            className={`flex h-10 w-10 cursor-pointer items-center justify-center rounded border font-mono text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus ${
              value === n ? "border-ink bg-ink text-paper" : "border-edge bg-surface text-ink hover:bg-paper"
            }`}
          >
            <input type="radio" name={name} value={n} checked={value === n} onChange={() => onChange(n)} className="sr-only" />
            {n}
          </label>
        ))}
      </div>
      <p className="mt-1 font-sans text-xs text-muted">1 = poor, 5 = excellent</p>
    </fieldset>
  );
}

// Asks how clear and how useful the debate was.
export function FeedbackForm({ debateId }: { debateId: string }) {
  const [clarity, setClarity] = useState(0);
  const [usefulness, setUsefulness] = useState(0);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (state !== "idle") return;
    if (!clarity || !usefulness) {
      setError("Rate both questions from 1 to 5.");
      return;
    }
    setState("sending");
    setError(null);
    try {
      await sendFeedback(debateId, clarity, usefulness, comment.trim());
      setState("sent");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send your feedback. Try again.");
      setState("idle");
    }
  }

  return (
    <section id="feedback" aria-labelledby="feedback-title" className="border-t border-line pt-8">
      <h2 id="feedback-title" className="font-serif text-2xl font-semibold text-ink">
        Was this useful?
      </h2>
      {state === "sent" ? (
        <p role="status" className="mt-3 font-sans text-base text-ok">
          Thank you. Your feedback was saved.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4" noValidate>
          <div className="flex flex-wrap gap-8">
            <Scale name="clarity" legend="How clear was it?" value={clarity} onChange={setClarity} />
            <Scale name="usefulness" legend="How useful was it?" value={usefulness} onChange={setUsefulness} />
          </div>
          <div>
            <label htmlFor="feedback-comment" className="font-sans text-sm font-medium text-ink">
              Anything to add? <span className="font-normal text-muted">(optional)</span>
            </label>
            <textarea
              id="feedback-comment"
              value={comment}
              maxLength={500}
              onChange={(event) => setComment(event.target.value)}
              className="mt-1.5 min-h-[72px] w-full max-w-reading rounded border border-edge bg-surface p-3 font-sans text-base text-ink"
            />
          </div>
          {error && (
            <p role="alert" className="font-sans text-sm text-agents-left">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={state === "sending"}
            className="rounded bg-ink px-4 py-2 font-sans text-sm font-medium text-paper hover:opacity-90 disabled:opacity-60"
          >
            {state === "sending" ? "Sending…" : "Send feedback"}
          </button>
        </form>
      )}
    </section>
  );
}
