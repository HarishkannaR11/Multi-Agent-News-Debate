// Runs in the browser: tabs, keyboard navigation and the compare view are interactive.
"use client";

import { useRef, useState } from "react";
import {
  PERSONA_LABELS,
  PERSONA_SHORT,
  PERSONAS,
  type Disagreements,
  type Persona,
  type PerspectiveState,
  type PerspectiveView,
  type Source,
} from "@/lib/debate";
import { ClaimLegend } from "./ClaimBadge";
import { ClaimList } from "./ClaimList";

// The accent colour of each analyst (a top border on the tab and a dot in the compare picker).
const ACCENT: Record<Persona, string> = {
  left: "border-agents-left",
  right: "border-agents-right",
  economist: "border-agents-econ",
  geopolitical: "border-agents-geo",
  devil: "border-agents-devil",
};

// A symbol plus words for each state, so the state is never shown by colour alone.
const STATE_TEXT: Record<PerspectiveState, { icon: string; text: string }> = {
  completed: { icon: "✓", text: "complete" },
  generating: { icon: "…", text: "writing" },
  pending: { icon: "○", text: "waiting" },
  failed: { icon: "!", text: "failed" },
};

// Placeholder shown while an analyst has not finished.
function Skeleton({ label }: { label: string }) {
  return (
    <div role="status" className="space-y-3" aria-live="polite">
      <p className="font-sans text-sm text-muted">{label}</p>
      <div className="skeleton h-4 w-3/4 rounded bg-line" />
      <div className="skeleton h-4 w-full rounded bg-line" />
      <div className="skeleton h-4 w-5/6 rounded bg-line" />
    </div>
  );
}

// A titled block of text inside a panel.
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">{title}</h4>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

// A plain list of short statements (assumptions, uncertainties).
function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="font-sans text-sm text-muted">{empty}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 font-sans text-base leading-relaxed text-warm">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

// Everything one analyst said. Shows the right thing for each state: finished, failed, in progress, or an older plain-text debate.
export function PerspectivePanel({
  view,
  sources,
  disagreements,
  retrying,
  onRetry,
}: {
  view: PerspectiveView;
  sources: Source[];
  disagreements: Disagreements | undefined;
  retrying: boolean;
  onRetry: (persona: Persona) => void;
}) {
  const label = PERSONA_LABELS[view.persona];
  if (view.state === "failed") {
    return (
      <div role="alert" className="rounded border border-warn p-4 font-sans text-sm">
        <p className="font-medium text-warn">{label} could not finish.</p>
        <p className="mt-1 text-warm">
          {view.error || "The perspective could not be generated."}
          {view.attempts > 0 ? ` (${view.attempts} attempt${view.attempts === 1 ? "" : "s"} made.)` : ""}
        </p>
        <p className="mt-1 text-warm">The other perspectives are unaffected. Nothing is shown here instead of a made-up answer.</p>
        {view.attempts > 0 && (
          <button
            type="button"
            disabled={retrying}
            onClick={() => onRetry(view.persona)}
            className="mt-3 rounded border border-warn px-3 py-1.5 font-medium text-warn hover:bg-surface disabled:opacity-60"
          >
            {retrying ? "Retrying…" : `Retry ${PERSONA_SHORT[view.persona]}`}
          </button>
        )}
      </div>
    );
  }
  if (view.state === "pending" || view.state === "generating") {
    return <Skeleton label={view.state === "generating" ? `${label} is writing…` : `${label} is waiting to start…`} />;
  }
  if (view.legacy) {
    const { argument, rebuttal, closing } = view.legacy;
    return (
      <div className="space-y-5">
        <Block title="Opening argument">
          <p className="font-sans text-base leading-relaxed text-ink">{argument}</p>
        </Block>
        {rebuttal && (
          <Block title="Rebuttal">
            <p className="font-sans text-base leading-relaxed text-ink">{rebuttal}</p>
          </Block>
        )}
        {closing && (
          <Block title="Closing statement">
            <p className="font-sans text-base leading-relaxed text-ink">{closing}</p>
          </Block>
        )}
        <p className="font-sans text-sm text-muted">
          This is an automatically generated daily debate. It is stored as plain text, so it has no separate claims, labels or sources.
        </p>
      </div>
    );
  }
  const content = view.content;
  if (!content) return <Skeleton label={`${label} has no content yet…`} />;
  return (
    <div className="space-y-6">
      <Block title="Position">
        <p className="font-serif text-xl leading-snug text-ink">{content.position_summary}</p>
      </Block>
      <Block title="Strongest argument">
        <p className="font-sans text-base leading-relaxed text-ink">{content.strongest_argument}</p>
      </Block>
      <Block title={`Claims (${content.claims.length})`}>
        <ClaimList claims={content.claims} sources={sources} disagreements={disagreements} />
      </Block>
      <Block title="Strongest counterargument to this position">
        <p className="font-sans text-base leading-relaxed text-ink">{content.counterargument}</p>
      </Block>
      <Block title="Assumptions">
        <Bullets items={content.assumptions} empty="No assumptions were stated." />
      </Block>
      <Block title="Uncertainties">
        <Bullets items={content.uncertainties} empty="No uncertainties were stated." />
      </Block>
    </div>
  );
}

