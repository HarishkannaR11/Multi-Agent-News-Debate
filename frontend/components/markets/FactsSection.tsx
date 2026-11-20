import type { MarketFact } from "@/lib/markets";

// The numbered facts the analysts were given. Every claim below cites these by id, so each can be read in full here.
export function FactsSection({ facts, sha }: { facts: MarketFact[]; sha: string }) {
  return (
    <section id="facts" aria-labelledby="facts-title" className="border-t border-line pt-8">
      <h2 id="facts-title" className="font-serif text-2xl font-semibold text-ink">
        The data packet <span className="font-sans text-base font-normal text-muted">({facts.length} facts)</span>
      </h2>
      <p className="mt-2 max-w-reading font-sans text-sm text-muted">
        Computed by plain code from the series above, before any AI wrote a word. The analysts see only these facts and may quote only
        these figures. Fingerprint <span className="break-all font-mono text-xs">{sha.slice(0, 16)}…</span>: the same data always gives the
        same packet.
      </p>
      <ol className="mt-4 space-y-2">
        {facts.map((fact) => (
          <li key={fact.id} id={`fact-${fact.id}`} className="flex gap-3 rounded border border-line bg-surface p-3">
            <span className="shrink-0 font-mono text-xs font-medium text-muted">{fact.id}</span>
            <p className="font-sans text-base leading-relaxed text-ink">{fact.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
