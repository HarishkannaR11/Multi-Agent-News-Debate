// Runs in the browser: search, filters and paging load results as the visitor types.
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { fetchArchive, type ArchiveItem, type ArchiveResponse } from "@/lib/api";
import { formatDay } from "@/lib/debate";
import { readIdList } from "@/lib/storage";

const PAGE_SIZE = 12;
const SCOPES = [
  { key: "all", label: "Daily debates" },
  { key: "mine", label: "My debates" },
  { key: "saved", label: "Saved" },
] as const;
type Scope = (typeof SCOPES)[number]["key"];

const STATUS_TEXT: Record<string, string> = { generating: "Generating", partial: "Partial", failed: "Failed" };

// Where each scope gets its ids: the public list needs none; the other two are remembered by this browser.
function idsFor(scope: Scope): string[] | undefined {
  if (scope === "mine") return readIdList("mine");
  if (scope === "saved") return readIdList("bookmarks");
  return undefined;
}

function Card({ item }: { item: ArchiveItem }) {
  const status = STATUS_TEXT[item.status];
  return (
    <li className="rounded border border-line bg-surface p-4">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-sans text-xs text-muted">
        <span>{formatDay(item.created_at || item.date)}</span>
        {item.category && (
          <>
            <span aria-hidden="true">·</span>
            <span>{item.category}</span>
          </>
        )}
        {status && (
          <span className="rounded-sm border border-warn px-1.5 py-0.5 font-medium text-warn">{status}</span>
        )}
      </p>
      <h3 className="mt-2 font-serif text-xl font-semibold leading-snug text-ink">
        <Link href={`/debate/${encodeURIComponent(item.id)}`} className="hover:underline">
          {item.topic}
        </Link>
      </h3>
      {item.summary && <p className="mt-2 line-clamp-3 font-sans text-sm leading-relaxed text-warm">{item.summary}</p>}
      <p className="mt-3 font-sans text-xs text-muted">
        {item.completed} of 5 perspectives · {item.origin === "user" ? "Started by a visitor" : "Daily debate"}
      </p>
    </li>
  );
}

