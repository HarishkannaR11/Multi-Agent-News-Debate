// Next.js's Link component for navigating without a full page reload.
import Link from "next/link";

// Shown for any address that does not match a page (a 404).
export default function NotFound() {
  return (
    <main className="py-24 text-center">
      <h1 className="font-serif text-3xl font-semibold text-ink">Page not found</h1>
      {/* A link back to the home page. */}
      <Link href="/" className="mt-6 inline-block font-sans text-sm font-medium text-ink underline">
        Back to the latest debate
      </Link>
    </main>
  );
}
