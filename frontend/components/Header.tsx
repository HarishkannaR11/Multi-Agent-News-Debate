export function Header({ date, topicCount }: { date: string; topicCount: number }) {
  return (
    <header className="border-b-2 border-ink pb-6 pt-8">
      <div className="flex items-baseline justify-between">
        <h1 className="font-serif text-[48px] font-bold leading-none tracking-[-0.02em] text-ink">
          The Debate
        </h1>
        <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">{date}</p>
      </div>
      <div className="mt-2 flex items-baseline justify-between">
        <p className="font-sans text-xs uppercase tracking-[0.04em] text-warm">
          Five perspectives. One verdict.
        </p>
        <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">
          {topicCount} {topicCount === 1 ? "topic" : "topics"}
        </p>
      </div>
    </header>
  );
}
