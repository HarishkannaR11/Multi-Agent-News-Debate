// Runs in the browser: the "part of a disagreement" links open the matching item.
"use client";

import { itemsForClaim, PERSONA_LABELS, type Claim, type Disagreements, type Source, type Persona } from "@/lib/debate";
import { ClaimBadge } from "./ClaimBadge";
import { SourceChips } from "./SourceChips";
import { revealDisagreement } from "./DisagreementMap";

// The claims of one perspective: each with its label, its sources and links to the disagreements it is part of.
export function ClaimList({
  claims,
  sources,
  disagreements,
}: {
  claims: Claim[];
  sources: Source[];
  disagreements: Disagreements | undefined;
}) {
  if (claims.length === 0) return <p className="font-sans text-sm text-muted">This perspective listed no separate claims.</p>;
  return (
    <ol className="space-y-3">
      {claims.map((claim) => {
        const persona = claim.id.split("-")[0] as Persona;
        const links = itemsForClaim(claim.id, disagreements);
        return (
          <li key={claim.id} id={`claim-${claim.id}`} className="rounded border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <ClaimBadge claim={claim} />
              <span className="font-mono text-[11px] text-muted" aria-label={`Claim ${claim.id} by ${PERSONA_LABELS[persona] ?? persona}`}>
                {claim.id}
              </span>
              <SourceChips ids={claim.source_ids} sources={sources} />
            </div>
            <p className="mt-2 font-sans text-base leading-relaxed text-ink">{claim.text}</p>
            {links.length > 0 && (
              <p className="mt-2 font-sans text-sm text-warm">
                Appears in the disagreement map:{" "}
                {links.map(({ item }, index) => (
                  <span key={item.id}>
                    {index > 0 && ", "}
                    <a href={`#d-${item.id}`} onClick={() => revealDisagreement(item.id)} className="underline underline-offset-2">
                      {item.id}
                    </a>
                  </span>
                ))}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
