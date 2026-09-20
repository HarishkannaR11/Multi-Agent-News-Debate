import type { OpinionResponse } from "@/lib/api";

const MODE_COLOR: Record<string, string> = {
  AGREE: "text-agents-geo",
  CHALLENGE: "text-agents-left",
  EXPAND: "text-agents-econ",
};

export function OpinionResponseView({ response }: { response: OpinionResponse }) {
  return (
    <div className="fade-in mt-8">
      <p className={`font-sans text-xs uppercase tracking-[0.04em] ${MODE_COLOR[response.mode] ?? "text-ink"}`}>
        [{response.mode}]
      </p>
      <div className="mt-2 border-l border-dashed border-muted pl-4">
        <p className="font-sans text-base leading-[1.75] text-ink">{response.agent_response}</p>
      </div>
      {response.followup && (
        <p className="mt-4 font-serif text-base italic text-warm">{response.followup}</p>
      )}
    </div>
  );
}