// The five perspectives as tabs, with an optional side-by-side comparison on wide screens.
export function PerspectiveExplorer({
  views,
  selected,
  onSelect,
  sources,
  disagreements,
  retrying,
  onRetry,
}: {
  views: PerspectiveView[];
  selected: Persona;
  onSelect: (persona: Persona) => void;
  sources: Source[];
  disagreements: Disagreements | undefined;
  retrying: Set<string>;
  onRetry: (persona: Persona) => void;
}) {
  const [compare, setCompare] = useState<Persona | "">("");
  const tabRefs = useRef<Partial<Record<Persona, HTMLButtonElement | null>>>({});
  const byPersona = new Map(views.map((v) => [v.persona, v]));
  const current = byPersona.get(selected) ?? views[0];
  const other = compare && compare !== selected ? byPersona.get(compare) : undefined;

  // Arrow keys, Home and End move between tabs (the standard tab pattern); the tab is selected as it gets focus.
  function onKeyDown(event: React.KeyboardEvent, persona: Persona) {
    const at = PERSONAS.indexOf(persona);
    let next = -1;
    if (event.key === "ArrowRight") next = (at + 1) % PERSONAS.length;
    else if (event.key === "ArrowLeft") next = (at - 1 + PERSONAS.length) % PERSONAS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = PERSONAS.length - 1;
    if (next < 0) return;
    event.preventDefault();
    onSelect(PERSONAS[next]);
    tabRefs.current[PERSONAS[next]]?.focus();
  }

  return (
    <section id="perspectives" aria-labelledby="perspectives-title" className="border-t border-line pt-8">
      <h2 id="perspectives-title" className="font-serif text-2xl font-semibold text-ink">
        The five perspectives
      </h2>
      <div className="mt-4 space-y-3">
        <ClaimLegend />
        {/* Comparison is only offered where there is room for two columns. */}
        <div className="hidden items-center gap-2 font-sans text-sm text-warm md:flex">
          <label htmlFor="compare-with" className="font-medium text-ink">
            Compare with
          </label>
          <select
            id="compare-with"
            value={compare}
            onChange={(event) => setCompare(event.target.value as Persona | "")}
            className="rounded border border-edge bg-surface px-2 py-1.5 text-ink"
          >
            <option value="">No comparison</option>
            {PERSONAS.filter((p) => p !== selected).map((p) => (
              <option key={p} value={p}>
                {PERSONA_LABELS[p]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div role="tablist" aria-label="Perspectives" className="relative mt-5 flex gap-1 overflow-x-auto border-b border-line">
        {views.map((view) => {
          const active = view.persona === selected;
          const state = STATE_TEXT[view.state];
          return (
            <button
              key={view.persona}
              ref={(node) => {
                tabRefs.current[view.persona] = node;
              }}
              type="button"
              role="tab"
              id={`tab-${view.persona}`}
              aria-selected={active}
              aria-controls={`panel-${view.persona}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onSelect(view.persona)}
              onKeyDown={(event) => onKeyDown(event, view.persona)}
              className={`-mb-px shrink-0 whitespace-nowrap border-t-[3px] px-3 py-2.5 font-sans text-sm ${
                active ? `${ACCENT[view.persona]} border-x border-x-line bg-surface font-semibold text-ink` : "border-transparent text-warm hover:text-ink"
              }`}
            >
              <span aria-hidden="true" className="mr-1.5 font-mono text-xs">
                {state.icon}
              </span>
              {PERSONA_SHORT[view.persona]}
              <span className="sr-only"> ({state.text})</span>
            </button>
          );
        })}
      </div>

      <div className={`mt-6 grid gap-8 ${other ? "md:grid-cols-2" : ""}`}>
        <div role="tabpanel" id={`panel-${selected}`} aria-labelledby={`tab-${selected}`} tabIndex={0} className="min-w-0">
          {other && <h3 className="mb-4 font-serif text-xl font-semibold text-ink">{PERSONA_LABELS[selected]}</h3>}
          <PerspectivePanel
            view={current}
            sources={sources}
            disagreements={disagreements}
            retrying={retrying.has(selected)}
            onRetry={onRetry}
          />
        </div>
        {other && (
          <div role="region" aria-label={`${PERSONA_LABELS[other.persona]} (comparison)`} className="hidden min-w-0 md:block">
            <h3 className="mb-4 font-serif text-xl font-semibold text-ink">{PERSONA_LABELS[other.persona]}</h3>
            <PerspectivePanel
              view={other}
              sources={sources}
              disagreements={disagreements}
              retrying={retrying.has(other.persona)}
              onRetry={onRetry}
            />
          </div>
        )}
      </div>
    </section>
  );
}
