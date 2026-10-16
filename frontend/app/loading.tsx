// Shown by Next.js while a page is still loading.
export default function Loading() {
  return (
    // role="status" lets screen readers announce the loading state.
    <main className="py-24 text-center" role="status">
      <p className="font-sans text-xs uppercase tracking-[0.04em] text-muted">Loading...</p>
    </main>
  );
}
