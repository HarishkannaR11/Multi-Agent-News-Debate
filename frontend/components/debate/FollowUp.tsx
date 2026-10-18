// Runs in the browser: the question box, the suggestions and the conversation are interactive.
"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, askFollowup, type FollowupTurn } from "@/lib/api";
import { splitReferences } from "@/lib/debate";

const MAX_CHARS = 400;

// Questions that make sense for any debate. Choosing one only fills the box; nothing is sent until the visitor presses Ask.
const SUGGESTIONS = [
  "Where is the strongest disagreement, and why?",
  "Which claims have no source behind them?",
  "What would change the verdict?",
];

type Turn = FollowupTurn & { references?: string[]; failed?: boolean };

// A question box tied to this debate. Answers come from the debate's own claims, sources and verdict.
export function FollowUp({
  debateId,
  disabled,
  validRefs,
  onJumpToClaim,
}: {
  debateId: string;
  // True when there is nothing to ask about yet (the debate is still being generated).
  disabled: boolean;
  validRefs: Set<string>;
  onJumpToClaim: (claimId: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // A different debate means a different conversation.
  useEffect(() => {
    setTurns([]);
    setQuestion("");
    setError(null);
  }, [debateId]);

  async function send() {
    const text = question.split(/\s+/).filter(Boolean).join(" ");
    if (!text || loading || disabled) return;
    setLoading(true);
    setError(null);
    // The last six turns are the context; the server accepts no more.
    const history: FollowupTurn[] = turns.filter((t) => !t.failed).slice(-6).map(({ role, content }) => ({ role, content }));
    try {
      const reply = await askFollowup(debateId, text, history);
      setTurns((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: reply.answer, references: reply.references }]);
      setQuestion("");
    } catch (err) {
      // The question stays in the box so it can be sent again.
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  // Renders an answer, turning ids such as [left-2] into buttons and [S1] into links, but only ids that exist.
  function renderAnswer(text: string) {
    return splitReferences(text, validRefs).map((part, i) => {
      if (part.type === "text") return <span key={i}>{part.text}</span>;
      if (/^S\d+$/.test(part.id)) {
        return (
          <a key={i} href={`#source-${part.id}`} className="mx-0.5 rounded-sm border border-edge px-1 font-mono text-[11px] text-ink hover:bg-surface">
            {part.id}
          </a>
        );
      }
      return (
        <button
          key={i}
          type="button"
          onClick={() => onJumpToClaim(part.id)}
          className="mx-0.5 rounded-sm border border-edge px-1 font-mono text-[11px] text-ink hover:bg-surface"
        >
          {part.id}
        </button>
      );
    });
  }

  return (
    <section id="followup" aria-labelledby="followup-title" className="border-t border-line pt-8">
      <h2 id="followup-title" className="font-serif text-2xl font-semibold text-ink">
        Ask about this debate
      </h2>
      <p className="mt-2 max-w-reading font-sans text-sm text-muted">
        Answers use only this debate&rsquo;s claims, sources and verdict, and say so when the debate does not cover the question.
      </p>
      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Suggested questions">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled || loading}
            onClick={() => {
              setQuestion(s);
              inputRef.current?.focus();
            }}
            className="rounded border border-edge bg-surface px-3 py-1.5 text-left font-sans text-sm text-ink hover:bg-paper disabled:opacity-60"
          >
            {s}
          </button>
        ))}
      </div>
      <label htmlFor="followup-input" className="sr-only">
        Your question about this debate
      </label>
      <textarea
        id="followup-input"
        ref={inputRef}
        value={question}
        maxLength={MAX_CHARS}
        disabled={disabled}
        placeholder={disabled ? "Available once the perspectives are in." : "Ask a question about this debate…"}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends; Shift+Enter adds a line.
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
          }
        }}
        className="mt-4 min-h-[72px] w-full max-w-reading rounded border border-edge bg-surface p-3 font-sans text-base text-ink disabled:opacity-60"
      />
      <div className="mt-2 flex max-w-reading items-center justify-between">
        <p className="font-mono text-xs text-muted">
          {question.length}/{MAX_CHARS}
        </p>
        <button
          type="button"
          onClick={() => void send()}
          disabled={disabled || loading || !question.trim()}
          className="rounded bg-ink px-4 py-2 font-sans text-sm font-medium text-paper hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Thinking…" : "Ask"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 font-sans text-sm text-agents-left">
          {error}
        </p>
      )}
      {turns.length > 0 && (
        <ol aria-label="Follow-up conversation" className="mt-6 max-w-reading space-y-5" aria-live="polite">
          {turns.map((turn, i) => (
            <li key={i} className={turn.role === "user" ? "border-l-2 border-ink pl-4 font-sans text-sm italic text-warm" : "font-sans text-base leading-relaxed text-ink"}>
              {turn.role === "user" ? (
                <>
                  <span className="sr-only">You asked: </span>
                  {turn.content}
                </>
              ) : (
                <>
                  <span className="sr-only">Answer: </span>
                  {renderAnswer(turn.content)}
                </>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
