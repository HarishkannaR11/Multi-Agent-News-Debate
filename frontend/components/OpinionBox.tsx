// Marks this file as a client component: it uses state, effects, localStorage and click handlers.
"use client";

// React tools: useState keeps values that re-draw the screen; useEffect runs code after rendering.
import { useEffect, useState } from "react";
// API helpers and constants: the error class, the character limit, the two request functions and a reply type.
import { ApiError, MAX_OPINION_CHARS, fetchOpinions, submitOpinion, type OpinionResponse } from "@/lib/api";
// Gets this browser's anonymous id.
import { getAnonymousUserId } from "@/lib/user";
// Displays the AI's reply to one opinion.
import { OpinionResponseView } from "./OpinionResponse";

// The box where a reader writes an opinion, submits it and sees the AI's replies.
export function OpinionBox({ debateId }: { debateId: string }) {
  // This browser's anonymous id (null until it is read after the page loads).
  const [userId, setUserId] = useState<string | null>(null);
  // The text currently typed in the box.
  const [opinion, setOpinion] = useState("");
  // The conversation so far: the user's opinions with the AI replies, oldest first.
  const [thread, setThread] = useState<OpinionResponse[]>([]);
  // True while a submission is waiting for the server.
  const [loading, setLoading] = useState(false);
  // An error message to display (null = none).
  const [error, setError] = useState<string | null>(null);

  // localStorage only exists in the browser, so resolve the id after mount.
  // Runs once after the first render and stores the id.
  useEffect(() => setUserId(getAnonymousUserId()), []);

  // Earlier takes on this debate. Best effort: the box works without them.
  // Runs when the debate or user id changes.
  useEffect(() => {
    // Wait until the user id is known.
    if (userId === null) return;
    // Becomes true if this effect is cleaned up before the request finishes.
    let cancelled = false;
    // Ask the server for this user's earlier opinions on this debate.
    fetchOpinions(debateId, userId)
      .then((history) => {
        // Only use the result if we are still on the same debate/user.
        if (!cancelled) setThread(history);
      })
      // If loading fails, ignore it quietly (the box still works).
      .catch(() => {});
    // Cleanup: mark this request as outdated.
    return () => {
      cancelled = true;
    };
  }, [debateId, userId]);

  // The Submit button works only when not busy, the id is known and the text is not blank.
  const canSubmit = !loading && userId !== null && opinion.trim().length > 0;

  // Sends the opinion to the server and adds the reply to the conversation.
  async function handleSubmit() {
    // Do nothing if submitting is not allowed right now (the extra userId check also satisfies TypeScript).
    if (!canSubmit || userId === null) return;
    // Show the "Thinking..." state and clear any old error.
    setLoading(true);
    setError(null);
    try {
      // Send the trimmed text and wait for the AI's reply.
      const entry = await submitOpinion(debateId, userId, opinion.trim());
      // Add the reply to the end of the conversation.
      setThread((prev) => [...prev, entry]);
      // Clear the text box.
      setOpinion("");
    } catch (err) {
      // Show the server's message if it is one of ours; otherwise a generic message.
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      // Whether it worked or not, stop showing "Thinking...".
      setLoading(false);
    }
  }

  return (
    // The section is labelled by the heading with id "your-take" (for screen readers).
    <section className="pb-16 pt-8" aria-labelledby="your-take">
      <h2 id="your-take" className="font-sans text-xs uppercase tracking-[0.04em] text-warm">
        Your take
      </h2>
      {/* The text area: limited to MAX_OPINION_CHARS characters and controlled by the "opinion" state. */}
      <textarea
        aria-label="Your opinion on this debate"
        className="mt-4 min-h-[80px] w-full rounded border border-line bg-surface p-4 font-sans text-base text-ink outline-none focus:border-ink"
        placeholder="What's your take on this?"
        maxLength={MAX_OPINION_CHARS}
        value={opinion}
        // Keep the state in sync with what the user types.
        onChange={(event) => setOpinion(event.target.value)}
        // Ctrl+Enter (or Cmd+Enter on Mac) submits.
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) handleSubmit();
        }}
      />
      {/* Row under the text area: a character counter on the left, the Submit button on the right. */}
      <div className="mt-3 flex items-center justify-between">
        <p className="font-mono text-xs text-muted">
          {opinion.length}/{MAX_OPINION_CHARS}
        </p>
        {/* Disabled when submitting is not allowed; shows "Thinking..." while waiting. */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="font-sans text-sm font-medium text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          {loading ? "Thinking..." : "Submit"}
        </button>
      </div>
      {/* Show the error message, if there is one. */}
      {error && (
        <p role="alert" className="mt-3 font-sans text-sm text-agents-left">
          {error}
        </p>
      )}
      {/* Show the conversation only if it has entries. */}
      {thread.length > 0 && (
        <ol aria-label="Your conversation" className="mt-8 flex flex-col gap-10">
          {/* Newest first: copy the list, reverse the copy (reverse changes the list it is called on), then loop. */}
          {[...thread].reverse().map((entry) => (
            // The timestamp is unique per reply, so it serves as the list key.
            <li key={entry.timestamp}>
              {/* What the user wrote. */}
              <p className="border-l-2 border-ink pl-4 font-sans text-sm italic text-warm">
                You: {entry.user_opinion}
              </p>
              {/* The AI's reply to it. */}
              <OpinionResponseView response={entry} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
