// Display names for each analyst, keyed by persona id.
const PERSONA_LABELS: Record<string, string> = {
  left: "Left Analyst",
  right: "Right Analyst",
  economist: "Economist",
  geopolitical: "Geopolitical Analyst",
  devil: "Devil's Advocate",
};

// Bar colour class per analyst.
const PERSONA_BAR: Record<string, string> = {
  left: "bg-agents-left",
  right: "bg-agents-right",
  economist: "bg-agents-econ",
  geopolitical: "bg-agents-geo",
  devil: "bg-agents-devil",
};

// A horizontal bar chart of each analyst's bias score (0 to 1 shown as 0 to 100).
export function BiasChart({ biasScores }: { biasScores: Record<string, number> }) {
  // Turn { left: 0.7, ... } into a list of [name, score] pairs we can loop over.
  const entries = Object.entries(biasScores);

  // No scores yet (the debate has not finished): show a hint instead of an empty chart.
  if (entries.length === 0) {
    return <p className="font-sans text-sm text-muted">Bias scores will appear once the debate finishes.</p>;
  }

  return (
    // A vertical stack of bars with a small gap between them.
    <div className="flex flex-col gap-3">
      {/* One row per analyst. */}
      {entries.map(([persona, score]) => (
        <div key={persona} className="flex items-center gap-4">
          {/* Left column: the analyst's name (fixed width so the bars line up). */}
          <p className="w-40 shrink-0 font-sans text-xs uppercase tracking-[0.04em] text-warm">
            {PERSONA_LABELS[persona] ?? persona}
          </p>
          {/* Middle column: takes the remaining width and holds the bar. */}
          <div className="flex-1">
            {/* The bar: its width is the score as a percentage; unknown analysts get a neutral colour. */}
            <div
              className={`h-[6px] opacity-60 ${PERSONA_BAR[persona] ?? "bg-ink"}`}
              style={{ width: `${Math.round(score * 100)}%` }}
            />
          </div>
          {/* Right column: the score as a whole number out of 100. */}
          <p className="w-10 shrink-0 text-right font-mono text-xs text-ink">{Math.round(score * 100)}</p>
        </div>
      ))}
    </div>
  );
}
