// Runs in the browser: the "cited by" links switch to the analyst's tab before jumping.
"use client";

import { claimsCiting, formatDay, PERSONA_SHORT, safeHttpUrl, type ClaimRef, type Source } from "@/lib/debate";

// The related articles found for the question, each with who cited it. Never invented; not fact-checked evidence.
export function SourcesSection({
  sources,
  index,
  searched,
  onJumpToClaim,
}: {
  sources: Source[];
  index: Map<string, ClaimRef>;
  // Whether a lookup was attempted for this debate (so "none found" can be told apart from "not looked for").
  searched: boolean;
  onJumpToClaim: (claimId: string) => void;
}) {
  return (
    <section id="sources" aria-labelledby="sources-title" className="border-t border-line pt-8">
      <h2 id="sources-title" className="font-serif text-2xl font-semibold text-ink">
        Sources <span className="font-sans text-base font-normal text-muted">({sources.length})</span>
      </h2>
      {sources.length === 0 ? (
        <p className="mt-3 max-w-reading font-sans text-base leading-relaxed text-warm">
          {searched
            ? "No related news articles were found, so no claim in this debate has a source. The perspectives rest on the analysts' general knowledge, which is not checked."
            : "No sources were retrieved for this debate. Its claims are not backed by cited material."}
        </p>
      ) : (
        <>
          <p className="mt-2 max-w-reading font-sans text-sm text-muted">
            Related news coverage found for the question. It is context, not verified evidence: an analyst citing an article does not make a claim true.
          </p>
          <ol className="mt-4 space-y-4">
            {sources.map((source) => {
              const href = safeHttpUrl(source.url);
              const citing = claimsCiting(source.id, index);
              return (
                <li key={source.id} id={`source-${source.id}`} className="rounded border border-line bg-surface p-4">
                  <p className="font-sans text-base font-medium leading-snug text-ink">
                    <span className="mr-2 font-mono text-xs text-muted">{source.id}</span>
                    {href ? (
                      <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
                        {source.title}
                        <span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    ) : (
                      source.title
                    )}
                  </p>
                  <p className="mt-1 font-sans text-sm text-muted">
                    {source.publisher}
                    {source.published_at ? ` · ${formatDay(source.published_at)}` : " · date not given"}
                  </p>
                  {source.excerpt && <p className="mt-2 font-sans text-sm leading-relaxed text-warm">&ldquo;{source.excerpt}&rdquo;</p>}
                  <p className="mt-2 font-sans text-sm text-warm">
                    {citing.length === 0 ? (
                      "Not cited by any claim."
                    ) : (
                      <>
                        Cited by:{" "}
                        {citing.map(({ claim, persona }) => (
                          <button
                            key={claim.id}
                            type="button"
                            onClick={() => onJumpToClaim(claim.id)}
                            className="mr-2 rounded-sm border border-edge px-1.5 py-0.5 font-mono text-[11px] text-ink hover:bg-paper"
                            aria-label={`Claim ${claim.id} by ${PERSONA_SHORT[persona]}`}
                          >
                            {claim.id}
                          </button>
                        ))}
                      </>
                    )}
                  </p>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </section>
  );
}
