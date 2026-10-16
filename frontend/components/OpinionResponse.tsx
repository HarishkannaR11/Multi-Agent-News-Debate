// Import only the type (no runtime code) describing the backend's opinion reply.
import type { OpinionResponse } from "@/lib/api";

// Text colour class for each reply mode, so the label's colour hints at the AI's stance.
const MODE_COLOR: Record<string, string> = {
  AGREE: "text-agents-geo",
  CHALLENGE: "text-agents-left",
  EXPAND: "text-agents-econ",
};

// Shows the AI's reply to one user opinion: a mode label, the reply, and a follow-up question.
export function OpinionResponseView({ response }: { response: OpinionResponse }) {
  return (
    // "fade-in" is a small animation defined in globals.css.
    <div className="fade-in mt-8">
      {/* The mode label such as [CHALLENGE], coloured by mode (plain ink colour if unknown). */}
      <p className={`font-sans text-xs uppercase tracking-[0.04em] ${MODE_COLOR[response.mode] ?? "text-ink"}`}>
        [{response.mode}]
      </p>
      {/* The reply itself, with a dashed line down its left side. */}
      <div className="mt-2 border-l border-dashed border-muted pl-4">
        <p className="font-sans text-base leading-[1.75] text-ink">{response.agent_response}</p>
      </div>
      {/* The follow-up question is shown only if the AI produced one. */}
      {response.followup && (
        <p className="mt-4 font-serif text-base italic text-warm">{response.followup}</p>
      )}
    </div>
  );
}
