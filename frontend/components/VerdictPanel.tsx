// The bar chart component shown inside this panel.
import { BiasChart } from "./BiasChart";

// The section showing the moderator's verdict and the bias scores.
export function VerdictPanel({
  verdict,
  biasScores,
}: {
  // The moderator's summary (empty until the debate finishes).
  verdict: string;
  // Each analyst's bias score (empty until the debate finishes).
  biasScores: Record<string, number>;
}) {
  return (
    // A thick line on top separates the verdict from the analyst cards.
    <section className="border-t-2 border-ink pb-10 pt-8">
      {/* Section heading. */}
      <h2 className="font-sans text-xs uppercase tracking-[0.04em] text-warm">Moderator&rsquo;s verdict</h2>
      <p className="mt-4 font-serif text-xl italic leading-[1.6] text-ink">
        {/* The verdict, or a placeholder while it is still empty. */}
        {verdict || "The moderator's verdict will appear once the debate concludes."}
      </p>
      {/* The bias-score sub-section. */}
      <div className="mt-10">
        <h3 className="font-sans text-xs uppercase tracking-[0.04em] text-warm">Bias scores</h3>
        <div className="mt-4">
          {/* Draw the bars (or a hint if there are no scores yet). */}
          <BiasChart biasScores={biasScores} />
        </div>
      </div>
    </section>
  );
}
