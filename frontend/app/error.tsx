// Marks this as a client component (Next.js requires error pages to run in the browser).
"use client";

// Shown when something crashes while rendering a page. Next.js passes "error" (unused here) and "reset" (retry).
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    // role="alert" makes screen readers announce the message immediately.
    <main role="alert" className="py-24 text-center">
      <h1 className="font-serif text-3xl font-semibold text-ink">Something went wrong</h1>
      <p className="mt-3 font-sans text-sm text-muted">The page failed to load. This is usually temporary.</p>
      {/* Clicking asks Next.js to try rendering the page again. */}
      <button onClick={reset} className="mt-6 font-sans text-sm font-medium text-ink underline">
        Try again
      </button>
    </main>
  );
}
