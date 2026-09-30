import Link from "next/link";

export default function NotFound() {
  return (
    <main className="py-24 text-center">
      <h1 className="font-serif text-3xl font-semibold text-ink">Page not found</h1>
      <Link href="/" className="mt-6 inline-block font-sans text-sm font-medium text-ink underline">
        Back to the latest debate
      </Link>
    </main>
  );
}
