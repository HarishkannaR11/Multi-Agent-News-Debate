import Link from "next/link";
import { DebateView } from "@/components/debate/DebateView";
import { Header } from "@/components/Header";

// The home page (address "/"): the latest daily debate, with a clear way to start your own.
export default function HomePage() {
  return (
    <>
      <Header current="latest" />
      <main>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded border border-line bg-surface px-4 py-3 font-sans text-sm text-warm">
          <span>Today&rsquo;s debate is below. Want five perspectives on a question of your own?</span>
          <Link href="/new" className="rounded bg-ink px-3.5 py-2 font-medium text-paper hover:opacity-90">
            Start a debate
          </Link>
        </div>
        {/* "latest" asks the server for the newest daily debate. */}
        <DebateView debateId="latest" />
      </main>
    </>
  );
}
