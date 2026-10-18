// Runs in the browser: the retry button is interactive.
"use client";

import type { Debate } from "@/lib/api";
import { PERSONA_SHORT, stageLabel, type PerspectiveView } from "@/lib/debate";

const CHIP: Record<string, string> = {
  completed: "✓ done",
  generating: "… writing",
  pending: "○ waiting",
  failed: "! failed",
};

// Shows what the server is doing while a debate is generated, and what failed afterwards.
// It reports real states only (stage, which analysts are done); there is no percentage because the server cannot know one.
export function GenerationStatus({
  debate,
  views,
  failedCount,
  retrying,
  onRetryAll,
  pollError,
}: {
  debate: Debate;
  views: PerspectiveView[];
  failedCount: number;
  retrying: boolean;
  onRetryAll: () => void;
  pollError: string | null;
}) {
  const generating = debate.status === "generating";
  if (!generating && failedCount === 0 && !pollError) return null;
  return (
    <section aria-label="Generation status" className="rounded border border-line bg-surface p-4">
      {generating && (
        <div role="status" aria-live="polite">
          <p className="font-sans text-base font-medium text-ink">{stageLabel(debate.stage)}</p>
          <p className="mt-1 font-sans text-sm text-muted">
            This page updates by itself. You can leave and come back later: the debate keeps generating and this address stays the same.
          </p>
        </div>
      )}
      {(generating || failedCount > 0) && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Progress per analyst">
          {views.map((v) => (
            <li key={v.persona} className="rounded-sm border border-edge px-2 py-1 font-sans text-xs text-warm">
              <span className="font-medium text-ink">{PERSONA_SHORT[v.persona]}</span> {CHIP[v.state]}
            </li>
          ))}
        </ul>
      )}
      {!generating && failedCount > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-3 font-sans text-sm text-warm">
          <span>
            {failedCount} of {views.length} perspectives did not finish, so the verdict is based on fewer voices.
          </span>
          <button
            type="button"
            disabled={retrying}
            onClick={onRetryAll}
            className="rounded border border-edge px-3 py-1.5 font-medium text-ink hover:bg-paper disabled:opacity-60"
          >
            {retrying ? "Retrying…" : `Retry ${failedCount === 1 ? "the failed perspective" : `all ${failedCount} failed`}`}
          </button>
        </div>
      )}
      {pollError && (
        <p role="alert" className="mt-3 font-sans text-sm text-warn">
          {pollError} We keep trying; what you see may be out of date.
        </p>
      )}
    </section>
  );
}