// The archive page (address "/archive"): search, category filter, sorting and paging done on the server.
export default function ArchivePage() {
  const [scope, setScope] = useState<Scope>("all");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<ArchiveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // The search text actually sent to the server (the typed text, after a short pause).
  const [sentQuery, setSentQuery] = useState("");
  const ready = useRef(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // Restore the filters from the address once, and focus the search box for the "Search" link (#search).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q") ?? "";
    setQuery(q);
    setSentQuery(q);
    setCategory(params.get("category") ?? "");
    setSort(params.get("sort") === "oldest" ? "oldest" : "newest");
    const s = params.get("scope");
    if (s === "mine" || s === "saved") setScope(s);
    setPage(Math.max(0, Number(params.get("page") ?? 1) - 1) || 0);
    ready.current = true;
    if (window.location.hash === "#search") searchRef.current?.focus();
  }, []);

  // Wait for a pause in typing before asking the server, so one request is not sent per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSentQuery((previous) => {
        if (previous !== query.trim()) setPage(0);
        return query.trim();
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Load the results whenever a filter changes. An older request that is still running is cancelled.
  useEffect(() => {
    if (!ready.current) return;
    const controller = new AbortController();
    const ids = idsFor(scope);
    if (ids && ids.length === 0) {
      setData({ items: [], total: 0, categories: [], offset: 0, limit: PAGE_SIZE });
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchArchive({ q: sentQuery, category, sort, offset: page * PAGE_SIZE, limit: PAGE_SIZE, ids }, controller.signal)
      .then((result) => setData(result))
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [scope, sentQuery, category, sort, page, reloadKey]);

  // Keep the address in step with the filters, so a refresh or a shared link shows the same list.
  useEffect(() => {
    if (!ready.current) return;
    const params = new URLSearchParams();
    if (sentQuery) params.set("q", sentQuery);
    if (category) params.set("category", category);
    if (sort !== "newest") params.set("sort", sort);
    if (scope !== "all") params.set("scope", scope);
    if (page > 0) params.set("page", String(page + 1));
    const text = params.toString();
    window.history.replaceState(null, "", text ? `/archive?${text}` : "/archive");
  }, [sentQuery, category, sort, scope, page]);

  const changeScope = useCallback((next: Scope) => {
    setScope(next);
    setPage(0);
    setCategory("");
  }, []);

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = Boolean(sentQuery || category);
  const field = "rounded border border-edge bg-surface px-3 py-2 font-sans text-sm text-ink";

  return (
    <>
      <Header current="archive" />
      <main className="pb-16">
        <h1 className="mt-10 font-serif text-3xl font-semibold text-ink">Archive</h1>

        <div role="group" aria-label="Which debates" className="mt-6 flex gap-1 border-b border-line">
          {SCOPES.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={scope === s.key}
              onClick={() => changeScope(s.key)}
              className={`-mb-px border-b-2 px-3 py-2 font-sans text-sm ${scope === s.key ? "border-ink font-semibold text-ink" : "border-transparent text-warm hover:text-ink"}`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <form role="search" onSubmit={(event) => event.preventDefault()} className="mt-5 flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <label htmlFor="search" className="block font-sans text-xs font-medium text-muted">
              Search
            </label>
            <input
              id="search"
              ref={searchRef}
              type="search"
              value={query}
              maxLength={100}
              placeholder="Search questions and summaries"
              onChange={(event) => setQuery(event.target.value)}
              className={`mt-1 w-full ${field}`}
            />
          </div>
          <div>
            <label htmlFor="category" className="block font-sans text-xs font-medium text-muted">
              Category
            </label>
            <select
              id="category"
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setPage(0);
              }}
              className={`mt-1 ${field}`}
            >
              <option value="">All categories</option>
              {(data?.categories ?? []).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
              {category && !(data?.categories ?? []).includes(category) && <option value={category}>{category}</option>}
            </select>
          </div>
          <div>
            <label htmlFor="sort" className="block font-sans text-xs font-medium text-muted">
              Sort by
            </label>
            <select
              id="sort"
              value={sort}
              onChange={(event) => {
                setSort(event.target.value as "newest" | "oldest");
                setPage(0);
              }}
              className={`mt-1 ${field}`}
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </div>
          {filtered && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setSentQuery("");
                setCategory("");
                setPage(0);
              }}
              className="py-2 font-sans text-sm text-ink underline"
            >
              Clear filters
            </button>
          )}
        </form>

        <p className="mt-4 font-sans text-sm text-muted" role="status" aria-live="polite">
          {loading ? "Loading…" : error ? "" : `${total} debate${total === 1 ? "" : "s"}${filtered ? " match" : ""}`}
        </p>

        {error && (
          <div role="alert" className="mt-4 rounded border border-warn p-4 font-sans text-sm text-warn">
            {error}{" "}
            <button type="button" onClick={() => setReloadKey((n) => n + 1)} className="ml-2 underline">
              Retry
            </button>
          </div>
        )}

        {loading && !data && (
          <ul className="mt-4 grid gap-4 md:grid-cols-2" aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="skeleton h-32 rounded border border-line bg-surface" />
            ))}
          </ul>
        )}

        {data && !error && data.items.length > 0 && (
          <ul className={`mt-4 grid gap-4 md:grid-cols-2 ${loading ? "opacity-60" : ""}`}>
            {data.items.map((item) => (
              <Card key={item.id} item={item} />
            ))}
          </ul>
        )}

        {data && !error && !loading && data.items.length === 0 && (
          <div className="mt-8 max-w-reading font-sans text-base text-warm">
            {filtered ? (
              <p>No debates match those filters. Try fewer words or clear the filters.</p>
            ) : scope === "mine" ? (
              <p>
                Debates you start from this browser appear here. <Link href="/new" className="text-ink underline">Start one</Link>.
              </p>
            ) : scope === "saved" ? (
              <p>Use &ldquo;Save&rdquo; on a debate to keep it here. Saved debates stay in this browser only.</p>
            ) : (
              <p>No daily debates have been published yet.</p>
            )}
          </div>
        )}

        {total > PAGE_SIZE && !error && (
          <nav aria-label="Pages" className="mt-8 flex items-center justify-center gap-8 font-sans text-sm">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
            >
              ← Previous
            </button>
            <span className="text-muted">
              Page {page + 1} of {pages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page + 1 >= pages}
              className="text-ink hover:underline disabled:text-muted disabled:hover:no-underline"
            >
              Next →
            </button>
          </nav>
        )}
      </main>
    </>
  );
}
