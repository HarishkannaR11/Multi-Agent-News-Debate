import { SERIES_LABELS } from "./labels";
import { attributionLabel, barPercent, regimeLabel, signedPct, signedPp, type Attribution, type Regime } from "@/lib/markets";

// One diverging bar: grows left for a fall and right for a rise, on a scale shared by every bar in the panel.
function Bar({ label, value, maxAbs, strong = false }: { label: string; value: number; maxAbs: number; strong?: boolean }) {
  const width = barPercent(value, maxAbs);
  const negative = value < 0;
  return (
    <div className="grid grid-cols-[9rem_1fr_5.5rem] items-center gap-3 font-sans text-sm">
      <span className={strong ? "font-medium text-ink" : "text-warm"}>{label}</span>
      <div className="relative h-4" aria-hidden="true">
        <div className="absolute inset-y-0 left-1/2 w-px bg-edge" />
        <div
          className={`absolute inset-y-0.5 ${negative ? "right-1/2 bg-agents-left" : "left-1/2 bg-agents-geo"}`}
          style={{ width: `${width / 2}%` }}
        />
      </div>
      <span className="text-right font-mono text-ink">{signedPp(value)}</span>
    </div>
  );
}

// Splits the index move into the part that lines up with imported factors and the part left over. The numbers come from
// a regression, so the panel says so and shows how weak the fit is.
export function AttributionPanel({ attribution, regime }: { attribution: Attribution; regime: Regime }) {
  const ok = attribution.status === "ok" && attribution.actual_pct !== undefined;
  const factors = attribution.factors ?? [];
  const maxAbs = ok
    ? Math.max(Math.abs(attribution.actual_pct ?? 0), Math.abs(attribution.explained_pct ?? 0), Math.abs(attribution.residual_pct ?? 0), ...factors.map((f) => Math.abs(f.contribution_pct)), 0.01)
    : 0;
  return (
    <section id="attribution" aria-labelledby="attribution-title" className="border-t border-line pt-8">
      <h2 id="attribution-title" className="font-serif text-2xl font-semibold text-ink">
        Domestic or imported?
      </h2>
      <p className="mt-2 flex flex-wrap items-center gap-2 font-sans text-sm text-warm">
        <span className="rounded-sm border border-edge px-2 py-0.5 font-medium text-ink">Regime: {regimeLabel(regime.label)}</span>
        {regime.risk_off_signals.length > 0 && <span>Risk-off signals: {regime.risk_off_signals.join(", ")}.</span>}
        {regime.risk_on_signals.length > 0 && <span>Risk-on signals: {regime.risk_on_signals.join(", ")}.</span>}
      </p>
      {!ok ? (
        <p className="mt-4 max-w-reading font-sans text-base text-warm">
          No attribution was computed: {attribution.reason ?? "there was not enough data"}.
        </p>
      ) : (
        <div className="mt-4 max-w-3xl space-y-3">
          <p className="font-sans text-base text-ink">
            Reading: <strong>{attributionLabel(attribution.label ?? "")}</strong>
            <span className="text-muted"> · confidence {attribution.confidence}</span>
          </p>
          <Bar label="Index move" value={attribution.actual_pct ?? 0} maxAbs={maxAbs} strong />
          <Bar label="Imported factors" value={attribution.explained_pct ?? 0} maxAbs={maxAbs} />
          <Bar label="Unexplained" value={attribution.residual_pct ?? 0} maxAbs={maxAbs} />
          <details className="rounded border border-line bg-surface p-3 font-sans text-sm text-warm">
            <summary className="cursor-pointer font-medium text-ink">Which factors, and how much to trust this</summary>
            <ul className="mt-3 space-y-1">
              {factors.map((f) => (
                <li key={f.series}>
                  {SERIES_LABELS[f.series] ?? f.series} ({f.lag === 0 ? "same day" : "previous US session"}, change{" "}
                  {f.series === "US10Y" ? `${f.today_change.toFixed(1)} bps` : signedPct(f.today_change)}): {signedPp(f.contribution_pct)}
                </li>
              ))}
            </ul>
            <p className="mt-3">
              {attribution.method} Fit: R² {attribution.r2?.toFixed(2)} on {attribution.n_obs} days. This is a statistical association, not
              proof of cause, and a low R² means imported factors explained little of the usual daily moves.
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
