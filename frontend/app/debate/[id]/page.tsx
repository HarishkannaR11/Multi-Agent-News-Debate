import { DebateView } from "@/components/debate/DebateView";
import { Header } from "@/components/Header";

// The page for one specific debate (address "/debate/<id>"); Next.js passes the <id> part in "params".
// Since Next.js 15, "params" is a Promise, so the page is an async function that waits for it.
export default async function DebatePage({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = await params;
  // Ids look like "2026-09-30:some-topic"; the ':' may arrive percent-encoded.
  let id = rawId;
  try {
    id = decodeURIComponent(rawId);
  } catch {
    // malformed escape: use it as-is and let the API answer 404
  }
  return (
    <>
      <Header />
      <main>
        <DebateView debateId={id} />
      </main>
    </>
  );
}
