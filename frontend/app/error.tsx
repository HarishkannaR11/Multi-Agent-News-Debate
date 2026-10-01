"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main role="alert" className="py-24 text-center">
      <h1 className="font-serif text-3xl font-semibold text-ink">Something went wrong</h1>
      <p className="mt-3 font-sans text-sm text-muted">The page failed to load. This is usually temporary.</p>
      <button onClick={reset} className="mt-6 font-sans text-sm font-medium text-ink underline">
        Try again
      </button>
    </main>
  );
}
