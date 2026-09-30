"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { fetchDebates, type DebateSummary } from "@/lib/api";

const PAGE_SIZE = 15;

export default function ArchivePage() {
  const [debates, setDebates] = useState<DebateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchDebates()
      .then(setDebates)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const start = page * PAGE_SIZE;
  const pageDebates = debates.slice(start, start + PAGE_SIZE);
  const hasOlder = start + PAGE_SIZE < debates.length;
  const hasNewer = page > 0;

  return (
    <main className="pb-16">
      <Header />
      <h2 className="mt-10 font-serif text-2xl font-semibold text-ink">Past debates</h2>

      {error && (
        <div role="alert" className="mt-6 font-sans text-sm text-agents-left">
          {error}{" "}
          <button onClick={load} className="underline">
            Retry
          </button>
        </div>
      )}

      <table className="mt-6 w-full border-collapse font-sans text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-[0.04em] text-muted">
            <th scope="col" className="py-3 pr-4">Date</th>
            <th scope="col" className="py-3 pr-4">Topic</th>
            <th scope="col" className="py-3 pr-4">Verdict</th>
            <th scope="col" className="py-3">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {pageDebates.map((debate, index) => (
            <tr
              key={debate.id}
              className={`border-b border-line hover:border-l-[3px] hover:border-l-ink ${
                index % 2 === 0 ? "bg-paper" : "bg-surface"
              }`}
            >
              <td className="whitespace-nowrap py-3 pr-4 text-ink">{debate.date}</td>
              <td className="py-3 pr-4 text-ink">{debate.topic}</td>
              <td className="py-3 pr-4 font-serif italic text-warm">
                {debate.verdict ? `${debate.verdict.slice(0, 120)}...` : "—"}
              </td>
              <td className="py-3">
                <Link href={`/debate/${encodeURIComponent(debate.id)}`} className="text-ink hover:underline">
                  Read<span className="sr-only">: {debate.topic}</span>
                </Link>
              </td>
            </tr>
          ))}
          {pageDebates.length === 0 && (
            <tr>
              <td colSpan={4} className="py-6 text-center text-muted">
                {loading ? "Loading..." : error ? "" : "No debates archived yet."}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="mt-6 flex justify-center gap-8 font-sans text-sm">
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={!hasOlder}
          className="text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
        >
          ← Older
        </button>
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
