import type { AuditEntry, MarketVerdict } from "@/lib/markets";

function Part({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5 font-sans text-base leading-relaxed text-warm">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

// The moderator's verdict, built only from validated claims, with its confidence decided by code (never by the model).
export function VerdictCard({
  verdict,
  error,
  generating,
  analysts,
}: {
  verdict: Partial<MarketVerdict>;
  error: string;
  generating: boolean;
  audit?: AuditEntry[];
  analysts: number;
}) {
  const ready = Boolean(verdict.summary);
  let body: React.ReactNode;
  if (ready) {
    const v = verdict as MarketVerdict;
    body = (
      <div className="space-y-6">
        <p className="font-serif text-2xl italic leading-[1.5] text-ink">{v.summary}</p>
        <p className="flex flex-wrap items-center gap-3 font-sans text-sm text-warm">
          <span className={`rounded-sm border px-2 py-0.5 font-medium ${v.confidence === "low" ? "border-warn text-warn" : "border-ok text-ok"}`}>
            Confidence: {v.confidence}
          </span>
          Based on {v.based_on.analysts} of {v.based_on.of} validated analysts and {v.based_on.facts} packet facts.
        </p>
        {v.based_on.analysts < v.based_on.of && (
          <p role="note" className="rounded border border-warn p-3 font-sans text-sm text-warn">
            Only {v.based_on.analysts} of {v.based_on.of} analysts passed validation, so this verdict is incomplete.
          </p>
        )}
        <Part title="Domestic or imported">
          <p className="font-sans text-base leading-relaxed text-ink">{v.attribution_view}</p>
        </Part>
        <Part title="Key drivers">
          <ul className="space-y-2 font-sans text-base leading-relaxed text-ink">
            {v.key_drivers.map((d) => (
              <li key={d.text}>
                {d.text}{" "}
                {d.fact_ids.map((id) => (
                  <a key={id} href={`#fact-${id}`} className="mr-1 rounded-sm border border-edge px-1 font-mono text-[11px] hover:bg-surface">
                    {id}
                  </a>
                ))}
              </li>
            ))}
          </ul>
        </Part>
        <Part title="Strongest bull point">
          <p className="font-sans text-base leading-relaxed text-ink">{v.bull_strongest}</p>
        </Part>
        <Part title="Strongest bear point">
          <p className="font-sans text-base leading-relaxed text-ink">{v.bear_strongest}</p>
        </Part>
        <Part title="Conclusion">
          <p className="font-sans text-base leading-relaxed text-ink">{v.conclusion}</p>
        </Part>
        {v.what_would_change.length > 0 && (
          <Part title="What would change this reading">
            <List items={v.what_would_change} />
          </Part>
        )}
        {v.data_gaps.length > 0 && (
          <Part title="Data gaps">
            <List items={v.data_gaps} />
          </Part>
        )}
        <Part title="Limitations">
          <List items={v.limitations} />
        </Part>
      </div>
    );
  } else if (generating) {
    body = (
      <div role="status" className="space-y-3">
        <p className="font-sans text-base text-warm">The moderator writes the verdict once the analysts are in.</p>
        <div className="skeleton h-4 w-3/4 rounded bg-line" />
      </div>
    );
  } else if (analysts < 2) {
    body = <p className="font-sans text-base text-warm">No verdict was written: it needs at least two validated analysts and this day has {analysts}.</p>;
  } else {
    body = (
      <div role="alert" className="rounded border border-warn p-4 font-sans text-sm">
        <p className="font-medium text-warn">The verdict could not be produced.</p>
        {error && <p className="mt-1 text-warm">{error}</p>}
      </div>
    );
  }
  return (
    <section id="verdict" aria-labelledby="verdict-title" className="border-t-2 border-ink pt-8">
      <h2 id="verdict-title" className="font-serif text-2xl font-semibold text-ink">
        Moderator&rsquo;s verdict
      </h2>
      <div className="mt-4 max-w-reading">{body}</div>
    </section>
  );
}
