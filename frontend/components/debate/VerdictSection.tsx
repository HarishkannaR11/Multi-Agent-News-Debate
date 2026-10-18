// Runs in the browser: the retry button and the reference jump buttons are interactive.
"use client";

import type { Debate } from "@/lib/api";
import { PERSONA_LABELS, splitReferences, type PerspectiveView, type Verdict } from "@/lib/debate";
import { BiasChart } from "../BiasChart";

const SUFFICIENCY: Record<Verdict["evidence_sufficiency"], { label: string; style: string }> = {
  sufficient: { label: "Evidence: sufficient", style: "border-ok text-ok" },
  limited: { label: "Evidence: limited", style: "border-warn text-warn" },
  insufficient: { label: "Evidence: insufficient", style: "border-agents-left text-agents-left" },
};

// A titled paragraph or list of the verdict.
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

// The moderator's verdict. Shows the structured version for debates started from a question, the older plain text otherwise,
// and an honest message while it is being written or when it failed.
export function VerdictSection({
  debate,
  views,
  structured,
  generating,
  retrying,
  onRetry,
  onJumpToClaim,
  validRefs,
}: {
  debate: Debate;
  views: PerspectiveView[];
  structured: boolean;
  generating: boolean;
  retrying: boolean;
  onRetry: () => void;
  onJumpToClaim: (claimId: string) => void;
  validRefs: Set<string>;
}) {
  const data = debate.verdict_data as Partial<Verdict> | undefined;
  const hasStructured = Boolean(data && data.summary);
  const completed = views.filter((v) => v.state === "completed").length;

  let body: React.ReactNode;
  if (hasStructured && data) {
    const verdict = data as Verdict;
    const sufficiency = SUFFICIENCY[verdict.evidence_sufficiency] ?? SUFFICIENCY.limited;
    // Turns [left-2] in the text into a button that jumps to that claim; unknown ids stay plain text.
    const withRefs = (text: string) =>
      splitReferences(text, validRefs).map((part, i) =>
        part.type === "text" ? (
          <span key={i}>{part.text}</span>
        ) : (
          <button
            key={i}
            type="button"
            onClick={() => onJumpToClaim(part.id)}
            className="mx-0.5 rounded-sm border border-edge px-1 font-mono text-[11px] text-ink hover:bg-surface"
          >
            {part.id}
          </button>
        )
      );
    body = (
      <div className="space-y-6">
        <p className="font-serif text-2xl italic leading-[1.5] text-ink">{verdict.summary}</p>
        <div className="flex flex-wrap items-center gap-3 font-sans text-sm text-warm">
          <span className={`rounded-sm border px-2 py-0.5 font-medium ${sufficiency.style}`}>{sufficiency.label}</span>
          <span>
            Based on {verdict.based_on.perspectives} of {verdict.based_on.of} perspectives and {verdict.based_on.sources} related article
            {verdict.based_on.sources === 1 ? "" : "s"}.
          </span>
        </div>
        {debate.status === "partial" && (
          <p role="note" className="rounded border border-warn p-3 font-sans text-sm text-warn">
            Only {completed} of {views.length} perspectives were available, so this verdict is incomplete.
          </p>
        )}
        <Part title="Conclusion">
          <p className="font-sans text-base leading-relaxed text-ink">{withRefs(verdict.conclusion)}</p>
        </Part>
        {verdict.strongest_arguments.length > 0 && (
          <Part title="Strongest argument from each side">
            <ul className="space-y-2 font-sans text-base leading-relaxed text-warm">
              {verdict.strongest_arguments.map((a) => (
                <li key={a.perspective}>
                  <strong className="text-ink">{PERSONA_LABELS[a.perspective] ?? a.perspective}:</strong> {withRefs(a.argument)}
                </li>
              ))}
            </ul>
          </Part>
        )}
        <Part title="What the evidence supports">
          <p className="font-sans text-base leading-relaxed text-ink">{withRefs(verdict.evidence_supports)}</p>
        </Part>
        <Part title="Strongest counterargument">
          <p className="font-sans text-base leading-relaxed text-ink">{withRefs(verdict.strongest_counterargument)}</p>
        </Part>
        <Part title="Conflicting or insufficient evidence">
          <p className="font-sans text-base leading-relaxed text-ink">{withRefs(verdict.conflicting_or_insufficient_evidence)}</p>
        </Part>
        {verdict.criteria.length > 0 && (
          <Part title="Criteria used">
            <dl className="space-y-2 font-sans text-base leading-relaxed">
              {verdict.criteria.map((c) => (
                <div key={c.name}>
                  <dt className="font-medium text-ink">{c.name}</dt>
                  <dd className="text-warm">{c.assessment}</dd>
                </div>
              ))}
            </dl>
          </Part>
        )}
        <Part title="Reasoning">
          <p className="font-sans text-base leading-relaxed text-ink">{withRefs(verdict.reasoning)}</p>
        </Part>
        {verdict.unresolved_questions.length > 0 && (
          <Part title="Unresolved questions">
            <List items={verdict.unresolved_questions} />
          </Part>
        )}
        {verdict.could_change_conclusion.length > 0 && (
          <Part title="What could change this conclusion">
            <List items={verdict.could_change_conclusion} />
          </Part>
        )}
        {verdict.limitations.length > 0 && (
          <Part title="Limitations">
            <List items={verdict.limitations} />
          </Part>
        )}
      </div>
    );
  } else if (debate.verdict && !structured) {
    // An older, automatically generated debate: plain text and the bias chart it always had.
    body = (
      <div className="space-y-8">
        <p className="font-serif text-xl italic leading-[1.6] text-ink">{debate.verdict}</p>
        <div>
          <h3 className="font-sans text-xs font-semibold uppercase tracking-[0.06em] text-muted">Bias scores</h3>
          <div className="mt-4">
            <BiasChart biasScores={debate.bias_scores ?? {}} />
          </div>
        </div>
      </div>
    );
  } else if (generating) {
    body = (
      <div role="status" className="space-y-3">
        <p className="font-sans text-base text-warm">The moderator writes the verdict once the perspectives are in.</p>
        <div className="skeleton h-4 w-3/4 rounded bg-line" />
        <div className="skeleton h-4 w-full rounded bg-line" />
      </div>
    );
  } else if (completed < 3) {
    body = (
      <p className="font-sans text-base text-warm">
        No verdict was written: it needs at least three completed perspectives and this debate has {completed}. Retry the failed analysts above.
      </p>
    );
  } else {
    body = (
      <div role="alert" className="rounded border border-warn p-4 font-sans text-sm">
        <p className="font-medium text-warn">The verdict could not be generated.</p>
        {debate.verdict_error && <p className="mt-1 text-warm">{String(debate.verdict_error)}</p>}
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="mt-3 rounded border border-warn px-3 py-1.5 font-medium text-warn hover:bg-surface disabled:opacity-60"
        >
          {retrying ? "Retrying…" : "Retry verdict"}
        </button>
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
