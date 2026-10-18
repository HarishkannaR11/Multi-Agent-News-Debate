import type { Metadata } from "next";
import { DebateComposer } from "@/components/DebateComposer";
import { Header } from "@/components/Header";

export const metadata: Metadata = { title: "Start a debate · The Debate" };

// The page for starting a debate from your own question (address "/new").
export default function NewDebatePage() {
  return (
    <>
      <Header current="new" />
      <main className="mx-auto max-w-reading pb-20 pt-10">
        <h1 className="font-sans text-xs uppercase tracking-[0.08em] text-muted">New debate</h1>
        <div className="mt-4">
          <DebateComposer />
        </div>
        {/* What will happen, and what the result is not. Plain statements, no promises about timing. */}
        <section aria-labelledby="how" className="mt-14 border-t border-line pt-8">
          <h2 id="how" className="font-serif text-xl font-semibold text-ink">
            How it works
          </h2>
          <ol className="mt-4 list-decimal space-y-3 pl-5 font-sans text-base leading-relaxed text-warm">
            <li>Five AI analysts (left, right, economist, geopolitical and a devil&rsquo;s advocate) each write a structured perspective on your exact question.</li>
            <li>The app can look up related news articles; analysts may cite only those real articles.</li>
            <li>A moderator maps where the perspectives agree and conflict, then writes a short verdict that says how strong the evidence is.</li>
          </ol>
          <p className="mt-4 rounded border border-line bg-surface p-4 font-sans text-sm leading-relaxed text-warm">
            Everything is written by AI. Claims are labelled <strong className="text-ink">unverified</strong> unless they are opinions or assumptions: nothing is
            fact-checked, and related articles are context, not proof.
          </p>
        </section>
      </main>
    </>
  );
}
