import Link from "next/link";

export function Header({ date, topicCount }: { date?: string; topicCount?: number }) {
  return (
    <header className="border-b-2 border-ink pb-6 pt-8">
      <div className="flex items-baseline justify-between">
        <h1 className="font-serif text-[48px] font-bold leading-none tracking-[-0.02em] text-ink">
          <Link href="/">The Debate</Link>
        </h1>
        {date && <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">{date}</p>}
      </div>
      <div className="mt-2 flex items-baseline justify-between">
        <p className="font-sans text-xs uppercase tracking-[0.04em] text-warm">
          Five perspectives. One verdict.
        </p>
        <nav aria-label="Primary" className="flex gap-6 font-sans text-xs uppercase tracking-[0.04em] text-muted">
          {topicCount !== undefined && (
            <span>
              {topicCount} {topicCount === 1 ? "topic" : "topics"}
            </span>
          )}
          <Link href="/" className="hover:text-ink hover:underline">
            Latest
          </Link>
          <Link href="/archive" className="hover:text-ink hover:underline">
            Archive
          </Link>
        </nav>
      </div>
    </header>
  );
}
