export type AgentDotState = "waiting" | "active" | "done";

const PERSONAS = ["left", "right", "economist", "geopolitical", "devil"] as const;

const PERSONA_LABELS: Record<string, string> = {
  left: "Left",
  right: "Right",
  economist: "Economist",
  geopolitical: "Geopolitical",
  devil: "Devil's Advocate",
};

const PERSONA_DOT_BG: Record<string, string> = {
  left: "bg-agents-left",
  right: "bg-agents-right",
  economist: "bg-agents-econ",
  geopolitical: "bg-agents-geo",
  devil: "bg-agents-devil",
};

const PERSONA_DOT_TEXT: Record<string, string> = {
  left: "text-agents-left",
  right: "text-agents-right",
  economist: "text-agents-econ",
  geopolitical: "text-agents-geo",
  devil: "text-agents-devil",
};

export function AgentStatusDots({ states }: { states: Record<string, AgentDotState> }) {
  return (
    <div className="flex justify-around border-b border-line py-6">
      {PERSONAS.map((persona) => {
        const state = states[persona] ?? "waiting";
        return (
          <div key={persona} className="flex flex-col items-center gap-2">
            {state === "done" ? (
              <span className={`text-sm ${PERSONA_DOT_TEXT[persona]}`}>&#10003;</span>
            ) : state === "active" ? (
              <span className={`dot-pulse h-2 w-2 rounded-full ${PERSONA_DOT_BG[persona]}`} />
            ) : (
              <span className="h-2 w-2 rounded-full border border-muted" />
            )}
            <p className="font-sans text-[11px] uppercase tracking-[0.04em] text-muted">
              {PERSONA_LABELS[persona]}
            </p>
          </div>
        );
      })}
    </div>
  );
}
