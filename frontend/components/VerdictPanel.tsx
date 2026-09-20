import { BiasChart } from "./BiasChart";

export function VerdictPanel({
  verdict,
  biasScores,
}: {
  verdict: string;
  biasScores: Record<string, number>;
}) {
  return (
    <section className="border-t-2 border-ink pb-10 pt-8">
      <h2 className="font-sans text-xs uppercase tracking-[0.04em] text-warm">Moderator&rsquo;s verdict</h2>
      <p className="mt-4 font-serif text-xl italic leading-[1.6] text-ink">
        {verdict || "The moderator's verdict will appear once the debate concludes."}
      </p>
      <div className="mt-10">
        <h3 className="font-sans text-xs uppercase tracking-[0.04em] text-warm">Bias scores</h3>
        <div className="mt-4">
          <BiasChart biasScores={biasScores} />
        </div>
      </div>
    </section>
  );
}
