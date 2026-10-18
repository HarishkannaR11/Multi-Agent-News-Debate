// Next.js's Link component for navigating without a full page reload.
import Link from "next/link";

// Shown for any address that does not match a page (a 404).
export default function NotFound() {
  return (
    <main className="py-24 text-center">
      <h1 className="font-serif text-3xl font-semibold text-ink">Page not found</h1>
      <div className="mt-6 flex justify-center gap-6 font-sans text-sm font-medium">
        <Link href="/" className="text-ink underline">
          Latest debate
        </Link>
        <Link href="/archive" className="text-ink underline">
          Archive
        </Link>
        <Link href="/new" className="text-ink underline">
          Start a debate
        </Link>
      </div>
    </main>
  );
}
