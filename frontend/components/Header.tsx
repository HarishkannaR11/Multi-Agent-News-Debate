// Next.js's Link component: navigates between pages without a full page reload.
import Link from "next/link";

// The site header: title, tagline and navigation. Both props are optional.
export function Header({ date, topicCount }: { date?: string; topicCount?: number }) {
  return (
    // A thick line under the header separates it from the page.
    <header className="border-b-2 border-ink pb-6 pt-8">
      {/* Top row: the site title on the left, the date (if any) on the right. */}
      <div className="flex items-baseline justify-between">
        <h1 className="font-serif text-[48px] font-bold leading-none tracking-[-0.02em] text-ink">
          {/* Clicking the title goes to the home page. */}
          <Link href="/">The Debate</Link>
        </h1>
        {/* Only show the date if one was passed in. */}
        {date && <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">{date}</p>}
      </div>
      {/* Second row: the tagline on the left, the navigation links on the right. */}
      <div className="mt-2 flex items-baseline justify-between">
        <p className="font-sans text-xs uppercase tracking-[0.04em] text-warm">
          Five perspectives. One verdict.
        </p>
        {/* The main navigation (labelled "Primary" for screen readers). */}
        <nav aria-label="Primary" className="flex gap-6 font-sans text-xs uppercase tracking-[0.04em] text-muted">
          {/* Show "N topic(s)" only when a count was given; note 0 still counts as given. */}
          {topicCount !== undefined && (
            <span>
              {/* Singular for exactly 1, plural otherwise. */}
              {topicCount} {topicCount === 1 ? "topic" : "topics"}
            </span>
          )}
          {/* Link to the latest debate (the home page). */}
          <Link href="/" className="hover:text-ink hover:underline">
            Latest
          </Link>
          {/* Link to the list of past debates. */}
          <Link href="/archive" className="hover:text-ink hover:underline">
            Archive
          </Link>
        </nav>
      </div>
    </header>
  );
}
