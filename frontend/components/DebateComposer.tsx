// Runs in the browser: it holds the typed text, handles keys and navigates after submitting.
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError, createDebate, fetchOptions, type DebateOptions } from "@/lib/api";
import { checkQuestion, newRequestId } from "@/lib/debate";
import { addId } from "@/lib/storage";

// Example questions. Clicking one only fills the box; the visitor still presses "Start debate".
const EXAMPLES = [
  "Should AI-generated code require mandatory human review?",
  "Is remote work more productive than working from an office?",
  "Should governments regulate advanced AI systems?",
  "Is cryptocurrency a reliable long-term investment?",
  "Should universities allow AI tools during examinations?",
];

// Used until the server's real limits arrive (or if they cannot be loaded).
const FALLBACK: DebateOptions = { enabled: true, min_chars: 10, max_chars: 500, categories: [], per_hour: 3, sources_available: true };
const DRAFT_KEY = "counterpoint_draft";

// The form that starts a debate from the visitor's own question.
export function DebateComposer() {
  const router = useRouter();
  const [options, setOptions] = useState<DebateOptions>(FALLBACK);
  const [question, setQuestion] = useState("");
  const [category, setCategory] = useState("");
  const [useSources, setUseSources] = useState(true);
  // Show validation messages only after the visitor has tried to submit or left the box (not while they type).
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  // One id per question: pressing Start twice, or retrying after a network error, returns the same debate.
  const request = useRef({ id: newRequestId(), question: "" });

  // Load the limits and categories; restore a draft the visitor typed before a refresh.
  useEffect(() => {
    fetchOptions().then(setOptions).catch(() => undefined);
    try {
      const draft = window.sessionStorage.getItem(DRAFT_KEY);
      if (draft) setQuestion(draft);
    } catch {
      // storage blocked: no draft
    }
  }, []);

  const check = checkQuestion(question, options.min_chars, options.max_chars);
  const length = question.split(/\s+/).filter(Boolean).join(" ").length;
  const over = length > options.max_chars;
  const message = !check.ok && (touched || over) ? check.message : null;

  function change(value: string) {
    setQuestion(value);
    setError(null);
    try {
      window.sessionStorage.setItem(DRAFT_KEY, value);
    } catch {
      // ignore
    }
  }

  async function submit() {
    // Ignore a second press while the first is being processed.
    if (submitting) return;
    setTouched(true);
    const result = checkQuestion(question, options.min_chars, options.max_chars);
    if (!result.ok) {
      textarea.current?.focus();
      return;
    }
    // A changed question is a new request; the same question keeps its id so a retry is safe.
    if (request.current.question !== result.value) request.current = { id: newRequestId(), question: result.value };
    setSubmitting(true);
    setError(null);
    try {
      const created = await createDebate({
        question: result.value,
        category: category || undefined,
        use_sources: useSources && options.sources_available,
        client_request_id: request.current.id,
      });
      addId("mine", created.id);
      try {
        window.sessionStorage.removeItem(DRAFT_KEY);
      } catch {
        // ignore
      }
      setDone(true);
      router.push(`/debate/${encodeURIComponent(created.id)}`);
    } catch (err) {
      // The question stays in the box so nothing is lost.
      setSubmitting(false);
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    }
  }

  const disabled = submitting || !options.enabled;
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      className="space-y-5"
    >
      <div>
        <label htmlFor="question" className="block font-serif text-2xl font-semibold text-ink">
          What would you like to debate?
        </label>
        <p id="question-hint" className="mt-1 font-sans text-sm text-warm">
          Ask a question or state a topic in your own words. Press Enter to start, Shift+Enter for a new line.
        </p>
        <textarea
          id="question"
          ref={textarea}
          value={question}
          rows={4}
          placeholder="What would you like to debate?"
          aria-describedby={`question-hint question-count${message ? " question-error" : ""}`}
          aria-invalid={message ? true : undefined}
          onChange={(event) => change(event.target.value)}
          onBlur={() => question && setTouched(true)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter makes a new line. Ignore Enter while an input method (IME) is composing text.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void submit();
            }
          }}
          disabled={!options.enabled}
          className="mt-3 w-full resize-y rounded border border-edge bg-surface p-4 font-serif text-lg leading-snug text-ink placeholder:text-muted disabled:opacity-60"
        />
        <div className="mt-1 flex items-start justify-between gap-4">
          <p id="question-error" role="alert" className="min-h-[1.25rem] font-sans text-sm text-warn">
            {message}
          </p>
          <p id="question-count" className={`shrink-0 font-mono text-xs ${over ? "text-warn" : "text-muted"}`}>
            {length}/{options.max_chars}
          </p>
        </div>
      </div>

      <div>
        <p className="font-sans text-xs uppercase tracking-[0.06em] text-muted">Try an example (fills the box, does not start)</p>
        <ul className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                onClick={() => {
                  change(example);
                  textarea.current?.focus();
                }}
                className="rounded border border-edge px-3 py-1.5 text-left font-sans text-sm text-ink hover:bg-surface"
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {options.categories.length > 0 && (
        <div>
          <label htmlFor="category" className="block font-sans text-sm font-medium text-ink">
            Topic category <span className="font-normal text-muted">(optional)</span>
          </label>
          <select
            id="category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="mt-1 w-full rounded border border-edge bg-surface p-2.5 font-sans text-sm text-ink sm:w-72"
          >
            <option value="">No category</option>
            {options.categories.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Collapsed by default: the settings most visitors never need. */}
      <details className="rounded border border-line bg-surface p-4">
        <summary className="cursor-pointer font-sans text-sm font-medium text-ink">Advanced settings</summary>
        <div className="mt-3 space-y-2">
          <label className="flex items-start gap-3 font-sans text-sm text-ink">
            <input
              type="checkbox"
              checked={useSources && options.sources_available}
              disabled={!options.sources_available}
              onChange={(event) => setUseSources(event.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <span>
              Look for related news coverage to use as sources
              <span className="block text-muted">
                {options.sources_available
                  ? "Real articles are shown as context. They are not fact-checked evidence."
                  : "Not available: this server has no news API key, so debates run without sources."}
              </span>
            </span>
          </label>
          <p className="font-sans text-sm text-muted">
            You can start {options.per_hour} debates per hour. Debates you start are unlisted: only people with the link can open them.
          </p>
        </div>
      </details>

      {!options.enabled && (
        <p role="alert" className="rounded border border-warn p-3 font-sans text-sm text-warn">
          Starting new debates is switched off on this server right now.
        </p>
      )}
      {error && (
        <div role="alert" className="rounded border border-warn p-3 font-sans text-sm text-warn">
          {error}
          <span className="mt-1 block text-warm">Your question is still in the box. Press Start debate to try again.</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={disabled}
          className="rounded bg-ink px-6 py-3 font-sans text-base font-medium text-paper hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Starting…" : "Start debate"}
        </button>
        <p role="status" aria-live="polite" className="font-sans text-sm text-warm">
          {done ? "Debate started. Opening it…" : submitting ? "Sending your question…" : ""}
        </p>
      </div>
    </form>
  );
}
