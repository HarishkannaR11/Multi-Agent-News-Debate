// Runs in the browser: items expand and collapse, and links open them.
"use client";

import { MAP_GROUPS, PERSONA_LABELS, type ClaimRef, type Disagreements, type MapItem, type Source } from "@/lib/debate";
import { ClaimBadge } from "./ClaimBadge";
import { SourceChips } from "./SourceChips";

// Opens a disagreement item and scrolls to it (used by links in the claim lists).
export function revealDisagreement(id: string): void {
  const element = document.getElementById(`d-${id}`);
  if (element instanceof HTMLDetailsElement) element.open = true;
}

// One item. With claims it expands to show them; without claims (open questions) it is a plain line.
function Item({ item, index, sources }: { item: MapItem; index: Map<string, ClaimRef>; sources: Source[] }) {
  const refs = item.claim_ids.map((id) => index.get(id)).filter((ref): ref is ClaimRef => Boolean(ref));
  if (refs.length === 0) {
    return (
      <li id={`d-${item.id}`} className="rounded border border-line bg-surface p-3 font-sans text-base leading-relaxed text-ink">
        {item.summary}
      </li>
    );
  }
  return (
    <li>
      <details id={`d-${item.id}`} className="rounded border border-line bg-surface">
        <summary className="cursor-pointer p-3 font-sans text-base leading-relaxed text-ink">
          <span className="mr-2 font-mono text-[11px] text-muted">{item.id}</span>
          {item.summary}
          <span className="ml-2 font-sans text-sm text-muted">
            ({refs.length} claims from {new Set(refs.map((r) => r.persona)).size} analysts)
          </span>
        </summary>
        <ul className="space-y-3 border-t border-line p-3">
          {refs.map(({ claim, persona }) => (
            <li key={claim.id} className="font-sans text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="text-ink">{PERSONA_LABELS[persona]}</strong>
                <ClaimBadge claim={claim} />
                <SourceChips ids={claim.source_ids} sources={sources} />
              </div>
              <p className="mt-1 text-base leading-relaxed text-warm">{claim.text}</p>
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

// Where the five perspectives agree and disagree, built only from the claims above (by claim id).
export function DisagreementMap({
  disagreements,
  index,
  sources,
  enough,
  generating,
  onRetry,
}: {
  disagreements: Disagreements | undefined;
  index: Map<string, ClaimRef>;
  sources: Source[];
  enough: boolean;
  generating: boolean;
  onRetry: () => void;
}) {
  let body: React.ReactNode;
  if (!enough) {
    body = <p className="font-sans text-base text-warm">The map needs at least three completed perspectives.</p>;
  } else if (disagreements?.error) {
    body = (
      <div role="alert" className="rounded border border-warn p-3 font-sans text-sm text-warn">
        The disagreement map could not be generated ({disagreements.error})
        <button type="button" onClick={onRetry} className="ml-3 rounded border border-warn px-2 py-1 underline">
          Retry
        </button>
      </div>
    );
  } else if (!disagreements || Object.keys(disagreements).length === 0) {
    body = (
      <p className="font-sans text-base text-warm">
        {generating ? "The moderator builds the map once the perspectives are in." : "No disagreement map is available for this debate."}
      </p>
    );
  } else {
    body = (
      <>
        {disagreements.central_question && (
          <p className="font-serif text-xl italic leading-snug text-ink">
            <span className="mr-2 font-sans text-xs not-italic uppercase tracking-[0.06em] text-muted">Central question</span>
            {disagreements.central_question}
          </p>
        )}
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {MAP_GROUPS.map(({ key, title, hint }) => {
            const items = disagreements[key] ?? [];
            return (
              <section key={key} aria-labelledby={`map-${key}`}>
                <h3 id={`map-${key}`} className="font-sans text-sm font-semibold text-ink">
                  {title} <span className="font-normal text-muted">({items.length})</span>
                </h3>
                <p className="font-sans text-sm text-muted">{hint}</p>
                {items.length === 0 ? (
                  <p className="mt-2 font-sans text-sm text-muted">None identified.</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {items.map((item) => (
                      <Item key={item.id} item={item} index={index} sources={sources} />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
        <p className="mt-6 font-sans text-sm text-muted">
          AI-assisted grouping: every item points at specific claims above, and an agreement or conflict must involve at least two analysts.
          Similar wording alone is not treated as agreement. Check the cited claims.
        </p>
      </>
    );
  }
  return (
    <section id="disagreements" aria-labelledby="disagreements-title" className="border-t border-line pt-8">
      <h2 id="disagreements-title" className="font-serif text-2xl font-semibold text-ink">
        Where they agree and disagree
      </h2>
      <div className="mt-4">{body}</div>
    </section>
  );
}
