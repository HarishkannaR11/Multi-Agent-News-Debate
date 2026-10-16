// Marks this as a client component: it uses state and loads data in the browser.
"use client";

// Next.js's Link component for navigating without a full page reload.
import Link from "next/link";
// React tools: state, effects, and useCallback (keeps a function's identity stable between renders).
import { useCallback, useEffect, useState } from "react";
// The site header.
import { Header } from "@/components/Header";
// The function that loads the list, and the type of one list entry.
import { fetchDebates, type DebateSummary } from "@/lib/api";

// How many debates to show per page of the table.
const PAGE_SIZE = 15;

// The archive page (address "/archive"): a table of past debates.
export default function ArchivePage() {
  // All debate summaries loaded from the server.
  const [debates, setDebates] = useState<DebateSummary[]>([]);
  // True while the list is loading.
  const [loading, setLoading] = useState(true);
  // An error message (null = none).
  const [error, setError] = useState<string | null>(null);
  // The current page number, starting at 0.
  const [page, setPage] = useState(0);

  // Loads the list from the server; also used by the Retry button.
  const load = useCallback(() => {
    // Show the loading text and clear any old error.
    setLoading(true);
    setError(null);
    fetchDebates()
      // On success store the list.
      .then(setDebates)
      // On failure store the error message.
      .catch((err: Error) => setError(err.message))
      // Either way, loading is over.
      .finally(() => setLoading(false));
  }, []);

  // Load the list once when the page first appears.
  useEffect(load, [load]);

  // Index of the first debate on the current page.
  const start = page * PAGE_SIZE;
  // The slice of debates to show on this page.
  const pageDebates = debates.slice(start, start + PAGE_SIZE);
  // Are there more (older) debates after this page?
  const hasOlder = start + PAGE_SIZE < debates.length;
  // Are we past the first page (so there are newer ones)?
  const hasNewer = page > 0;

  return (
    <main className="pb-16">
      <Header />
      <h2 className="mt-10 font-serif text-2xl font-semibold text-ink">Past debates</h2>

      {/* If loading failed, show the message and a Retry button. */}
      {error && (
        <div role="alert" className="mt-6 font-sans text-sm text-agents-left">
          {/* {" "} inserts a space between the message and the button. */}
          {error}{" "}
          <button onClick={load} className="underline">
            Retry
          </button>
        </div>
      )}

      {/* The table of debates. */}
      <table className="mt-6 w-full border-collapse font-sans text-sm">
        {/* Column headings; scope="col" tells screen readers these head the columns. */}
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-[0.04em] text-muted">
            <th scope="col" className="py-3 pr-4">Date</th>
            <th scope="col" className="py-3 pr-4">Topic</th>
            <th scope="col" className="py-3 pr-4">Verdict</th>
            <th scope="col" className="py-3">
              {/* The last column has no visible title; this text is for screen readers only. */}
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {/* One row per debate on this page. */}
          {pageDebates.map((debate, index) => (
            // Alternating row backgrounds (zebra stripes); the left border thickens on hover.
            <tr
              key={debate.id}
              className={`border-b border-line hover:border-l-[3px] hover:border-l-ink ${
                index % 2 === 0 ? "bg-paper" : "bg-surface"
              }`}
            >
              <td className="whitespace-nowrap py-3 pr-4 text-ink">{debate.date}</td>
              <td className="py-3 pr-4 text-ink">{debate.topic}</td>
              <td className="py-3 pr-4 font-serif italic text-warm">
                {/* The first 120 characters of the verdict, or a dash if there is none. */}
                {debate.verdict ? `${debate.verdict.slice(0, 120)}...` : "—"}
              </td>
              <td className="py-3">
                {/* Link to the debate page; the id is URL-encoded because it contains ":". */}
                <Link href={`/debate/${encodeURIComponent(debate.id)}`} className="text-ink hover:underline">
                  {/* Screen readers hear which debate the link opens. */}
                  Read<span className="sr-only">: {debate.topic}</span>
                </Link>
              </td>
            </tr>
          ))}
          {/* If this page has no rows, show a single message row spanning all four columns. */}
          {pageDebates.length === 0 && (
            <tr>
              <td colSpan={4} className="py-6 text-center text-muted">
                {/* Loading text, nothing if an error is already shown, otherwise "none yet". */}
                {loading ? "Loading..." : error ? "" : "No debates archived yet."}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Paging buttons. */}
      <div className="mt-6 flex justify-center gap-8 font-sans text-sm">
        {/* Go to the next page of older debates (disabled on the last page). */}
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={!hasOlder}
          className="text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          ← Older
        </button>
        {/* Go back one page, but never below page 0 (disabled on the first page). */}
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={!hasNewer}
          className="text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          Newer →
        </button>
      </div>
    </main>
  );
}
