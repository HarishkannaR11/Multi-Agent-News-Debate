// Next.js's Link component: navigates between pages without a full page reload.
import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";

// The site header: compact and sticky, with the four main actions always in reach.
// "current" marks the page the visitor is on, for the visual highlight and for screen readers.
export function Header({ current }: { current?: "latest" | "archive" | "new" }) {
  // Shared look of the plain text links.
  const link = (active: boolean) =>
    `rounded px-2 py-1.5 font-sans text-sm hover:bg-surface hover:text-ink ${active ? "text-ink underline underline-offset-4" : "text-warm"}`;
  return (
    <header className="sticky top-0 z-30 -mx-6 border-b border-line bg-paper/95 px-6 backdrop-blur md:-mx-12 md:px-12">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-3">
        <Link href="/" className="font-serif text-2xl font-bold leading-none tracking-[-0.02em] text-ink">
          The Debate
          {/* The tagline is part of the name for screen readers but hidden on small screens to save space. */}
          <span className="ml-3 hidden font-sans text-xs font-normal uppercase tracking-[0.06em] text-muted lg:inline">
            Five perspectives. One verdict.
          </span>
        </Link>
        <nav aria-label="Primary" className="flex flex-wrap items-center gap-1 sm:gap-2">
          <Link href="/" className={link(current === "latest")} aria-current={current === "latest" ? "page" : undefined}>
            Latest
          </Link>
          <Link href="/archive" className={link(current === "archive")} aria-current={current === "archive" ? "page" : undefined}>
            Archive
          </Link>
          {/* Opens the archive with the search box focused. */}
          <Link href="/archive#search" className={link(false)}>
            Search
          </Link>
          <Link
            href="/new"
            aria-current={current === "new" ? "page" : undefined}
            className="rounded bg-ink px-3.5 py-2 font-sans text-sm font-medium text-paper hover:opacity-90"
          >
            New debate
          </Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
