// Runs in the browser: tabs and the expandable audit trail.
"use client";

import { useRef } from "react";
import {
  attributionLabel,
  MARKET_ROLES,
  outcomeLabel,
  rejectedAttempts,
  ROLE_BLURBS,
  ROLE_LABELS,
  type AgentState,
  type MarketRole,
} from "@/lib/markets";

const STATE_TEXT: Record<AgentState["status"], { icon: string; text: string }> = {
  completed: { icon: "✓", text: "complete" },
  generating: { icon: "…", text: "writing" },
  pending: { icon: "○", text: "waiting" },
  failed: { icon: "!", text: "failed" },
};

// What the validator did with each attempt. This is the audit trail: a rejected answer is sent back with these reasons.
function AuditTrail({ audit }: { audit: AgentState["audit"] }) {
  if (audit.length === 0) return null;
  const failed = rejectedAttempts(audit);
  return (
    <details className="rounded border border-line bg-surface p-3 font-sans text-sm text-warm">
      <summary className="cursor-pointer font-medium text-ink">
        Validator audit: {audit.length} attempt{audit.length === 1 ? "" : "s"}
        {failed > 0 ? `, ${failed} not accepted` : ", accepted first time"}
      </summary>
      <ol className="mt-3 space-y-3">
        {audit.map((entry) => (
          <li key={entry.attempt}>
            <p className="font-medium text-ink">
              Attempt {entry.attempt}: {outcomeLabel(entry.outcome)}
            </p>
            {entry.rejections.length > 0 && (
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {entry.rejections.map((r, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs text-muted">{r.code}</span> {r.message}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-muted">A rejected answer goes back to the analyst with these reasons, up to a fixed number of attempts.</p>
    </details>
  );
}

function Panel({ role, state }: { role: MarketRole; state: AgentState }) {
  if (state.status === "failed") {
    return (
      <div className="space-y-4">
        <div role="alert" className="rounded border border-warn p-4 font-sans text-sm">
          <p className="font-medium text-warn">{ROLE_LABELS[role]} could not produce an answer that passed validation.</p>
          <p className="mt-1 text-warm">{state.error}</p>
          <p className="mt-1 text-warm">Nothing is shown instead of an unchecked answer. The verdict uses only validated analysts.</p>
        </div>
        <AuditTrail audit={state.audit} />
      </div>
    );
  }
  if (state.status !== "completed" || !state.content) {
    return (
      <div role="status" className="space-y-3">
        <p className="font-sans text-sm text-muted">{state.status === "generating" ? `${ROLE_LABELS[role]} is writing…` : "Waiting to start…"}</p>
        <div className="skeleton h-4 w-3/4 rounded bg-line" />
        <div className="skeleton h-4 w-full rounded bg-line" />
      </div>
    );
  }
  const content = state.content;
  return (
    <div className="space-y-6">
      <div>
        <h4 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">Position</h4>
        <p className="mt-1.5 font-serif text-xl leading-snug text-ink">{content.stance}</p>
        <p className="mt-2 font-sans text-base leading-relaxed text-warm">{content.thesis}</p>
      </div>
      {content.attribution && (
        <div className="rounded border border-line bg-surface p-3 font-sans text-base">
          <p className="text-ink">
            <span className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">Attribution </span>
            <strong>{attributionLabel(content.attribution)}</strong>
          </p>
          <p className="mt-1 text-warm">{content.attribution_reasoning}</p>
        </div>
      )}
      <div>
        <h4 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">Claims ({content.claims.length})</h4>
        <ol className="mt-2 space-y-3">
          {content.claims.map((claim) => (
            <li key={claim.id} id={`claim-${claim.id}`} className="rounded border border-line bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-sm border border-edge px-1.5 py-0.5 font-sans text-[11px] font-medium uppercase tracking-[0.04em] text-warm">
                  {claim.kind}
                </span>
                <span className="font-mono text-[11px] text-muted">{claim.id}</span>
                <span className="font-sans text-xs text-muted">cites</span>
                {claim.fact_ids.map((id) => (
                  <a key={id} href={`#fact-${id}`} className="rounded-sm border border-edge px-1.5 py-0.5 font-mono text-[11px] text-ink hover:bg-paper">
                    {id}
                    <span className="sr-only"> (jump to the fact)</span>
                  </a>
                ))}
              </div>
              <p className="mt-2 font-sans text-base leading-relaxed text-ink">{claim.text}</p>
            </li>
          ))}
        </ol>
      </div>
      {content.caveats.length > 0 && (
        <div>
          <h4 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">What could make this wrong</h4>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 font-sans text-base leading-relaxed text-warm">
            {content.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <AuditTrail audit={state.audit} />
    </div>
  );
}

// The three analysts as tabs (the same pattern as the news debate: arrow keys, Home and End move between them).
export function AgentsSection({
  agents,
  selected,
  onSelect,
}: {
  agents: Record<MarketRole, AgentState>;
  selected: MarketRole;
  onSelect: (role: MarketRole) => void;
}) {
  const refs = useRef<Partial<Record<MarketRole, HTMLButtonElement | null>>>({});
  function onKeyDown(event: React.KeyboardEvent, role: MarketRole) {
    const at = MARKET_ROLES.indexOf(role);
    let next = -1;
    if (event.key === "ArrowRight") next = (at + 1) % MARKET_ROLES.length;
    else if (event.key === "ArrowLeft") next = (at - 1 + MARKET_ROLES.length) % MARKET_ROLES.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = MARKET_ROLES.length - 1;
    if (next < 0) return;
    event.preventDefault();
    onSelect(MARKET_ROLES[next]);
    refs.current[MARKET_ROLES[next]]?.focus();
  }
  return (
    <section id="analysts" aria-labelledby="analysts-title" className="border-t border-line pt-8">
      <h2 id="analysts-title" className="font-serif text-2xl font-semibold text-ink">
        The three analysts
      </h2>
      <p className="mt-2 max-w-reading font-sans text-sm text-muted">{ROLE_BLURBS[selected]}</p>
      <div role="tablist" aria-label="Analysts" className="relative mt-4 flex gap-1 overflow-x-auto border-b border-line">
        {MARKET_ROLES.map((role) => {
          const active = role === selected;
          const state = STATE_TEXT[agents[role].status];
          return (
            <button
              key={role}
              ref={(node) => {
                refs.current[role] = node;
              }}
              type="button"
              role="tab"
              id={`tab-${role}`}
              aria-selected={active}
              aria-controls={`panel-${role}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onSelect(role)}
              onKeyDown={(event) => onKeyDown(event, role)}
              className={`-mb-px shrink-0 whitespace-nowrap border-t-[3px] px-3 py-2.5 font-sans text-sm ${
                active ? "border-ink border-x border-x-line bg-surface font-semibold text-ink" : "border-transparent text-warm hover:text-ink"
              }`}
            >
              <span aria-hidden="true" className="mr-1.5 font-mono text-xs">
                {state.icon}
              </span>
              {ROLE_LABELS[role]}
              <span className="sr-only"> ({state.text})</span>
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`panel-${selected}`} aria-labelledby={`tab-${selected}`} tabIndex={0} className="mt-6 max-w-reading">
        <Panel role={selected} state={agents[selected]} />
      </div>
    </section>
  );
}
