import { safeHttpUrl } from "@/lib/debate";
import { latestOf, signedPct, type SeriesInfo } from "@/lib/markets";
import { Sparkline } from "./Sparkline";

const STATUS_STYLE: Record<SeriesInfo["status"], string> = {
  ok: "border-ok text-ok",
  stale: "border-warn text-warn",
  missing: "border-agents-left text-agents-left",
};

// Where each number came from, and whether it was available. A missing series is shown as missing, never filled in.
export function SeriesTable({ series }: { series: Record<string, SeriesInfo> }) {
  const rows = Object.entries(series);
  return (
    <section id="series" aria-labelledby="series-title" className="border-t border-line pt-8">
      <h2 id="series-title" className="font-serif text-2xl font-semibold text-ink">
        Markets and sources
      </h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse font-sans text-sm">
          <caption className="sr-only">Each series: latest value, day change, trend, data status and source</caption>
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-[0.04em] text-muted">
              <th scope="col" className="py-2 pr-3">Series</th>
              <th scope="col" className="py-2 pr-3 text-right">Latest</th>
              <th scope="col" className="py-2 pr-3 text-right">Day</th>
              <th scope="col" className="py-2 pr-3">Trend</th>
              <th scope="col" className="py-2 pr-3">Data</th>
              <th scope="col" className="py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([id, info]) => {
              const latest = latestOf(info);
              const href = safeHttpUrl(info.source_url);
              const isFlow = id === "FII_NET";
              return (
                <tr key={id} className="border-b border-line align-middle">
                  <th scope="row" className="py-3 pr-3 text-left font-medium text-ink">
                    {info.label}
                    <span className="block text-xs font-normal text-muted">{info.unit}</span>
                  </th>
                  <td className="py-3 pr-3 text-right font-mono text-ink">
                    {latest ? latest.value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—"}
                    {latest && <span className="block text-xs text-muted">{latest.date}</span>}
                  </td>
                  <td className="py-3 pr-3 text-right font-mono text-ink">{isFlow ? "—" : signedPct(latest?.changePct)}</td>
                  <td className="py-3 pr-3">
                    <Sparkline points={info.points} />
                  </td>
                  <td className="py-3 pr-3">
                    <span className={`rounded-sm border px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLE[info.status]}`}>
                      {info.status === "ok" ? "Available" : info.status === "stale" ? "Stale" : "Missing"}
                    </span>
                    {info.detail && <span className="mt-1 block text-xs text-muted">{info.detail}</span>}
                  </td>
                  <td className="py-3 text-warm">
                    {info.source ? (
                      href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
                          {info.source}
                          <span className="sr-only"> (opens in a new tab)</span>
                        </a>
                      ) : (
                        info.source
                      )
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
