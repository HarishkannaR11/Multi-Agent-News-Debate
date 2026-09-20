const PERSONA_LABELS: Record<string, string> = {
  left: "Left Analyst",
  right: "Right Analyst",
  economist: "Economist",
  geopolitical: "Geopolitical Analyst",
  devil: "Devil's Advocate",
};

const PERSONA_BAR: Record<string, string> = {
  left: "bg-agents-left",
  right: "bg-agents-right",
  economist: "bg-agents-econ",
  geopolitical: "bg-agents-geo",
  devil: "bg-agents-devil",
};

export function BiasChart({ biasScores }: { biasScores: Record<string, number> }) {
  const entries = Object.entries(biasScores);

  if (entries.length === 0) {
    return <p className="font-sans text-sm text-muted">Bias scores will appear once the debate finishes.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {entries.map(([persona, score]) => (
        <div key={persona} className="flex items-center gap-4">
          <p className="w-40 shrink-0 font-sans text-xs uppercase tracking-[0.04em] text-warm">
            {PERSONA_LABELS[persona] ?? persona}
          </p>
          <div className="flex-1">
            <div
              className={`h-[6px] opacity-60 ${PERSONA_BAR[persona] ?? "bg-ink"}`}
              style={{ width: `${Math.round(score * 100)}%` }}
            />
          </div>
          <p className="w-10 shrink-0 text-right font-mono text-xs text-ink">{Math.round(score * 100)}</p>
        </div>
      ))}
    </div>
  );
}
