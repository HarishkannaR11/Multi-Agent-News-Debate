// Display names for each analyst, keyed by the persona id the backend uses.
const PERSONA_LABELS: Record<string, string> = {
  left: "Left Analyst",
  right: "Right Analyst",
  economist: "Economist",
  geopolitical: "Geopolitical Analyst",
  devil: "Devil's Advocate",
};

// The Tailwind class that paints a coloured stripe on the card's left edge, one colour per analyst.
// (Full class names are written out so Tailwind can find them when it builds the CSS.)
const PERSONA_STRIPE: Record<string, string> = {
  left: "border-l-agents-left",
  right: "border-l-agents-right",
  economist: "border-l-agents-econ",
  geopolitical: "border-l-agents-geo",
  devil: "border-l-agents-devil",
};

// One card showing an analyst's opening argument and (once available) their rebuttal.
export function AgentCard({
  persona,
  argument,
  rebuttal,
  closing,
}: {
  // Which analyst this card is for, e.g. "left".
  persona: string;
  // Their opening argument (undefined until it has arrived).
  argument?: string;
  // Their rebuttal (undefined until it has arrived).
  rebuttal?: string;
  // Their closing statement from the optional second round (undefined when there was none).
  closing?: string;
}) {
  return (
    // The card box: a border, an 8px coloured left stripe for this analyst, and the surface background.
    <div className={`border border-line border-l-[8px] bg-surface ${PERSONA_STRIPE[persona] ?? ""}`}>
      {/* Card header: the analyst's name under a thin line. */}
      <div className="border-b border-line px-6 py-4">
        <h3 className="font-sans text-xs uppercase tracking-[0.1em] text-warm">
          {/* Show the friendly name, or the raw id if we have no label for it. */}
          {PERSONA_LABELS[persona] ?? persona}
        </h3>
      </div>
      {/* Card body: the argument text and optional rebuttal. */}
      <div className="px-6 py-4">
        <p className="font-sans text-base leading-[1.75] text-ink">
          {/* Show the argument, or a placeholder until it arrives. */}
          {argument ?? "Waiting for opening argument..."}
        </p>
        {/* Only render the rebuttal block if a rebuttal exists. */}
        {rebuttal && (
          <div className="mt-4 border-l border-dashed border-muted pl-6">
            {/* A small "Rebuttal" label, then the rebuttal text. */}
            <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Rebuttal</p>
            <p className="mt-1 font-sans text-base leading-[1.75] text-ink">{rebuttal}</p>
          </div>
        )}
        {/* Only render the closing statement if the moderator asked for a second round. */}
        {closing && (
          <div className="mt-4 border-l border-dashed border-muted pl-6">
            {/* A small "Closing statement" label, then the text. */}
            <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Closing statement</p>
            <p className="mt-1 font-sans text-base leading-[1.75] text-ink">{closing}</p>
          </div>
        )}
      </div>
    </div>
  );
}
