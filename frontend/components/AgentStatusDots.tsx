// The three states one analyst's progress dot can be in.
export type AgentDotState = "waiting" | "active" | "done";

// The analysts, in display order ("as const" makes this a fixed, read-only list).
const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"] as const;

// Short names shown under each dot.
const PERSONA_LABELS: Record<string, string> = {
  left: "Left",
  right: "Right",
  economist: "Economist",
  geopolitical: "Geopolitical",
  devil: "Devil's Advocate",
};

// Words read aloud by screen readers for each state (the dots themselves are only visual).
const STATE_LABELS: Record<AgentDotState, string> = {
  waiting: "waiting",
  active: "writing",
  done: "done",
};

// Background colour class for the pulsing dot, one per analyst.
const PERSONA_DOT_BG: Record<string, string> = {
  left: "bg-agents-left",
  right: "bg-agents-right",
  economist: "bg-agents-econ",
  geopolitical: "bg-agents-geo",
  devil: "bg-agents-devil",
};

// Text colour class for the tick mark, one per analyst.
const PERSONA_DOT_TEXT: Record<string, string> = {
  left: "text-agents-left",
  right: "text-agents-right",
  economist: "text-agents-econ",
  geopolitical: "text-agents-geo",
  devil: "text-agents-devil",
};

// A row of five dots (one per analyst) showing who is waiting, writing or done.
export function AgentStatusDots({ states }: { states: Record<string, AgentDotState> }) {
  return (
    // A list with an accessible name; the dots are spread evenly across the row.
    <ul aria-label="Analyst progress" className="flex justify-around border-b border-line py-6">
      {/* Make one list item per analyst. */}
      {PERSONAS.map((persona) => {
        // This analyst's state; default to "waiting" if none was given.
        const state = states[persona] ?? "waiting";
        return (
          <li key={persona} className="flex flex-col items-center gap-2">
            {/* The visual indicator; hidden from screen readers because the label below says the same. */}
            <span aria-hidden="true">
              {/* done = coloured tick, active = pulsing coloured dot, waiting = empty outlined circle. */}
              {state === "done" ? (
                <span className={`text-sm ${PERSONA_DOT_TEXT[persona]}`}>&#10003;</span>
              ) : state === "active" ? (
                <span className={`dot-pulse block h-2 w-2 rounded-full ${PERSONA_DOT_BG[persona]}`} />
              ) : (
                <span className="block h-2 w-2 rounded-full border border-muted" />
              )}
            </span>
            <p className="font-sans text-[11px] uppercase tracking-[0.04em] text-muted">
              {/* The analyst's short name. */}
              {PERSONA_LABELS[persona]}
              {/* Text only screen readers hear, e.g. ": writing". */}
              <span className="sr-only">: {STATE_LABELS[state]}</span>
            </p>
          </li>
        );
      })}
    </ul>
  );
}
