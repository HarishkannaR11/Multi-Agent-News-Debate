const PERSONA_LABELS: Record<string, string> = {
  left: "Left Analyst",
  right: "Right Analyst",
  economist: "Economist",
  geopolitical: "Geopolitical Analyst",
  devil: "Devil's Advocate",
};

const PERSONA_STRIPE: Record<string, string> = {
  left: "border-l-agents-left",
  right: "border-l-agents-right",
  economist: "border-l-agents-econ",
  geopolitical: "border-l-agents-geo",
  devil: "border-l-agents-devil",
};

export function AgentCard({
  persona,
  argument,
  rebuttal,
}: {
  persona: string;
  argument?: string;
  rebuttal?: string;
}) {
  return (
    <div className={`border border-line border-l-[8px] bg-surface ${PERSONA_STRIPE[persona] ?? ""}`}>
      <div className="border-b border-line px-6 py-4">
        <h3 className="font-sans text-xs uppercase tracking-[0.1em] text-warm">
          {PERSONA_LABELS[persona] ?? persona}
        </h3>
      </div>
      <div className="px-6 py-4">
        <p className="font-sans text-base leading-[1.75] text-ink">
          {argument ?? "Waiting for opening argument..."}
        </p>
        {rebuttal && (
          <div className="mt-4 border-l border-dashed border-muted pl-6">
            <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Rebuttal</p>
            <p className="mt-1 font-sans text-base leading-[1.75] text-ink">{rebuttal}</p>
          </div>
        )}
      </div>
    </div>
  );
}
